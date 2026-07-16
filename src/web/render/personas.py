"""The /personas management console page."""

from __future__ import annotations

import html
import json
from typing import Any

from orchestrator import personas as personas_registry

from web.assets import _PERSONAS_CSS
from web.render.common import _initials, _layout, _pm_svg


def _group_select(current: str, groups: list[str], cls: str) -> str:
    """Render a <select> of existing group folders + a "new group" escape hatch.

    ``current`` is pre-selected (and added as an option if it isn't already in
    ``groups``, e.g. the default group on a fresh DB). A trailing ``__new__``
    option reveals a sibling text input client-side so a brand-new group can be
    created inline at persona-creation/import time (groups are just distinct
    ``"group"`` values, so a group materializes when its first persona lands)."""
    opts: list[str] = []
    seen = False
    for g in groups:
        sel = " selected" if g == current else ""
        seen = seen or g == current
        opts.append(f'<option value="{html.escape(g, quote=True)}"{sel}>{html.escape(g)}</option>')
    if current and not seen:
        opts.insert(0, f'<option value="{html.escape(current, quote=True)}" selected>{html.escape(current)}</option>')
    opts.append('<option value="__new__">+ Create new group…</option>')
    return f'<select class="{cls}">{"".join(opts)}</select>'

def _pm_glabel(g: str) -> str:
    """Display label for a group folder name (hyphens/underscores → spaces)."""
    return g.replace("-", " ").replace("_", " ")


