import {
  ACTIVE_PLAYERS, PREVIEW8, STOCK16, deepFreeze, fitRoster, openRom, previewRoster,
  readRosterFile, rosterJson, sameTeams, skillStars, writeRom,
} from './rom.js';

const RATING_LABELS = ['Batting', 'Running', 'Pitching', 'Defense'];
const VIEWS = new Map([
  [PREVIEW8, { label: 'Preview 8', chip: 'Preview 8', roster: './roster32.json', meta: './teams32.json', stem: 'preview8' }],
  [STOCK16, { label: '16-team US', chip: '16-team', roster: './roster.json', stem: 'us16' }],
]);

/**
 * @typedef {{bytes: Uint8Array, name: string, sha256: string, exact: boolean}} LoadedRom
 * @typedef {{profile: object, baseline: object[], rom: LoadedRom | null}} Session
 *
 * `session.baseline` is the frozen roster the session started from: the ROM as
 * read, or the bundled preview. `teams` is the draft, dirty whenever it differs
 * from the baseline. Imports replace only the draft, so Revert always returns to
 * the baseline. `revision` counts draft changes, which lets a load that finishes
 * later notice edits made while it ran.
 */
const state = { session: null, teams: [], selected: 0, revision: 0 };

// Each load or import takes a ticket. Only the newest ticket may change the
// session or report an error, so a slow read, hash or fetch can't land on top
// of a later choice.
let ticket = 0;
let answerPrompt = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));
const pad2 = (n) => String(n).padStart(2, '0');
const stem = (name) => name.replace(/\.(nes|json)$/i, '');
const isDirty = () => state.session !== null && !sameTeams(state.teams, state.session.baseline);
const isStale = (t) => t !== ticket;
const label = (profile) => VIEWS.get(profile).label;
const textField = (key) => state.session?.profile.text.find((f) => f.key === key && f.editable);

/** Uppercase and keep only glyphs the game font has. */
const clean = (text, max) => text.toUpperCase().replace(/[^A-Z0-9 ]/g, '').slice(0, max);

function nextTicket() {
  ticket += 1;
  settlePrompt(false);
  return ticket;
}

function askReplace(action) {
  settlePrompt(false);
  $('replaceText').textContent =
    `${action} replaces the edits you haven't exported. Export JSON first if you want to keep them.`;
  $('replaceDialog').showModal();
  return new Promise((resolve) => { answerPrompt = resolve; });
}

function settlePrompt(answer) {
  const resolve = answerPrompt;
  if (!resolve) return;
  answerPrompt = null;
  $('replaceDialog').close();
  resolve(answer);
}

async function mayReplace(t, draft, action, sameSession = false) {
  while (isDirty() && !(sameSession && sameTeams(draft, state.teams))) {
    if (isStale(t)) return false;
    const revision = state.revision;
    if (!(await askReplace(action)) || isStale(t)) return false;
    if (state.revision === revision) return true;
  }
  return !isStale(t);
}

function startSession(session, draft) {
  const sameLayout = state.session?.profile === session.profile;
  state.session = session;
  state.teams = structuredClone(draft);
  state.selected = sameLayout ? state.selected : 0;
  state.revision += 1;
  renderAll();
}

function replaceDraft(draft) {
  state.teams = structuredClone(draft);
  state.revision += 1;
  renderAll();
}

function changed({ list = false } = {}) {
  state.revision += 1;
  if (list) renderTeamList();
  renderChrome();
}

const previews = new Map();

async function previewTeams(profile) {
  if (!previews.has(profile)) {
    const files = VIEWS.get(profile);
    const [doc, meta] = await Promise.all([fetchJson(files.roster), files.meta ? fetchJson(files.meta) : null]);
    previews.set(profile, deepFreeze(previewRoster(profile, doc, meta)));
  }
  return previews.get(profile);
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`The server answered ${res.status} for ${url.replace('./', '')}.`);
  return res.json();
}

