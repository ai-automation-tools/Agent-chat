"""POST /api/orchestrate — validate, preflight, seed a conversation.

Also (Phase 2b) resolves an optional per-CLI persona cast and, on the local
machine, best-effort spawns one CLI window per participant in character via
``scripts/orchestrate-debate.ps1``. Seeding always succeeds independently of
whether the spawn is possible (hosted mirror, non-Windows, no ``pwsh``).
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import delivery as orch_delivery
from orchestrator import personas as orch_personas
from orchestrator import preflight as orch_preflight
from orchestrator import seeding as orch_seeding
from orchestrator import seats as orch_seats
from orchestrator.conv_types import CONV_TYPES, ConvTypeError, normalize_conv_type
from presets import PRESETS, PRESET_NAMES

from web import db
from web.security import _is_public_readonly

# Sentinel values a persona <select> can post per CLI. Anything else is treated
# as a slug / display name to resolve against the registry.
_PERSONA_RANDOM = "__random__"
_PERSONA_NONE = "__none__"
# A card uploaded on the form for one run. It lands in `participant_personas`
# like any other cast entry but with an EMPTY slug, and is never written to the
# `personas` table — same reasoning as the Battleground's custom instructions
# (docs/App/battleground.md): a one-off is not a registry entry. Every consumer
# of `persona_slug` already falls back when it is blank — `export.persona_doc`
# and `bundle_files` drop the `-<slug>` from the filename, `media_prompts`
# strips it, and the reader resolves the avatar from the agent id — so this
# needs no schema change and no export-contract change.
_PERSONA_CUSTOM = "__custom__"
# Guard the parse, not just the upload: the browser caps the file, but this
# route is reachable without it.
_PERSONA_CUSTOM_MAX_CHARS = 100_000


async def api_orchestrate(request: Request) -> Response:
    """POST /api/orchestrate — validate body, run preflight on selected CLIs, seed conversation.

    Response shape:
      success → {"ok": true, "conversation_id": N}
      preflight failure → {"ok": false, "kind": "preflight_failed",
                           "preflight": [PreflightResult...], "log_path": "..."}
      validation/seed error → {"ok": false, "kind": "validation"|"seed_error", "error": "..."}

    A log file is written to ``<repo>/logs/orchestrator-<timestamp>.log`` on
    preflight failure so the operator can inspect the full report later.
    Successful runs do not write a log (the conversation row is the audit trail).
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "request body must be JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "JSON body must be an object"}, status_code=400)

    topic = (payload.get("topic") or "").strip()
    if not topic:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "topic is required"}, status_code=400)
    # `seed_conversation()` enforces this too — it has to, so start_conversation.py
    # is covered. Checking it here as well only buys the operator the error
    # before preflight spends thirty seconds validating every CLI's MCP config.
    if len(topic) > orch_seeding.TOPIC_MAX_CHARS:
        return JSONResponse(
            {"ok": False, "kind": "validation",
             "error": (f"topic is {len(topic)} characters; the limit is "
                       f"{orch_seeding.TOPIC_MAX_CHARS}. It becomes the page "
                       "heading and the export slug — put a long brief in the "
                       "Brief box instead, where the agents read it as the "
                       "conversation's first message.")},
            status_code=400)

    participants = payload.get("participants") or []
    if not isinstance(participants, list) or not all(isinstance(p, str) for p in participants):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "participants must be a list of strings"}, status_code=400)
    participants = [p.strip() for p in participants if p.strip()]

    try:
        conv_type = normalize_conv_type(payload.get("conv_type"))
    except ConvTypeError as e:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": str(e)}, status_code=400)
    type_spec = CONV_TYPES[conv_type]

    # What ``participants`` means depends on the type (see
    # ConvType.lead_needs_own_seat):
    #
    # - lead on its own seat (debate, podcast): the *member* list only. The lead
    #   arrives separately as ``moderator`` and is prepended below.
    # - lead is a member (collaborate): the WHOLE room. Whoever speaks first
    #   holds the lead role, and no separate seat is asked for.
    if type_spec.lead_needs_own_seat:
        lo, hi, noun = (type_spec.min_members, type_spec.max_members,
                        type_spec.members_label.lower())
    else:
        lo, hi, noun = (type_spec.min_participants, type_spec.max_participants,
                        type_spec.members_label.lower())
    if not lo <= len(participants) <= hi:
        return JSONResponse({
            "ok": False, "kind": "validation",
            "error": f"select {lo}–{hi} {noun}; got {len(participants)}",
        }, status_code=400)

    preset = payload.get("preset") or None
    if preset is not None and preset not in PRESET_NAMES:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": f"unknown preset {preset!r}; "
                                      f"choices: {', '.join(PRESET_NAMES)}"}, status_code=400)

    max_turns_raw = payload.get("max_turns")
    if max_turns_raw is None:
        max_turns = PRESETS[preset]["max_turns"] if preset else 10
    else:
        try:
            max_turns = int(max_turns_raw)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "max_turns must be an integer"}, status_code=400)
        if max_turns < 1 or max_turns > 50:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "max_turns must be between 1 and 50"}, status_code=400)

    first = payload.get("first") or None
    if first and first not in participants:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": f"first speaker {first!r} is not in participants"}, status_code=400)

    mode = PRESETS[preset]["mode"] if preset else "turns"
    tone = PRESETS[preset]["tone"] if preset else None
    initial_msg = (payload.get("kickoff") or "").strip() or None

    # ---- extra seat roles (optional) ----------------------------------------
    # ``roles`` maps cli -> one of the type's EXTRA roles (today: a
    # collaboration's ``skeptic``). Deliberately not a way to set the lead or
    # the member role: those are decided by ``moderator`` / seat order below,
    # and letting the form post them too would give two mechanisms for one
    # seat. An extra role re-brands a seat the operator already picked, so it
    # never changes the participant count.
    extra_roles_pick = payload.get("roles") or {}
    if not isinstance(extra_roles_pick, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in extra_roles_pick.items()):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "roles must be an object mapping cli -> role"},
                            status_code=400)
    extra_roles_pick = {k.strip(): v.strip()
                        for k, v in extra_roles_pick.items() if v.strip()}
    allowed_extras = {e.role for e in type_spec.extra_roles}
    for cli, role in extra_roles_pick.items():
        if role not in allowed_extras:
            offer = (", ".join(sorted(allowed_extras)) if allowed_extras
                     else "none — this format has no extra seats")
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": f"{role!r} is not an extra seat a {conv_type} "
                                          f"offers; choices: {offer}"}, status_code=400)
        if cli not in participants:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": f"cannot make {cli!r} the {role} — it is not "
                                          "one of the selected participants"},
                                status_code=400)

    # ---- persona cast (optional) --------------------------------------------
    # ``personas`` maps cli -> slug/name | "__random__" | "__none__"/"". Resolve
    # it into the participant_personas dict seed_conversation stores as JSON (so
    # the Cast panel + .zip export are self-describing) and the spawn wrapper
    # reads back. A bad slug is a validation error; seeding never runs on one.
    personas_pick = payload.get("personas") or {}
    if not isinstance(personas_pick, dict):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "personas must be an object mapping cli -> selection"},
                            status_code=400)
    persona_custom = payload.get("persona_custom") or {}
    if not isinstance(persona_custom, dict):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "persona_custom must be an object mapping cli -> "
                                      "{filename, text}"}, status_code=400)
    try:
        participant_personas = _resolve_personas(participants, personas_pick, persona_custom)
    except _CastError as e:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": str(e)}, status_code=400)

    # ---- moderator / host (optional) ----------------------------------------
    # ``moderator`` is ``{cli, persona}`` | null. The host runs on its own CLI
    # (not a debater), speaks first, and keeps the debate on turns rotation — so
    # a moderator forces mode='turns' (a continuous host is an uncoordinated
    # free-for-all). Its persona is added to participant_personas like any other;
    # the spawn layer tags it role='moderator' so it gets the host prompt.
    moderator = payload.get("moderator") or None
    moderator_cli: str | None = None

    # A type whose lead is one of the members has no separate lead seat to ask
    # for. Refuse rather than quietly ignore: a caller that sent one believes it
    # is choosing the facilitator, and silently dropping it would seat somebody
    # else. The lead here is `first` — see the role assignment below.
    if moderator is not None and not type_spec.lead_needs_own_seat:
        return JSONResponse({
            "ok": False, "kind": "validation",
            "error": (f"a {conv_type} takes no separate "
                      f"{type_spec.lead_label.lower()} seat — the "
                      f"{type_spec.lead_label.lower()} is whichever participant "
                      f"speaks first. Pass 'first' instead of 'moderator'."),
        }, status_code=400)

    if moderator is None and type_spec.lead_required and type_spec.lead_needs_own_seat:
        return JSONResponse({
            "ok": False, "kind": "validation",
            "error": (f"a {conv_type} needs a {type_spec.lead_label.lower()} — "
                      f"pick the seat it runs on"),
        }, status_code=400)
    if moderator is not None:
        if not isinstance(moderator, dict):
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "moderator must be an object {cli, persona} or null"},
                                status_code=400)
        moderator_cli = (moderator.get("cli") or "").strip() or None
        if not moderator_cli:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "moderator.cli is required when a moderator is set"},
                                status_code=400)
        if not orch_seats.is_seat(moderator_cli):
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": f"unknown moderator cli {moderator_cli!r}; "
                                          f"choices: {', '.join(orch_preflight.SUPPORTED_CLIS)}"},
                                status_code=400)
        # Seats, not tools: the host needs its own *seat*, but that seat may be
        # a second window of a tool a debater is already using ('codex-2').
        if moderator_cli in participants:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": f"moderator seat {moderator_cli!r} is already a debater; "
                                          "the host needs its own seat"}, status_code=400)
        try:
            mod_entry = _resolve_moderator_persona(
                (moderator.get("persona") if isinstance(moderator.get("persona"), str) else ""),
                exclude_slugs={e["persona_slug"] for e in participant_personas.values()},
                lead_group=type_spec.lead_group,
            )
        except _CastError as e:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": str(e)}, status_code=400)
        if mod_entry is not None:
            participant_personas[moderator_cli] = mod_entry

    # Effective seed params: the lead opens, and for a type it *runs* it also
    # forces orderly rotation (see ConvType.lead_forces_turns — a continuous
    # moderator is a free-for-all). A collaboration's facilitator doesn't police
    # the floor, so there the preset's own mode stands and a brainstorm stays
    # continuous.
    seed_participants = ([moderator_cli] + participants) if moderator_cli else participants
    seed_first = moderator_cli or first
    seed_mode = "turns" if (moderator_cli and type_spec.lead_forces_turns) else mode

    # Seat roles: only the lead is named here; seeding fills in the member role
    # for everyone else and re-validates the whole set against the type.
    participant_roles = (
        {moderator_cli: type_spec.lead_role} if moderator_cli else None
    )

    # Lead-is-a-member types: the first speaker holds the lead role. Move it to
    # the head of the list and let `conv_types.default_roles()` assign from seat
    # order — the same rule `start_conversation.py` gets for free. Leaving roles
    # as None keeps ONE definition of "the lead is participants[0]".
    if type_spec.lead_required and not type_spec.lead_needs_own_seat:
        lead_seat = seed_first or seed_participants[0]
        seed_participants = [lead_seat] + [p for p in seed_participants if p != lead_seat]
        seed_first = lead_seat
        participant_roles = None

    # Extra seats are layered on last, over whichever of the two branches above
    # ran. When the lead was left implicit (roles is None so `default_roles()`
    # can assign from seat order), it has to be written down here — the map
    # stops being a partial one the moment it names a second seat.
    if extra_roles_pick:
        lead_seat = (moderator_cli
                     or (seed_first or seed_participants[0]
                         if type_spec.lead_required else None))
        clash = [c for c in extra_roles_pick if c == lead_seat]
        if clash:
            return JSONResponse({
                "ok": False, "kind": "validation",
                "error": (f"{lead_seat!r} is the {type_spec.lead_label.lower()} and "
                          f"cannot also be the {extra_roles_pick[clash[0]]} — pick "
                          "another seat, or change who speaks first"),
            }, status_code=400)
        merged = dict(participant_roles or {})
        if lead_seat and not participant_roles:
            merged[lead_seat] = type_spec.lead_role
        merged.update(extra_roles_pick)
        participant_roles = merged

    # ---- preflight gate ------------------------------------------------------
    results = orch_preflight.run_preflight(seed_participants)
    if not all(r.ok for r in results):
        log_path = _write_preflight_log(results, topic)
        return JSONResponse({
            "ok": False,
            "kind": "preflight_failed",
            "preflight": [_preflight_to_dict(r) for r in results],
            "log_path": str(log_path),
        }, status_code=409)

    # ---- seed ----------------------------------------------------------------
    try:
        seed = orch_seeding.seed_conversation(
            db_path=db.DB_PATH,
            topic=topic,
            participants=seed_participants,
            mode=seed_mode,
            max_turns=max_turns,
            first=seed_first,
            preset=preset,
            tone=tone,
            initial_system_message=initial_msg,
            participant_personas=participant_personas or None,
            conv_type=conv_type,
            participant_roles=participant_roles,
        )
    except orch_seeding.SeedError as e:
        return JSONResponse({"ok": False, "kind": "seed_error",
                             "error": str(e)}, status_code=400)

    # ---- record the delivery opt-in -----------------------------------------
    # Purely local bookkeeping (config/delivery-optin.json, gitignored, never
    # synced) and deliberately AFTER the seed: a conversation that exists but
    # isn't marked loses a copy, while a mark with no conversation is a lie.
    # mark_opt_in() cannot raise, so a read-only config directory costs the
    # copy, not the launch.
    delivered = False
    if payload.get("deliver_locally"):
        delivered = orch_delivery.mark_opt_in(seed.conversation_id)

    # ---- best-effort spawn ---------------------------------------------------
    if payload.get("spawn"):
        spawn = _maybe_spawn(
            conversation_id=seed.conversation_id,
            topic=topic,
            participants=seed_participants,
            first=seed.first,
            participant_personas=participant_personas,
            participant_roles=seed.participant_roles,
            skip_permissions=bool(payload.get("skip_permissions")),
        )
    else:
        spawn = {"status": "skipped", "detail": "auto-spawn not requested"}

    return JSONResponse({
        "ok": True,
        "conversation_id": seed.conversation_id,
        "spawn": spawn,
        "deliver_locally": delivered,
    })