def _render_personas_page() -> str:
    crumbs = '<strong>Personas</strong>'
    if not personas_registry.root_exists():
        body = (
            '<div class="pm-unavail">Persona storage is <strong>unavailable</strong> &mdash; '
            'the database can\'t be reached right now. Try again shortly.</div>'
        )
        return _layout("Personas", crumbs, body, head_extras=_PERSONAS_CSS,
                       active="personas")

    groups = personas_registry.discover_groups()
    default_group = personas_registry.DEFAULT_DEBATER_GROUP
    active_group = groups[0] if groups else default_group

    # Build, in one pass: the per-group row markup, the flat data blob the
    # detail pane reads bodies from, and the group counts for the rail.
    data_personas: list[dict[str, Any]] = []
    rows_by_group: list[str] = []
    group_counts: dict[str, int] = {}
    for g in groups:
        cards = personas_registry.list_personas(g)
        group_counts[g] = len(cards)
        gq = html.escape(g, quote=True)
        row_html: list[str] = []
        for p in cards:
            data_personas.append({
                "group": g, "slug": p.slug, "name": p.name,
                "tags": list(p.tags), "body": p.body,
            })
            sq = html.escape(p.slug, quote=True)
            chips = "".join(
                f'<span class="pm-chip-sm">{html.escape(t)}</span>' for t in p.tags[:4]
            )
            search_blob = html.escape(
                " ".join([p.name, p.slug, " ".join(p.tags)]).lower(), quote=True
            )
            row_html.append(
                f'<div class="pm-row" data-group="{gq}" data-slug="{sq}" '
                f'data-search="{search_blob}">'
                f'<input type="checkbox" class="pm-sel" data-group="{gq}" data-slug="{sq}" '
                f'aria-label="Select {html.escape(p.name, quote=True)}">'
                f'<span class="pm-av">{html.escape(_initials(p.name))}</span>'
                f'<span class="pm-row-name">{html.escape(p.name)}</span>'
                f'<span class="pm-row-slug mono">{html.escape(p.slug)}</span>'
                f'<span class="pm-row-tags">{chips}</span>'
                f'<span class="pm-row-acts">'
                f'<button type="button" class="pm-iact pm-edit" title="Edit" aria-label="Edit">{_pm_svg("edit")}</button>'
                f'<button type="button" class="pm-iact pm-dup" title="Duplicate" aria-label="Duplicate">{_pm_svg("copy")}</button>'
                f'<button type="button" class="pm-iact pm-del" title="Delete" aria-label="Delete">{_pm_svg("trash")}</button>'
                f'</span></div>'
            )
        hidden = "" if g == active_group else " hidden"
        rows_by_group.append(
            f'<div class="pm-rows" data-group="{gq}"{hidden}>{"".join(row_html)}</div>'
        )

    # ---- Left rail: search + group navigator + new-group ----
    grp_btns = []
    for g in groups:
        act = " active" if g == active_group else ""
        grp_btns.append(
            f'<button type="button" class="pm-grp{act}" data-group="{html.escape(g, quote=True)}">'
            f'{_pm_svg("folder")}'
            f'<span class="pm-grp-name">{html.escape(_pm_glabel(g))}</span>'
            f'<span class="pm-grp-count">{group_counts[g]}</span></button>'
        )
    rail = (
        '<aside class="pm-rail">'
        f'<div class="pm-search">{_pm_svg("search")}'
        '<input type="text" id="pm-search" placeholder="Search personas" autocomplete="off"></div>'
        '<div class="pm-grps"><div class="pm-rail-h">Groups</div>'
        + "".join(grp_btns) +
        '</div>'
        '<div class="pm-rail-foot">'
        '<button type="button" class="btn btn-primary" id="pm-newgrp">+ New group</button>'
        '</div></aside>'
    )

    # ---- Center: persona list ----
    center = (
        '<section class="pm-center">'
        '<header class="pm-chead">'
        f'<h2 class="pm-ctitle" id="pm-ctitle">{html.escape(_pm_glabel(active_group).upper())}</h2>'
        '<div class="pm-ctools">'
        '<select class="pm-sort" id="pm-sort" aria-label="Sort personas">'
        '<option value="az">Name A&ndash;Z</option>'
        '<option value="za">Name Z&ndash;A</option></select>'
        '<button type="button" class="btn btn-primary" id="pm-new">+ New</button>'
        '<button type="button" class="btn" id="pm-import-open">Import</button>'
        '<button type="button" class="btn pm-sel-toggle" id="pm-sel-toggle">Select</button>'
        '</div></header>'
        '<div class="pm-colhead"><span></span><span>Persona</span><span>Slug</span>'
        '<span>Tags</span><span></span></div>'
        '<div class="pm-scroll" id="pm-scroll">'
        + "".join(rows_by_group) +
        '<div class="pm-center-empty" id="pm-center-empty" hidden></div>'
        '</div></section>'
    )

    # ---- Right: detail / edit pane (one shared form, populated client-side) ----
    detail = (
        '<aside class="pm-detail" id="pm-detail">'
        '<div class="pm-detail-empty" id="pm-detail-empty">'
        f'{_pm_svg("doc")}'
        '<p>Select a persona to edit,<br>or create a new one.</p>'
        '<button type="button" class="btn btn-primary" id="pm-new-2">+ New persona</button>'
        '</div>'
        '<form class="pm-dform" id="pm-dform" data-mode="create" data-slug="" data-group="" hidden>'
        '<div class="pm-dhead">'
        '<h2 class="pm-dtitle" id="pm-dtitle">New persona</h2>'
        '<button type="button" class="pm-dclose" id="pm-dclose" aria-label="Close">&#10005;</button>'
        '</div>'
        '<div class="pm-dbody">'
        '<label class="pm-l">Display name</label>'
        '<input type="text" class="pm-d-name" id="pm-d-name" placeholder="e.g. Crypto Chad">'
        '<label class="pm-l">Group</label>'
        + _group_select(active_group, groups, "pm-d-group-select")
        + '<input type="text" class="pm-d-group-new" placeholder="New group name" '
        'style="display:none;margin-top:8px">'
        '<label class="pm-l">Tags</label>'
        '<div class="pm-tagbox" id="pm-d-tags"><input class="pm-f-tags-input" type="text" '
        'placeholder="add a tag&hellip;"></div>'
        '<label class="pm-l">System prompt / bio</label>'
        '<div class="pm-tabs">'
        '<button type="button" class="pm-tab on" data-tab="edit">Edit</button>'
        '<button type="button" class="pm-tab" data-tab="preview">Preview</button></div>'
        '<textarea class="pm-d-body" id="pm-d-body" placeholder="Markdown personality card&hellip;"></textarea>'
        '<div class="pm-preview" id="pm-d-preview" hidden></div>'
        '</div>'
        '<div class="pm-detail-foot">'
        '<button type="button" class="btn btn-danger pm-d-delete" id="pm-d-delete">Delete</button>'
        '<button type="submit" class="btn btn-primary pm-d-save">Save</button>'
        '<span class="pm-msg pm-d-msg" id="pm-d-msg"></span>'
        '</div></form></aside>'
    )

    # ---- Import modal ----
    import_modal = (
        '<div class="pm-modal" id="pm-modal">'
        '<div class="pm-modal-card">'
        '<h3>Import personas</h3>'
        '<p class="pm-hint">Select one or more <code>.md</code> cards (seed-card '
        'frontmatter) and/or a <code>.zip</code> archive. The filename becomes the '
        'slug; title, tags, and category come from the frontmatter.</p>'
        '<label class="pm-l">Target group</label>'
        + _group_select(active_group, groups, "pm-imp-group-select")
        + '<input class="pm-imp-group-new" type="text" placeholder="New group name" '
        'style="display:none;margin-top:8px">'
        '<label class="pm-l">Markdown files or .zip</label>'
        '<input class="pm-imp-files" type="file" '
        'accept=".md,.markdown,.zip,text/markdown,application/zip" multiple>'
        '<label class="pm-check" style="margin-top:12px"><input type="checkbox" '
        'class="pm-imp-overwrite"> Overwrite existing personas with the same slug</label>'
        '<div class="pm-detail-foot" style="border-top:0;padding:14px 0 0">'
        '<button type="button" class="btn pm-imp-cancel" style="margin-left:auto">Cancel</button>'
        '<button type="button" class="btn btn-primary pm-imp-btn">Import</button>'
        '<span class="pm-msg pm-imp-msg"></span>'
        '</div></div></div>'
    )

    # ---- Floating bulk-delete action bar ----
    select_actions = (
        '<div class="pm-selactions" hidden>'
        '<span class="pm-sel-count">0 selected</span>'
        '<button type="button" class="btn pm-sel-all">Select all</button>'
        '<button type="button" class="btn pm-sel-clear">Clear</button>'
        '<button type="button" class="btn btn-danger pm-sel-del" disabled>Delete selected</button>'
        '<button type="button" class="btn pm-sel-cancel">Cancel</button>'
        '<span class="pm-msg pm-sel-msg"></span>'
        '</div>'
    )

    # Persona bodies live in a JSON island the detail pane reads on selection
    # (lighter than embedding every body in a textarea per row). Escape "<" so a
    # body containing "</script>" can't break out of the data island.
    data_blob = (
        '<script type="application/json" id="pm-data">'
        + json.dumps({"active": active_group, "personas": data_personas}).replace("<", "\\u003c")
        + '</script>'
    )

    script = """
    <script>
    (function() {
      const root = document.querySelector('.pm3');
      if (!root) return;
      const DATA = JSON.parse(document.getElementById('pm-data').textContent);
      const SEP = '\\u0000';
      const byKey = {};
      DATA.personas.forEach(p => { byKey[p.group + SEP + p.slug] = p; });
      let activeGroup = DATA.active || '';

      const $ = s => root.querySelector(s);
      const $$ = s => [...root.querySelectorAll(s)];
      async function postJSON(url, data) {
        const res = await fetch(url, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(data)
        });
        let body = {};
        try { body = await res.json(); } catch (e) {}
        return { ok: res.ok && body.ok !== false, body };
      }

      // --- Tag chip input -----------------------------------------------------
      function chips(box) { return [...box.querySelectorAll('.pm-chip')]; }
      function tagList(box) { return chips(box).map(c => c.dataset.tag); }
      function clearChips(box) { chips(box).forEach(c => c.remove()); }
      function addChip(box, text) {
        text = (text || '').trim().replace(/,+$/, '').trim();
        if (!text) return;
        if (tagList(box).map(t => t.toLowerCase()).includes(text.toLowerCase())) return;
        const input = box.querySelector('.pm-f-tags-input');
        const chip = document.createElement('span');
        chip.className = 'pm-chip'; chip.dataset.tag = text;
        chip.append(document.createTextNode(text));
        const x = document.createElement('button');
        x.type = 'button'; x.className = 'pm-chip-x'; x.textContent = '\\u00d7';
        x.addEventListener('click', e => { e.stopPropagation(); chip.remove(); });
        chip.appendChild(x);
        box.insertBefore(chip, input);
      }
      function initTagbox(box) {
        const input = box.querySelector('.pm-f-tags-input');
        box.addEventListener('click', () => input.focus());
        input.addEventListener('keydown', e => {
          if (e.key === ',' || e.key === 'Enter') {
            e.preventDefault(); addChip(box, input.value); input.value = '';
          } else if (e.key === 'Backspace' && !input.value) {
            const cs = chips(box); if (cs.length) cs[cs.length - 1].remove();
          }
        });
        input.addEventListener('input', () => {
          if (input.value.includes(',')) {
            const parts = input.value.split(','); input.value = parts.pop();
            parts.forEach(p => addChip(box, p));
          }
        });
        input.addEventListener('blur', () => { addChip(box, input.value); input.value = ''; });
      }
      $$('.pm-tagbox').forEach(initTagbox);

      // --- group <select> "create new" reveal --------------------------------
      function wireGroupSelect(sel, newInput) {
        if (!sel || !newInput) return;
        sel.addEventListener('change', () => {
          const isNew = sel.value === '__new__';
          newInput.style.display = isNew ? 'block' : 'none';
          if (isNew) newInput.focus();
        });
      }
      function groupValue(sel, newInput) {
        return sel.value === '__new__' ? (newInput.value || '').trim() : sel.value;
      }

      // --- minimal, XSS-safe markdown preview (escape first, then format) ----
      function mdToHtml(src) {
        const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const inline = t => esc(t)
          .replace(/`([^`]+)`/g, '<code>$1</code>')
          .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
          .replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
        const lines = (src || '').split('\\n');
        let html = '', inUl = false, inCode = false, code = '';
        for (const ln of lines) {
          if (ln.trim().startsWith('```')) {
            if (inCode) { html += '<pre>' + esc(code) + '</pre>'; code = ''; inCode = false; }
            else { if (inUl) { html += '</ul>'; inUl = false; } inCode = true; }
            continue;
          }
          if (inCode) { code += ln + '\\n'; continue; }
          const h = ln.match(/^(#{1,6})\\s+(.*)$/);
          if (h) { if (inUl) { html += '</ul>'; inUl = false; }
                   const lv = h[1].length; html += '<h' + lv + '>' + inline(h[2]) + '</h' + lv + '>'; continue; }
          const li = ln.match(/^\\s*[-*]\\s+(.*)$/);
          if (li) { if (!inUl) { html += '<ul>'; inUl = true; } html += '<li>' + inline(li[1]) + '</li>'; continue; }
          if (ln.trim() === '') { if (inUl) { html += '</ul>'; inUl = false; } continue; }
          if (inUl) { html += '</ul>'; inUl = false; }
          html += '<p>' + inline(ln) + '</p>';
        }
        if (inUl) html += '</ul>';
        if (inCode) html += '<pre>' + esc(code) + '</pre>';
        return html;
      }

      // --- list: group switching, search, sort --------------------------------
      const ctitle = $('#pm-ctitle');
      const centerEmpty = $('#pm-center-empty');
      const searchInput = $('#pm-search');
      const sortSel = $('#pm-sort');
      function glabel(g) { return g.replace(/[-_]/g, ' '); }
      function activeRowsEl() { return $$('.pm-rows').find(el => el.dataset.group === activeGroup) || null; }
      function rowName(r) { const p = byKey[r.dataset.group + SEP + r.dataset.slug]; return (p && p.name || '').toLowerCase(); }

      function applyFilterSort() {
        const rowsEl = activeRowsEl();
        const q = (searchInput.value || '').trim().toLowerCase();
        let visible = 0;
        if (rowsEl) {
          const rows = [...rowsEl.querySelectorAll('.pm-row')];
          rows.forEach(r => {
            const hit = !q || (r.dataset.search || '').includes(q);
            r.style.display = hit ? '' : 'none'; if (hit) visible++;
          });
          const dir = sortSel.value;
          rows.sort((a, b) => dir === 'za' ? rowName(b).localeCompare(rowName(a)) : rowName(a).localeCompare(rowName(b)));
          rows.forEach(r => rowsEl.appendChild(r));
        }
        centerEmpty.hidden = visible !== 0;
        centerEmpty.innerHTML = q
          ? 'No personas match &ldquo;' + q.replace(/</g, '&lt;') + '&rdquo;.'
          : 'No personas in this group yet. Use <code>+ New</code> to add one.';
      }
      function setActiveGroup(g) {
        activeGroup = g;
        $$('.pm-grp').forEach(b => b.classList.toggle('active', b.dataset.group === g));
        $$('.pm-rows').forEach(el => { el.hidden = el.dataset.group !== g; });
        ctitle.textContent = glabel(g).toUpperCase();
        applyFilterSort();
      }
      $$('.pm-grp').forEach(b => b.addEventListener('click', () => setActiveGroup(b.dataset.group)));
      searchInput.addEventListener('input', applyFilterSort);
      sortSel.addEventListener('change', applyFilterSort);

      // --- detail / edit pane -------------------------------------------------
      const detail = $('#pm-detail');
      const dform = $('#pm-dform');
      const dempty = $('#pm-detail-empty');
      const dTitle = $('#pm-dtitle');
      const dName = $('#pm-d-name');
      const dBody = $('#pm-d-body');
      const dPrev = $('#pm-d-preview');
      const dTags = $('#pm-d-tags');
      const dSel = dform.querySelector('.pm-d-group-select');
      const dNew = dform.querySelector('.pm-d-group-new');
      const dDelete = $('#pm-d-delete');
      const dMsg = $('#pm-d-msg');
      const dSave = dform.querySelector('.pm-d-save');
      wireGroupSelect(dSel, dNew);

      function isMobile() { return window.matchMedia('(max-width:900px)').matches; }
      function showForm() { dempty.hidden = true; dform.hidden = false; if (isMobile()) detail.classList.add('open'); }
      function resetTabs() {
        dform.querySelectorAll('.pm-tab').forEach(t => t.classList.toggle('on', t.dataset.tab === 'edit'));
        dBody.hidden = false; dPrev.hidden = true;
      }
      function setGroupSelect(g) {
        dNew.style.display = 'none'; dNew.value = '';
        if (g && ![...dSel.options].some(o => o.value === g)) {
          dSel.insertBefore(new Option(g, g), dSel.options[dSel.options.length - 1]);
        }
        if (g) dSel.value = g;
      }
      function fillForm(p) {
        clearChips(dTags); (p.tags || []).forEach(t => addChip(dTags, t));
        dName.value = p.name || ''; dBody.value = p.body || '';
        setGroupSelect(p.group || activeGroup);
        resetTabs(); dMsg.textContent = ''; dMsg.className = 'pm-msg pm-d-msg';
      }
      function selectPersona(group, slug) {
        const p = byKey[group + SEP + slug]; if (!p) return;
        dform.dataset.mode = 'update'; dform.dataset.slug = slug; dform.dataset.group = group;
        dTitle.textContent = p.name; dDelete.style.display = '';
        fillForm(p); showForm();
        $$('.pm-row').forEach(r => r.classList.toggle('active', r.dataset.group === group && r.dataset.slug === slug));
      }
      function createMode(prefill) {
        prefill = prefill || {};
        dform.dataset.mode = 'create'; dform.dataset.slug = ''; dform.dataset.group = '';
        dTitle.textContent = 'New persona'; dDelete.style.display = 'none';
        fillForm({ name: prefill.name || '', body: prefill.body || '', tags: prefill.tags || [], group: prefill.group || activeGroup });
        showForm(); $$('.pm-row').forEach(r => r.classList.remove('active')); dName.focus();
      }
      async function rowDelete(group, slug) {
        if (!confirm('Delete persona "' + slug + '"? This removes it everywhere (synced).')) return;
        const { ok, body } = await postJSON('/api/personas/' + encodeURIComponent(slug) + '/delete', {});
        if (ok) location.reload();
        else alert('Delete failed: ' + ((body && body.error) || 'unknown'));
      }

      dform.querySelectorAll('.pm-tab').forEach(t => t.addEventListener('click', () => {
        const isEdit = t.dataset.tab === 'edit';
        dform.querySelectorAll('.pm-tab').forEach(x => x.classList.toggle('on', x === t));
        dBody.hidden = !isEdit; dPrev.hidden = isEdit;
        if (!isEdit) dPrev.innerHTML = mdToHtml(dBody.value);
      }));
      $('#pm-dclose').addEventListener('click', () => detail.classList.remove('open'));
      $('#pm-new').addEventListener('click', () => createMode());
      $('#pm-new-2').addEventListener('click', () => createMode());
      $('#pm-newgrp').addEventListener('click', () => { createMode(); dSel.value = '__new__'; dNew.style.display = 'block'; dNew.focus(); });
      dDelete.addEventListener('click', () => { if (dform.dataset.slug) rowDelete(dform.dataset.group, dform.dataset.slug); });

      // Row click delegation: select / edit / duplicate / delete / bulk-toggle.
      $('#pm-scroll').addEventListener('click', e => {
        if (e.target.closest('.pm-sel')) return;
        const delBtn = e.target.closest('.pm-del');
        if (delBtn) { const r = delBtn.closest('.pm-row'); rowDelete(r.dataset.group, r.dataset.slug); return; }
        const dupBtn = e.target.closest('.pm-dup');
        if (dupBtn) {
          const r = dupBtn.closest('.pm-row'); const p = byKey[r.dataset.group + SEP + r.dataset.slug];
          if (p) createMode({ name: p.name + ' copy', tags: p.tags, body: p.body, group: p.group });
          return;
        }
        const row = e.target.closest('.pm-row'); if (!row) return;
        if (root.classList.contains('pm-selecting')) {
          const cb = row.querySelector('.pm-sel'); cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); return;
        }
        selectPersona(row.dataset.group, row.dataset.slug);
      });

      dform.addEventListener('submit', async ev => {
        ev.preventDefault();
        const tagInput = dTags.querySelector('.pm-f-tags-input');
        addChip(dTags, tagInput.value); tagInput.value = '';
        const group = groupValue(dSel, dNew);
        if (dSel.value === '__new__' && !group) { dMsg.className = 'pm-msg pm-d-msg err'; dMsg.textContent = 'Enter a name for the new group'; return; }
        const name = dName.value.trim();
        if (!name) { dMsg.className = 'pm-msg pm-d-msg err'; dMsg.textContent = 'Display name is required'; return; }
        if (!dBody.value.trim()) { dMsg.className = 'pm-msg pm-d-msg err'; dMsg.textContent = 'Body is required'; return; }
        const payload = { name: name, group: group, tags: tagList(dTags), body: dBody.value };
        const url = dform.dataset.mode === 'create'
          ? '/api/personas' : '/api/personas/' + encodeURIComponent(dform.dataset.slug);
        dMsg.className = 'pm-msg pm-d-msg'; dMsg.textContent = 'Saving\\u2026'; dSave.disabled = true;
        const { ok, body } = await postJSON(url, payload);
        dSave.disabled = false;
        if (ok) { dMsg.className = 'pm-msg pm-d-msg ok'; dMsg.textContent = 'Saved'; location.reload(); }
        else { dMsg.className = 'pm-msg pm-d-msg err'; dMsg.textContent = (body && body.error) || 'Failed'; }
      });

      // --- import modal -------------------------------------------------------
      const modal = $('#pm-modal');
      const impSel = modal.querySelector('.pm-imp-group-select');
      const impNew = modal.querySelector('.pm-imp-group-new');
      const impBtn = modal.querySelector('.pm-imp-btn');
      wireGroupSelect(impSel, impNew);
      $('#pm-import-open').addEventListener('click', () => modal.classList.add('open'));
      modal.querySelector('.pm-imp-cancel').addEventListener('click', () => modal.classList.remove('open'));
      modal.addEventListener('click', e => { if (e.target === modal) modal.classList.remove('open'); });
      impBtn.addEventListener('click', async () => {
        const msg = modal.querySelector('.pm-imp-msg');
        const files = [...modal.querySelector('.pm-imp-files').files];
        if (!files.length) { msg.className = 'pm-msg pm-imp-msg err'; msg.textContent = 'Choose at least one .md or .zip file'; return; }
        const group = groupValue(impSel, impNew);
        if (impSel.value === '__new__' && !group) { msg.className = 'pm-msg pm-imp-msg err'; msg.textContent = 'Enter a name for the new group'; return; }
        msg.className = 'pm-msg pm-imp-msg'; msg.textContent = 'Reading files\\u2026';
        const bytesToBase64 = (bytes) => {
          let bin = ''; const chunk = 0x8000;
          for (let i = 0; i < bytes.length; i += chunk) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
          return btoa(bin);
        };
        const units = [];
        for (const f of files) {
          if (/\\.zip$/i.test(f.name)) {
            const buf = await f.arrayBuffer();
            units.push({ kind: 'zip', size: buf.byteLength, item: { filename: f.name, b64: bytesToBase64(new Uint8Array(buf)) } });
          } else {
            const text = await f.text();
            units.push({ kind: 'file', size: text.length, item: { filename: f.name, text } });
          }
        }
        // Size-bounded batches (~3 MB raw) so a big selection doesn't OOM the small hosted VM.
        const BATCH_BYTES = 3 * 1024 * 1024;
        const batches = []; let cur = [], curSize = 0;
        for (const u of units) {
          if (cur.length && curSize + u.size > BATCH_BYTES) { batches.push(cur); cur = []; curSize = 0; }
          cur.push(u); curSize += u.size;
        }
        if (cur.length) batches.push(cur);
        const overwrite = modal.querySelector('.pm-imp-overwrite').checked;
        impBtn.disabled = true;
        let totImported = 0, totSkipped = 0, allErrors = [], failed = '';
        for (let i = 0; i < batches.length; i++) {
          msg.className = 'pm-msg pm-imp-msg';
          msg.textContent = batches.length > 1 ? 'Importing\\u2026 batch ' + (i + 1) + ' of ' + batches.length : 'Importing\\u2026';
          const p = { group: group, overwrite: overwrite, files: [], zips: [] };
          for (const u of batches[i]) (u.kind === 'zip' ? p.zips : p.files).push(u.item);
          const { ok, body } = await postJSON('/api/personas/import', p);
          if (ok) {
            totImported += body.imported || 0; totSkipped += body.skipped || 0;
            if (body.errors && body.errors.length) allErrors = allErrors.concat(body.errors);
          } else { failed = (body && body.error) || 'Import failed (batch ' + (i + 1) + ')'; break; }
        }
        impBtn.disabled = false;
        if (!failed) {
          msg.className = 'pm-msg pm-imp-msg ok';
          let txt = 'Imported ' + totImported + ', skipped ' + totSkipped;
          if (allErrors.length) txt += ' \\u2014 ' + allErrors[0];
          msg.textContent = txt;
          setTimeout(() => location.reload(), totImported ? 900 : 2500);
        } else {
          msg.className = 'pm-msg pm-imp-msg err';
          msg.textContent = failed + (totImported ? ' (imported ' + totImported + ' before this)' : '');
        }
      });

      // --- bulk-delete (select mode) -----------------------------------------
      const selToggle = $('#pm-sel-toggle');
      const selBar = $('.pm-selactions');
      if (selToggle && selBar) {
        const boxes = () => $$('.pm-sel');
        const selCount = selBar.querySelector('.pm-sel-count');
        const selDel = selBar.querySelector('.pm-sel-del');
        const selMsg = selBar.querySelector('.pm-sel-msg');
        function updateCount() { const n = boxes().filter(b => b.checked).length; selCount.textContent = n + ' selected'; selDel.disabled = n === 0; }
        function setSelecting(on) {
          root.classList.toggle('pm-selecting', on);
          selBar.hidden = !on;
          selToggle.textContent = on ? 'Done' : 'Select';
          if (!on) boxes().forEach(b => { b.checked = false; });
          selMsg.textContent = ''; updateCount();
        }
        selToggle.addEventListener('click', () => setSelecting(selBar.hidden));
        boxes().forEach(b => b.addEventListener('change', updateCount));
        selBar.querySelector('.pm-sel-all').addEventListener('click', () => {
          boxes().forEach(b => { const r = b.closest('.pm-row'); if (!b.closest('.pm-rows').hidden && r.style.display !== 'none') b.checked = true; });
          updateCount();
        });
        selBar.querySelector('.pm-sel-clear').addEventListener('click', () => { boxes().forEach(b => { b.checked = false; }); updateCount(); });
        selBar.querySelector('.pm-sel-cancel').addEventListener('click', () => setSelecting(false));
        selDel.addEventListener('click', async () => {
          const chosen = boxes().filter(b => b.checked);
          if (!chosen.length) return;
          if (!confirm('Delete ' + chosen.length + ' persona' + (chosen.length === 1 ? '' : 's') + '? This removes them everywhere (synced).')) return;
          const items = chosen.map(b => ({ group: b.dataset.group, slug: b.dataset.slug }));
          selDel.disabled = true;
          selMsg.className = 'pm-msg pm-sel-msg'; selMsg.textContent = 'Deleting\\u2026';
          const { ok, body } = await postJSON('/api/personas/bulk-delete', { items });
          if (ok) {
            selMsg.className = 'pm-msg pm-sel-msg ok';
            let txt = 'Deleted ' + body.deleted;
            if (body.not_found) txt += ', ' + body.not_found + ' not found';
            if (body.errors && body.errors.length) txt += ' \\u2014 ' + body.errors[0];
            selMsg.textContent = txt;
            setTimeout(() => location.reload(), 700);
          } else {
            selMsg.className = 'pm-msg pm-sel-msg err';
            selMsg.textContent = (body && body.error) || 'Delete failed';
            selDel.disabled = false;
          }
        });
      }

      // Deep-link target for the command palette, which links personas as
      // /personas?group=<group>&q=<name>: select the group, then prefill the
      // search so the card the operator picked is the one row on screen.
      // Runs before the initial applyFilterSort() so we filter exactly once.
      (() => {
        const qs = new URLSearchParams(location.search);
        const g = qs.get('group');
        if (g && $$('.pm-grp').some(b => b.dataset.group === g)) setActiveGroup(g);
        const q = qs.get('q');
        if (q) searchInput.value = q;
      })();

      applyFilterSort();
    })();
    </script>"""

    body = (
        '<div class="pm3">'
        + rail + center + detail + import_modal + select_actions + data_blob + script
        + '</div>'
    )
    return _layout("Personas", crumbs, body, head_extras=_PERSONAS_CSS,
                   active="personas")