async function showPreview(profile) {
  const t = nextTicket();
  try {
    const teams = await previewTeams(profile);
    if (isStale(t)) return;
    if (!(await mayReplace(t, teams, `Switching to the ${label(profile)} roster`))) return;
    startSession({ profile, baseline: teams, rom: null }, teams);
    showBanner(profile === PREVIEW8
      ? 'This is the Preview 8 roster. To export a ROM, use Get Preview 8, then Open ROM. ' +
        'The file is read in this browser and never uploaded.'
      : 'This is the original 16-team roster. Open your copy of the US ROM to export an edited ROM. ' +
        'The file is read in this browser and never uploaded.', 'info');
  } catch (err) {
    if (!isStale(t)) {
      showBanner(`Couldn't load the ${label(profile)} roster. ${err.message}`, 'warn');
      if (!state.session) $('statusChip').textContent = 'NO ROSTER';
    }
  }
}

async function openRomFile(file) {
  const t = nextTicket();
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (isStale(t)) return;
    const rom = await openRom(bytes);
    if (isStale(t)) return;
    if (!(await mayReplace(t, rom.teams, `Opening ${file.name}`))) return;
    const baseline = deepFreeze(rom.teams);
    startSession({ profile: rom.profile, baseline, rom: { bytes, name: file.name, sha256: rom.sha256, exact: rom.exact } }, baseline);
    showBanner(rom.exact
      ? `Opened ${file.name}, the original ${label(rom.profile)} ROM. Edits stay in this browser until you export.`
      : `Opened ${file.name}, an edited copy of the ${label(rom.profile)} ROM. ` +
        "It matches the original everywhere Roster Lab doesn't edit.",
    'ok', { autoHide: true });
  } catch (err) {
    if (!isStale(t)) showBanner(`Couldn't open ${file.name}. ${err.message}`, 'warn');
  }
}

async function importJsonFile(file) {
  const t = nextTicket();
  try {
    const text = await file.text();
    if (isStale(t)) return;
    let doc;
    try {
      doc = JSON.parse(text);
    } catch {
      throw new Error('The file isn’t valid JSON.');
    }
    const read = readRosterFile(doc);
    const current = state.session;
    if (current?.rom && read.profile !== current.profile) {
      throw new Error(`It is a ${label(read.profile)} roster, but the open ROM is ${label(current.profile)}.`);
    }
    const session = current?.profile === read.profile
      ? current
      : { profile: read.profile, baseline: await previewTeams(read.profile), rom: null };
    if (isStale(t)) return;
    const teams = fitRoster(read, session.baseline);
    if (!(await mayReplace(t, teams, `Importing ${file.name}`, session === current))) return;
    if (session === current) replaceDraft(teams);
    else startSession(session, teams);
    const into = session.rom
      ? 'into the open ROM.'
      : `onto the ${label(read.profile)} roster. To export a ROM, open the ROM, then import this file again.`;
    showBanner([`Imported ${file.name} ${into}`, ...read.notices].join(' '), 'ok', { autoHide: !read.notices.length });
  } catch (err) {
    if (!isStale(t)) showBanner(`Couldn't import ${file.name}. ${err.message}`, 'warn');
  }
}

function handleFile(file) {
  if (!file) return;
  const name = file.name.toLowerCase();
  if (name.endsWith('.nes')) return openRomFile(file);
  if (name.endsWith('.json')) return importJsonFile(file);
  toast('Drop a .nes ROM or a roster .json.', 'warn');
}

async function exportRomFile() {
  const { session } = state;
  if (!session?.rom) return;
  const draft = structuredClone(state.teams);
  try {
    const out = await writeRom(session.rom.bytes, session.profile, session.baseline, draft);
    const filename = `${stem(session.rom.name)}-edited.nes`;
    download(filename, new Blob([out], { type: 'application/octet-stream' }));
    toast(sameTeams(draft, session.baseline)
      ? `Saved ${filename}, an unchanged copy of ${session.rom.name}.`
      : `Saved ${filename} with your edits.`);
  } catch (err) {
    showBanner(`Couldn't export the ROM. ${err.message}`, 'warn');
  }
}