class _CastError(ValueError):
    """Raised when a persona pick can't be resolved; caller renders .args[0]."""


def _persona_entry(p: orch_personas.Persona) -> dict[str, str]:
    return {"persona_slug": p.slug, "persona_name": p.name, "persona_body": p.body}


def _custom_persona_entry(cli: str, raw: Any) -> dict[str, str]:
    """Parse an uploaded persona card into a cast entry, without saving it.

    ``raw`` is the ``{"filename", "text"}`` the form sends for a seat set to
    ``__custom__``. The card is parsed by the same
    :func:`orchestrator.personas.parse_card_text` the registry importer uses, so
    a file that works on /personas works here — but the result goes straight
    into ``participant_personas`` with an **empty slug** and no DB write. The
    filename is only used to name the persona when the card has no title.
    """
    if not isinstance(raw, dict):
        raise _CastError(f"custom persona for {cli!r} must be an object with a 'text' field")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _CastError(f"custom persona for {cli!r} is empty")
    if len(text) > _PERSONA_CUSTOM_MAX_CHARS:
        raise _CastError(
            f"custom persona for {cli!r} is {len(text)} characters; "
            f"the limit is {_PERSONA_CUSTOM_MAX_CHARS}"
        )
    filename = str(raw.get("filename") or "").strip()
    stem = Path(filename).stem if filename else "custom"
    parsed = orch_personas.parse_card_text(
        text, orch_personas.slugify(stem) or "custom", "Custom")
    # Slug stays EMPTY on purpose. A slug is a claim that this card is in the
    # registry, and this one never will be; writing the file stem there would
    # make the export name a persona file after a card nobody can look up.
    return {"persona_slug": "", "persona_name": parsed.name, "persona_body": parsed.body}


