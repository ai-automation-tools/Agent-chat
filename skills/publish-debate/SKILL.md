---
name: publish-debate
description: Use when the operator asks you to PUBLISH / export / archive / file a finished debate into the AI-Automation-Library (as opposed to starting or joining one). Triggered by phrases like "publish conversation #N to the library", "publish this debate under Technology", "add that debate to the AI library", "file the restaurant debate", "generate a cover for the debate", "publish everything from this week". Covers scripts/publish_debate.py (bundle straight from chat.db — no ZIP download) plus generating the cover-image.png from the master cover prompt.
---

# publish-debate — file a finished debate into the AI-Automation-Library

## When this skill applies

The operator wants a **completed** conversation published into the library
archive at `AI-Automation-Library/My-Library/Content/Agent-Debates/<Category>/<slug>/`
— the curated store that feeds the library site and the debate-chat-theater app.
Publishing = write the markdown bundle **and** generate the cover image.

Local-only: the library repo lives on this machine (sibling of this repo under
`Live_Apps/`). The hosted mirror can't publish.

> Starting a debate is [`start-debate`](../start-debate/SKILL.md); participating
> is [`agent-chat`](../agent-chat/SKILL.md). This skill is for afterwards.

## The workflow

### 1. Identify the conversation

If the operator gave a topic instead of an id, find it:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py list
```

Only publish `status='complete'` conversations (the script enforces this;
`--force` overrides for deliberate exceptions).

### 2. Pick the category bucket

List what buckets already exist and reuse the best fit:

```powershell
Get-ChildItem ..\AI-Automation-Library\My-Library\Content\Agent-Debates -Directory
```

Buckets are broad topics (e.g. `Technology`, `Space-&-Science`,
`Society-&-Culture` — the live set may differ; `Prompts/` is not a bucket).
Only propose a **new** bucket when the debate clearly fits none — confirm a
new bucket name with the operator first.

### 3. Write the bundle

```powershell
.\.venv\Scripts\python.exe scripts\publish_debate.py --cid <N> --category "<Bucket>"
```

This writes `topic.md` + `transcript.md` + `personas/*.md` straight from
`db/chat.db` into `<Bucket>/<topic-slug>/` — same renderers as the web UI's
export endpoints, no ZIP involved.

| Flag | Effect |
|---|---|
| `--cid N` | Conversation id (required) |
| `--category "X"` | Bucket folder; created if new (required) |
| `--push` | After writing: stage the debate folder, commit, and push to the library repo. Safe by construction — see step 5. |
| `--force` | Overwrite a **different** conversation's folder (slug collision) / publish a non-complete conversation. Re-publishing the *same* conversation never needs it. Never touches `cover-image.png`. |
| `--db-path`, `--library-root` | Overrides; defaults are `db/chat.db` and the sibling-repo library (`$AGENT_DEBATES_ROOT` also works) |

Don't pass `--push` yet on this first run — the cover isn't in the folder, and
one commit should carry the whole debate (step 5).

Batch: run once per id — e.g. every completed conversation the library doesn't
have yet. Report per-id results.

### 4. Generate the cover image

Read the freshly written `topic.md` and the first few turns of `transcript.md`,
then fill the two bracketed fields of the master prompt below:

| Field | What to put |
|---|---|
| `[DEBATE_TITLE]` | The debate title (the `topic.md` H1) |
| `[TOPIC_SPECIFIC_SCENE]` | A concrete environment tied to the subject — e.g. a future lab, courtroom-like evidence room, orbital command deck, restaurant kitchen pass |
| `[TOPIC_SPECIFIC_METAPHOR]` | The one central object/visual idea that summarizes the debate — e.g. a holographic brain, an evidence table, a wireframe planet |

Generate with whatever image tool this session has, and save the result as
`cover-image.png` **inside the debate folder** (exact filename; 16:9 landscape).

#### Master cover prompt

```text
Use case: stylized-concept
Asset type: web app debate cover image, final PNG replacement
Primary request: Create a cinematic 16:9 cover image for an AI agent debate titled "[DEBATE_TITLE]".

Scene/backdrop: [TOPIC_SPECIFIC_SCENE]. The setting should feel like an intelligent debate space blended with the subject matter of the debate, not a literal podcast studio.

Subject: two or three abstract AI-agent debaters represented as luminous digital silhouettes, holographic avatars, or wireframe human-like forms. They should appear to be debating across podiums, a table, or a shared interface. Include a clear central visual metaphor for the topic: [TOPIC_SPECIFIC_METAPHOR].

Style/medium: polished editorial technology illustration, cinematic sci-fi realism, premium magazine feature art, sophisticated and grounded. The image should match a high-end AI/devtools publication cover: detailed, atmospheric, sharp, and visually rich without becoming cluttered.

Composition/framing: wide landscape 16:9 cover, strong central focal point, clear depth, clean margins, no important subject matter at the extreme edges. The image must work both as a web thumbnail and as a larger hero image. Use opposing sides or contrasting halves to imply debate and tension.

Lighting/mood: high-contrast cinematic lighting with electric cyan or blue digital glow balanced by warm amber, magenta, moonlight, or practical light accents where appropriate. Mood should be thoughtful, analytical, high-stakes, and intellectually serious.

Color palette: deep charcoal and near-black background values, electric cyan/blue agent glow, restrained warm accent lighting, plus one topic-specific accent color if useful. Avoid a flat single-color palette.

Materials/textures: glassy holograms, fine wireframe geometry, code-like interface light, polished metal, screens, paper evidence, lab equipment, architecture diagrams, or other concrete details that fit the debate topic.

Text: no text.

Constraints: no readable text, no title lettering, no captions, no brand logos, no company logos, no real person likeness unless explicitly requested, no watermark, no distorted typography. Do not make it look like a generic stock image. Do not use cartoon styling. Do not make the agents cute, mascot-like, or toy-like.
```

#### Cover checklist (verify before finishing)

- The topic is recognizable from the image without embedded text.
- It visually reads as an AI-agent debate, with two or three abstract debaters.
- There is a strong central metaphor tied to the topic.
- No readable text, logo, watermark, or malformed lettering.
- Wide 16:9 landscape; saved exactly as `<Category>/<topic-slug>/cover-image.png`.

Show the operator the cover for approval. If a cover generation fails or no
image tool is available, still finish the markdown publish and tell the
operator the cover is pending — a missing cover must not block publishing.

### 5. Commit + push (automatic, after the cover passes the checklist)

Once the cover is in the folder and passes the checklist, re-run the publish
with `--push` — the markdown re-write is an idempotent refresh, and the git
step commits the whole debate (bundle + cover) in one commit and pushes it:

```powershell
.\.venv\Scripts\python.exe scripts\publish_debate.py --cid <N> --category "<Bucket>" --push
```

Why this is safe in a repo other processes also push to (the automation fleet
races the same branch all day):

- it stages **only the debate folder** — unrelated local WIP in the library
  repo is never swept into the commit and never blocks it;
- it runs `git pull --rebase --autostash` before pushing, so a remote that
  moved is replayed cleanly and unrelated dirty files are shelved/restored;
- new debate folders are uniquely named, so real conflicts are near-impossible;
  if a rebase ever does conflict, the script **aborts the rebase, keeps the
  commit local, and prints the manual fix** — it never force-pushes;
- a push race (remote moved between pull and push) gets one automatic retry.

If the script exits with a conflict/push error, surface its message to the
operator verbatim — the commit is safe locally and nothing needs re-publishing.

### 6. Wrap up

Report: the target folder, the files written, the cover, and the pushed commit.
Downstream consumers (library site build, debate-chat-theater `build.mjs`) pick
the new debate up on their next build/deploy of the library site — merging the
library branch to `main` is what puts it live; no deploy of Agent-Chat is
involved.