function exportJsonFile() {
  const { session } = state;
  if (!session) return;
  const source = session.rom
    ? { name: session.rom.name, sha256: session.rom.sha256 }
    : { name: `${label(session.profile)} roster preview` };
  const doc = rosterJson(session.profile, state.teams, source);
  const filename = `${session.rom ? stem(session.rom.name) : VIEWS.get(session.profile).stem}-roster.json`;
  download(filename, new Blob([`${JSON.stringify(doc, null, 2)}\n`], { type: 'application/json' }));
  toast(`Saved ${filename}.`);
}

function revert() {
  if (!isDirty()) return;
  state.teams = structuredClone(state.session.baseline);
  state.revision += 1;
  renderAll();
  toast(state.session.rom ? `Reverted to ${state.session.rom.name}.` : 'Reverted to the roster preview.');
}

function resetTeam() {
  const base = state.session?.baseline[state.selected];
  if (!base) return;
  state.teams[state.selected] = structuredClone(base);
  state.revision += 1;
  renderAll();
  toast(`Reset team ${state.selected + 1}.`);
}

function renderChrome() {
  const { session } = state;
  const dirty = isDirty();
  const chip = $('statusChip');
  chip.dataset.mode = session?.rom ? 'rom' : 'preview';
  chip.dataset.dirty = String(dirty);
  const source = !session?.rom ? 'ROSTER ONLY' : session.rom.exact ? 'ORIGINAL ROM' : 'EDITED ROM';
  chip.textContent = session
    ? [VIEWS.get(session.profile).chip, source, dirty && 'UNSAVED'].filter(Boolean).join(' · ')
    : 'LOADING';
  chip.title = session?.rom ? session.rom.name : '';
  $('exportRomBtn').disabled = !session?.rom;
  $('exportRomBtn').title = session?.rom ? '' : 'Open a ROM to export one';
  $('exportJsonBtn').disabled = !session;
  $('revertBtn').disabled = !dirty;
}

function renderTeamList() {
  $('teamCount').textContent = String(state.teams.length);
  $('teamList').innerHTML = state.teams.map((t, i) => `
    <button type="button" class="team-card${i === state.selected ? ' active' : ''}" data-team="${i}"
            aria-current="${i === state.selected}">
      <span class="t-num">${pad2(i + 1)}</span>
      <span class="t-main">
        <span class="t-name">${esc(t.name || '—')}</span>
        <span class="bars" aria-hidden="true">${t.ratings.map((v) => `<i style="--v:${v}"></i>`).join('')}</span>
      </span>
    </button>`).join('');
}

function renderRatings(team) {
  $('ratings').innerHTML = RATING_LABELS.map((name, r) => `
    <div class="rating">
      <span class="r-label">${name}</span>
      <div class="r-pips" data-r="${r}">
        ${[1, 2, 3, 4].map((v) => `
          <button type="button" class="rp${team.ratings[r] === v ? ' on' : ''}" data-rating="${v}"
                  aria-label="${name} ${v}" aria-pressed="${team.ratings[r] === v}">${v}</button>`).join('')}
      </div>
    </div>`).join('');
}

const statCell = (field, value, name, p) => `
  <td class="stat">
    <div class="stat-inner">
      <input type="range" min="0" max="15" step="1" value="${value}" data-field="${field}" aria-label="Player ${p + 1} ${name}">
      <output>${value}</output>
    </div>
  </td>`;

function playerRow(player, p) {
  const [, , , stats, speed, skill, pitcher] = player.attrs;
  const stars = skillStars(skill);
  return `
    <tr data-p="${p}">
      <td class="slot">${pad2(p + 1)}${pitcher ? '<i class="pitch-flag" title="Linked to one of the team’s pitcher records">P</i>' : ''}</td>
      <td>
        <input class="name-input" data-field="name" value="${esc(player.name)}"
               maxlength="6" spellcheck="false" autocomplete="off" aria-label="Player ${p + 1} name">
      </td>
      <td>
        <div class="pips">
          ${[1, 2, 3, 4, 5].map((n) => `
            <button type="button" class="pip${n <= stars ? ' on' : ''}" data-skill="${n}"
                    aria-label="Player ${p + 1} skill ${n}" aria-pressed="${n === stars}"></button>`).join('')}
        </div>
      </td>
      ${statCell('bat', stats >> 4, 'batting', p)}
      ${statCell('pit', stats & 0x0f, 'pitching', p)}
      ${statCell('speed', speed & 0x0f, 'speed', p)}
    </tr>`;
}