def _resolve_personas(
    participants: list[str],
    picks: dict[str, Any],
    custom: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Turn a cli -> selection map into {cli: {persona_slug, persona_name,
    persona_body}} for the participants that got a persona.

    Explicit slugs/names resolve across every group; ``__random__`` draws from
    the debater roster (falling back to the whole registry if that group is
    empty), never repeating a persona already picked in the same cast.
    ``__custom__`` takes the card the form uploaded for that seat, parses it in
    memory and gives it an empty slug — it is used for this run and never saved.
    ``__none__`` / blank leaves that CLI plain. Raises :class:`_CastError` on an
    unknown slug, a bad custom card, or when there aren't enough personas to
    satisfy the random picks.
    """
    custom = custom or {}
    result: dict[str, dict[str, str]] = {}
    used_slugs: set[str] = set()
    random_clis: list[str] = []

    for cli in participants:
        raw = picks.get(cli)
        val = (raw if isinstance(raw, str) else "").strip()
        if not val or val == _PERSONA_NONE:
            continue
        if val == _PERSONA_RANDOM:
            random_clis.append(cli)
            continue
        if val == _PERSONA_CUSTOM:
            if cli not in custom:
                raise _CastError(
                    f"{cli!r} is set to a custom persona but no card was uploaded")
            result[cli] = _custom_persona_entry(cli, custom[cli])
            continue
        persona = orch_personas.get_persona(val)
        if persona is None:
            raise _CastError(f"persona not found for {cli!r}: {val!r}")
        result[cli] = _persona_entry(persona)
        used_slugs.add(persona.slug)

    if random_clis:
        # DEFAULT_DEBATER_GROUP is often empty (the roster was reorganised into
        # per-category groups), so this normally falls through to the whole
        # registry — which is why the fallback must exclude the reserved
        # AI-Models reference cards rather than calling list_personas(None).
        pool = orch_personas.list_personas(orch_personas.DEFAULT_DEBATER_GROUP)
        if not pool:
            pool = orch_personas.list_debater_personas()
        available = [p for p in pool if p.slug not in used_slugs]
        random.shuffle(available)
        if len(available) < len(random_clis):
            raise _CastError(
                f"not enough personas in the registry for {len(random_clis)} "
                f"random pick(s) (found {len(available)} unused)"
            )
        for cli in random_clis:
            persona = available.pop()
            used_slugs.add(persona.slug)
            result[cli] = _persona_entry(persona)

    return result


def _resolve_moderator_persona(
    value: str,
    exclude_slugs: set[str],
    lead_group: str = "Debate-Hosts",
) -> dict[str, str] | None:
    """Resolve the lead seat's persona pick into a persona entry, or ``None`` for
    the built-in generic host (blank / ``__none__``).

    ``__random__`` prefers ``lead_group`` — the host roster, shared by every
    conversation type (see ``orchestrator.conv_types``) — falling back to the
    whole registry when that group holds no cards, and skipping any slug
    already cast as a member. An
    explicit slug/name resolves across all groups. Raises :class:`_CastError` on
    an unknown pick or an empty pool for a random host.
    """
    val = (value or "").strip()
    if not val or val == _PERSONA_NONE:
        return None
    if val == _PERSONA_RANDOM:
        pool = (orch_personas.list_personas(lead_group)
                or orch_personas.list_debater_personas())
        available = [p for p in pool if p.slug not in exclude_slugs]
        if not available:
            raise _CastError("no personas available for a random moderator")
        random.shuffle(available)
        return _persona_entry(available[0])
    persona = orch_personas.get_persona(val)
    if persona is None:
        raise _CastError(f"moderator persona not found: {val!r}")
    return _persona_entry(persona)


def _maybe_spawn(
    *,
    conversation_id: int,
    topic: str,
    participants: list[str],
    first: str,
    participant_personas: dict[str, dict[str, str]],
    skip_permissions: bool,
    participant_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Best-effort: launch one CLI window per participant via the PowerShell
    spawn wrapper. Returns a status dict; never raises (seeding already
    succeeded, so a spawn problem must not fail the request).

    Statuses: ``launched`` (wrapper started), ``unavailable`` (hosted / non-
    Windows / no pwsh — includes the manual command to run), ``error``.
    """
    manual = f".\\scripts\\orchestrate-debate.ps1  (conversation #{conversation_id})"
    if _is_public_readonly():
        return {"status": "unavailable",
                "detail": "the hosted mirror can't spawn local CLIs"}
    if sys.platform != "win32":
        return {"status": "unavailable",
                "detail": "agent spawn is Windows-only", "manual": manual}
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return {"status": "unavailable",
                "detail": "pwsh not found on PATH", "manual": manual}

    # <repo>/src/web/api/orchestrate.py → parents[3] is the repo root.
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "orchestrate-debate.ps1"
    if not script.exists():
        return {"status": "unavailable",
                "detail": f"spawn wrapper missing at {script}", "manual": manual}

    # Launch order: --first speaker first (the lead seat, when present), then the
    # rest in declared order. Each agent carries its seat role verbatim, so the
    # spawn wrapper hands it the matching prompt shape (host / guest / moderator
    # / debater — see New-AgentPrompt in scripts/lib/spawn-agents.ps1).
    roles = participant_roles or {}
    ordered = [first] + [c for c in participants if c != first]
    agents = [{
        "cli": c,
        "persona_name": participant_personas.get(c, {}).get("persona_name", ""),
        "persona_body": participant_personas.get(c, {}).get("persona_body", ""),
        "role": roles.get(c, "debater"),
    } for c in ordered]

    launch_dir = repo_root / "db" / "launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    assign_file = launch_dir / f"orch-{conversation_id}-{uuid.uuid4().hex[:8]}.json"
    try:
        assign_file.write_text(json.dumps({
            "conversation_id": conversation_id,
            "topic": topic,
            "skip_permissions": skip_permissions,
            "agents": agents,
        }), encoding="utf-8")
    except OSError as e:
        return {"status": "error", "detail": f"could not write assignments file: {e}",
                "manual": manual}

    cmd = [pwsh, "-NoProfile", "-File", str(script),
           "-AssignmentsFile", str(assign_file)]
    try:
        # Detached + no console: the wrapper opens its own visible pwsh windows
        # (one per agent) and exits; we don't wait on it.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(cmd, creationflags=creationflags, cwd=str(repo_root))
    except OSError as e:
        return {"status": "error", "detail": f"failed to launch spawn wrapper: {e}",
                "manual": manual}

    return {"status": "launched", "detail": f"spawning {len(agents)} CLI window(s)",
            "agents": [a["cli"] for a in agents]}


def _preflight_to_dict(r: orch_preflight.PreflightResult) -> dict[str, Any]:
    """Serialize a PreflightResult for the JSON response."""
    return {
        "cli": r.cli,
        "ok": r.ok,
        "config_path": r.config_path,
        "command": r.command,
        "launcher_path": r.launcher_path,
        "failures": [{"code": f.code, "detail": f.detail} for f in r.failures],
    }


def _write_preflight_log(
    results: list[orch_preflight.PreflightResult],
    topic: str,
) -> Path:
    """Write a preflight-failure audit log under ``<repo>/logs/``.

    Filename uses an ISO-ish timestamp (no colons, safe on Windows):
    ``orchestrator-2026-05-15T14-32-09.log``. Best-effort: on filesystem
    failure (read-only, disk full, etc.), returns the intended path
    anyway so the caller's response message stays consistent.
    """
    # This file lives at <repo>/src/web/api/orchestrate.py — parents[3] is the
    # repo root (parents[2] would be src/).
    repo_root = Path(__file__).resolve().parents[3]
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    log_path = log_dir / f"orchestrator-{stamp}.log"
    try:
        with log_path.open("w", encoding="utf-8") as f:
            f.write(f"# Orchestrator preflight failure — {stamp}\n")
            f.write(f"# Topic: {topic}\n")
            f.write(f"# Requested CLIs: {', '.join(r.cli for r in results)}\n\n")
            f.write(orch_preflight.format_preflight_log(results))
    except OSError:
        pass
    return log_path