function storedRow(player, p) {
  const [, , , stats, speed, skill] = player.attrs;
  return `
    <tr>
      <td class="slot">${pad2(p + 1)}</td>
      <td>${esc(player.name || '—')}</td>
      <td>${skillStars(skill)}</td>
      <td>${stats >> 4}</td>
      <td>${stats & 0x0f}</td>
      <td>${speed & 0x0f}</td>
    </tr>`;
}

function renderEditor() {
  const team = state.teams[state.selected];
  $('emptyState').hidden = Boolean(team);
  $('teamPanel').hidden = !team;
  if (!team) return;

  const { profile } = state.session;
  const tags = [team.code, team.region].filter(Boolean).join(' · ');
  $('teamEyebrow').textContent = `Team ${pad2(state.selected + 1)} / ${state.teams.length}${tags ? ` · ${tags}` : ''}`;
  $('teamTitle').textContent = team.name || '—';

  const editable = profile.text.filter((f) => f.editable);
  $('identityEdit').hidden = editable.length === 0;
  $('identityNote').hidden = editable.length > 0;
  $('shortPreview').hidden = team.shortName === undefined;
  for (const f of editable) {
    const input = document.querySelector(`[data-text="${f.key}"]`);
    input.value = team[f.key];
    input.maxLength = f.width(state.selected);
  }
  if (team.shortName !== undefined) {
    $('shortPreview').textContent = team.shortName || '—';
    $('shortLimit').textContent = `${textField('shortName').width(state.selected)} max`;
  }

  renderRatings(team);
  $('rosterHint').textContent = `${ACTIVE_PLAYERS} players · names up to 6 letters or digits`;
  $('playerBody').innerHTML = team.players.slice(0, ACTIVE_PLAYERS).map(playerRow).join('');
  const unused = team.players.slice(ACTIVE_PLAYERS);
  $('storedBox').hidden = unused.length === 0;
  $('storedCount').textContent = `${unused.length} players`;
  $('storedBody').innerHTML = unused.map((player, i) => storedRow(player, ACTIVE_PLAYERS + i)).join('');
}

function renderAll() {
  renderTeamList();
  renderEditor();
  renderChrome();
}

let bannerTimer = null;
function showBanner(text, kind = 'info', { autoHide = false } = {}) {
  const el = $('banner');
  el.textContent = text;
  el.dataset.kind = kind;
  el.hidden = false;
  clearTimeout(bannerTimer);
  if (autoHide) bannerTimer = setTimeout(() => { el.hidden = true; }, 9000);
}

function toast(message, kind = 'info') {
  const el = document.createElement('div');
  el.className = 'toast';
  el.dataset.kind = kind;
  el.textContent = message;
  $('toasts').appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .2s ease, transform .2s ease';
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    setTimeout(() => el.remove(), 220);
  }, kind === 'error' ? 6000 : 3600);
}

function download(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function onEditorInput(e) {
  const team = state.teams[state.selected];
  const el = e.target;
  if (!team || !el.dataset) return;

  const field = el.dataset.text && textField(el.dataset.text);
  if (field) {
    const v = clean(el.value, field.width(state.selected));
    if (el.value !== v) el.value = v;
    team[field.key] = v.trimEnd();
    if (field.key === 'name') $('teamTitle').textContent = team.name || '—';
    if (field.key === 'shortName') $('shortPreview').textContent = team.shortName || '—';
    changed({ list: field.key === 'name' });
    return;
  }

  const row = el.closest('tr[data-p]');
  const p = Number(row?.dataset.p);
  if (!row || !(p < ACTIVE_PLAYERS)) return;
  const player = team.players[p];

  if (el.dataset.field === 'name') {
    const v = clean(el.value, 6);
    if (el.value !== v) el.value = v;
    player.name = v.trimEnd();
    changed();
    return;
  }

  if (el.type === 'range') {
    const v = Number(el.value);
    const { attrs } = player;
    if (el.dataset.field === 'bat') attrs[3] = (v << 4) | (attrs[3] & 0x0f);
    if (el.dataset.field === 'pit') attrs[3] = (attrs[3] & 0xf0) | v;
    if (el.dataset.field === 'speed') attrs[4] = (attrs[4] & 0xf0) | v;
    el.nextElementSibling.textContent = String(v);
    changed();
  }
}

function onEditorClick(e) {
  const team = state.teams[state.selected];
  if (!team) return;

  const pip = e.target.closest('[data-skill]');
  if (pip) {
    const row = pip.closest('tr[data-p]');
    const player = team.players[Number(row.dataset.p)];
    const n = Number(pip.dataset.skill);
    // Clicking the shown value keeps the stored byte, including the one source value above 4.
    if (n === skillStars(player.attrs[5])) return;
    player.attrs[5] = n - 1;
    row.querySelectorAll('.pip').forEach((b) => {
      b.classList.toggle('on', Number(b.dataset.skill) <= n);
      b.setAttribute('aria-pressed', String(Number(b.dataset.skill) === n));
    });
    changed();
    return;
  }

  const rating = e.target.closest('[data-rating]');
  if (rating) {
    const box = rating.closest('[data-r]');
    const r = Number(box.dataset.r);
    const v = Number(rating.dataset.rating);
    if (team.ratings[r] === v) return;
    team.ratings[r] = v;
    box.querySelectorAll('.rp').forEach((b) => {
      b.classList.toggle('on', Number(b.dataset.rating) === v);
      b.setAttribute('aria-pressed', String(Number(b.dataset.rating) === v));
    });
    changed({ list: true });
  }
}

function closeMenu() {
  $('moreMenu').hidden = true;
  $('moreBtn').setAttribute('aria-expanded', 'false');
}

function bindEvents() {
  const menuAction = (id, action) => $(id).addEventListener('click', () => {
    closeMenu();
    return action();
  });
  $('openBtn').addEventListener('click', () => $('romInput').click());
  $('exportRomBtn').addEventListener('click', exportRomFile);
  menuAction('exportJsonBtn', exportJsonFile);
  menuAction('importJsonBtn', () => $('jsonInput').click());
  menuAction('preview32Btn', () => showPreview(PREVIEW8));
  menuAction('preview16Btn', () => showPreview(STOCK16));
  menuAction('revertBtn', revert);
  $('resetTeamBtn').addEventListener('click', resetTeam);

  $('romInput').addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    return file && openRomFile(file);
  });
  $('jsonInput').addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    return file && importJsonFile(file);
  });

  $('keepBtn').addEventListener('click', () => settlePrompt(false));
  $('replaceBtn').addEventListener('click', () => settlePrompt(true));
  // Escape closes the dialog. Browsers fire `close` later, as a task, so ignore
  // it when a new prompt has already reopened the dialog.
  $('replaceDialog').addEventListener('close', () => {
    if (!$('replaceDialog').open) settlePrompt(false);
  });

  $('moreBtn').addEventListener('click', () => {
    const menu = $('moreMenu');
    menu.hidden = !menu.hidden;
    $('moreBtn').setAttribute('aria-expanded', String(!menu.hidden));
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu')) closeMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
  });

  $('banner').addEventListener('click', () => { $('banner').hidden = true; });

  $('teamList').addEventListener('click', (e) => {
    const card = e.target.closest('[data-team]');
    if (!card) return;
    state.selected = Number(card.dataset.team);
    renderTeamList();
    renderEditor();
  });

  $('editor').addEventListener('input', onEditorInput);
  $('editor').addEventListener('click', onEditorClick);

  let dragDepth = 0;
  const drop = $('drop');
  window.addEventListener('dragenter', (e) => {
    if (!e.dataTransfer?.types?.includes('Files')) return;
    dragDepth += 1;
    drop.hidden = false;
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) drop.hidden = true;
  });
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    dragDepth = 0;
    drop.hidden = true;
    return handleFile(e.dataTransfer?.files?.[0]);
  });

  window.addEventListener('beforeunload', (e) => {
    if (!isDirty()) return;
    e.preventDefault();
    e.returnValue = '';
  });
}

bindEvents();
renderAll();
const ready = showPreview(PREVIEW8);

// Hook for the browser console and automation.
window.rosterLab = { state, ready };
