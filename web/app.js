import {
  ACTIVE_PLAYERS, PREVIEW8, STOCK16, deepFreeze, fitRoster, needsColorUpgrade, openRom, previewRoster,
  readRosterFile, rosterJson, sameTeams, skillStars, writeRom,
} from './rom.js';
import {
  BASIC_COLORS, BELOW_BLACK, BELOW_BLACK_NOTE, NES_RGB, batterColor, batterPicture, colorName, describeColor,
  parseColorCode,
} from './colors.js';

const RATING_LABELS = ['Batting', 'Running', 'Pitching', 'Defense'];
const UNIFORM_PARTS = [
  { slot: 'cap', label: 'Cap & trim', help: 'Cap, helmet, socks and belt trim.' },
  { slot: 'jersey', label: 'Jersey', help: '' },
  {
    slot: 'hair',
    label: 'Hair',
    help: 'Batter’s hair while this team bats, and hair in ending scenes. ' +
      'While this team bats, the other team’s pitcher shows a little of this color too.',
  },
];
/** The numbers a roster row edits, in column order: where each lives in a record's attrs, and its range. */
const STATS = new Map([
  ['bat', {
    name: 'batting', min: 0, max: 15, read: (a) => a[3] >> 4, write: (a, v) => { a[3] = (v << 4) | (a[3] & 0x0f); },
  }],
  ['pit', {
    name: 'pitching', min: 0, max: 15, read: (a) => a[3] & 0x0f, write: (a, v) => { a[3] = (a[3] & 0xf0) | v; },
  }],
  ['speed', {
    name: 'speed', min: 0, max: 15, read: (a) => a[4] & 0x0f, write: (a, v) => { a[4] = (a[4] & 0xf0) | v; },
  }],
  // Entering the shown skill keeps the stored byte, including the one source value above 4.
  ['skill', {
    name: 'skill', min: 1, max: 5, read: (a) => skillStars(a[5]), write: (a, v) => { if (v !== skillStars(a[5])) a[5] = v - 1; },
  }],
]);
const GRID_COLUMNS = 13;
const OWN_COLORS = 'preview8-independent-colors-v1';
const VIEWS = new Map([
  [PREVIEW8, { label: 'Preview 8', chip: 'Preview 8', roster: './roster32.json', meta: './teams32.json', stem: 'preview8' }],
  [STOCK16, { label: '16-team US', chip: '16-team', roster: './roster.json', stem: 'us16' }],
]);

/**
 * @typedef {{bytes: Uint8Array, name: string, sha256: string, exact: boolean, variant: string}} LoadedRom
 * @typedef {{profile: object, baseline: object[], rom: LoadedRom | null}} Session
 * @typedef {{team: number, part: string, opening: number, announced: number, extra: number | null}} Picker
 *
 * `session.baseline` is the frozen roster the session started from: the ROM as
 * read, or the bundled preview. `teams` is the draft, dirty whenever it differs
 * from the baseline. Imports replace only the draft, so Revert always returns to
 * the baseline. `revision` counts draft changes, which lets a load that finishes
 * later notice edits made while it ran. The page follows the session: the start
 * screen without one, a roster-only preview without a ROM, the ROM editor with
 * one. `picker` is the shared color palette: the team and uniform part it
 * edits, that part's value when it was chosen or last kept (Escape restores
 * it), the last value announced, and a code outside the basic grid that it
 * keeps on offer.
 */
const state = { session: null, teams: [], selected: 0, revision: 0, picker: null };

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
  const needsFocus = state.session === null || document.activeElement === $('uniformOpen');
  const sameLayout = state.session?.profile === session.profile;
  state.session = session;
  state.teams = structuredClone(draft);
  state.selected = sameLayout ? state.selected : 0;
  state.revision += 1;
  renderAll();
  if (needsFocus) $('teamTitle').focus();
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
    if (!isStale(t)) showBanner(`Couldn't load the ${label(profile)} roster. ${err.message}`, 'warn');
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
    const loaded = { bytes, name: file.name, sha256: rom.sha256, exact: rom.exact, variant: rom.variant };
    startSession({ profile: rom.profile, baseline, rom: loaded }, baseline);
    const kind = rom.variant === OWN_COLORS ? `${label(rom.profile)} ROM where every team has its own colors` : `${label(rom.profile)} ROM`;
    showBanner(rom.exact
      ? `Opened ${file.name}, the original ${label(rom.profile)} ROM. Edits stay in this browser until you export.`
      : `Opened ${file.name}, an edited copy of the ${kind}. ` +
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
    // A file without team colors keeps the colors being edited; a new session starts from its baseline's.
    const fit = () => fitRoster(read, session.baseline, session === current ? state.teams : session.baseline);
    if (!(await mayReplace(t, fit(), `Importing ${file.name}`, session === current))) return;
    const teams = fit();
    const keptColors = read.teams.some((team, i) => !team.uniform && !sameTeams(teams[i].uniform, session.baseline[i].uniform));
    if (session === current) replaceDraft(teams);
    else startSession(session, teams);
    const into = session.rom
      ? 'into the open ROM.'
      : `onto the ${label(read.profile)} roster. To export a ROM, open the ROM, then import this file again.`;
    const notices = [...read.notices, ...(keptColors ? ['It has no team colors, so your color edits stay.'] : [])];
    showBanner([`Imported ${file.name} ${into}`, ...notices].join(' '), 'ok', { autoHide: !notices.length });
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
    const upgrades = needsColorUpgrade(session.rom.variant, session.baseline, draft);
    const out = await writeRom(session.rom.bytes, session.profile, session.baseline, draft);
    const filename = `${stem(session.rom.name)}-edited.nes`;
    download(filename, new Blob([out], { type: 'application/octet-stream' }));
    toast(sameTeams(draft, session.baseline)
      ? `Saved ${filename}, an unchanged copy of ${session.rom.name}.`
      : `Saved ${filename} with your edits.${upgrades ? ' In this copy all 32 teams have their own colors.' : ''}`);
  } catch (err) {
    showBanner(`Couldn't export the ROM. ${err.message}`, 'warn');
  }
}

function exportJsonFile() {
  const { session } = state;
  if (!session) return;
  const source = session.rom
    ? { name: session.rom.name, sha256: session.rom.sha256, variant: session.rom.variant }
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
  const rom = session?.rom;
  const dirty = isDirty();
  $('start').hidden = session !== null;
  $('workspace').hidden = session === null;
  $('fileBar').hidden = session === null;
  $('fileBar').dataset.mode = rom ? 'rom' : 'roster';
  $('fileBar').dataset.dirty = String(dirty);
  $('fileName').textContent = rom ? rom.name : 'No ROM open';
  $('fileBtn').textContent = rom ? 'Change file' : 'Open ROM';
  $('fileGetRom').hidden = Boolean(rom);
  const source = !rom ? 'ROSTER ONLY' : rom.exact ? 'ORIGINAL ROM' : 'EDITED ROM';
  const own = rom?.variant === OWN_COLORS && 'own team colors';
  $('statusChip').textContent = session
    ? [VIEWS.get(session.profile).chip, own, source, dirty && 'UNSAVED'].filter(Boolean).join(' · ')
    : '';
  $('exportRomBtn').hidden = !rom;
  $('exportRomBtn').disabled = !rom;
  $('exportJsonBtn').disabled = !session;
  $('revertBtn').disabled = !dirty;
  $('saveState').hidden = session === null;
  $('saveState').dataset.dirty = String(dirty);
  $('saveState').textContent = dirty ? 'Unsaved changes' : 'No unsaved changes';
  $('resetTeamBtn').hidden = session === null;
  $('upgradeNote').hidden = !(rom && needsColorUpgrade(rom.variant, session.baseline, state.teams));
}

function renderTeamList() {
  $('teamCount').textContent = String(state.teams.length);
  $('teamList').innerHTML = state.teams.map((t, i) => `
    <button type="button" class="team" data-team="${i}">
      <span class="t-num">${pad2(i + 1)}</span> <span class="t-name">${esc(t.name || '—')}</span>
    </button>`).join('');
  $('teamSelect').innerHTML = state.teams.map((t, i) => `<option value="${i}">${pad2(i + 1)} ${esc(t.name || '—')}</option>`).join('');
  markTeam();
  filterTeams();
}

/** Mark the selected team in the rail and the narrow-screen select, in place so focus stays put. */
function markTeam() {
  for (const card of document.querySelectorAll('#teamList [data-team]')) {
    const on = Number(card.dataset.team) === state.selected;
    card.classList.toggle('selected', on);
    card.setAttribute('aria-current', String(on));
  }
  $('teamSelect').value = String(state.selected);
}

function filterTeams() {
  const words = $('teamSearch').value.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const card of document.querySelectorAll('#teamList [data-team]')) {
    const t = Number(card.dataset.team);
    const text = [pad2(t + 1), state.teams[t].name, state.teams[t].code].filter(Boolean).join(' ').toLowerCase();
    card.hidden = !words.every((word) => text.includes(word));
    if (!card.hidden) shown += 1;
  }
  $('teamNone').hidden = shown > 0 || state.teams.length === 0;
}

function selectTeam(t) {
  keepColor();
  state.selected = t;
  markTeam();
  renderEditor();
}

const dots = (v) => '●'.repeat(v) + '○'.repeat(4 - v);

function renderRatings(team) {
  $('ratings').innerHTML = RATING_LABELS.map((name, r) => `
    <div class="rating">
      <label for="rating-${r}">${name}</label>
      <select id="rating-${r}" data-r="${r}">
        ${[1, 2, 3, 4].map((v) => `<option value="${v}"${team.ratings[r] === v ? ' selected' : ''}>${v}</option>`).join('')}
      </select>
      <i data-dots aria-hidden="true">${dots(team.ratings[r])}</i>
    </div>`).join('');
}

const rowOf = (slot) => UNIFORM_PARTS.find((row) => row.slot === slot);
const teamLabel = (t) => state.teams[t].name || `Team ${t + 1}`;
const colorCells = (picker) => (picker.extra === null ? BASIC_COLORS : [...BASIC_COLORS, picker.extra]);
const partButton = (slot) => document.querySelector(`#parts [data-part="${slot}"]`);
const pickedColor = () => state.teams[state.picker.team].uniform[state.picker.part];
const keptText = () =>
  `${teamLabel(state.picker.team)} ${rowOf(state.picker.part).label}: ${describeColor(pickedColor())}.`;

function inkFor(code) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(NES_RGB[code].slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? 'dark' : 'light';
}

function swatch(row, code, value, extra) {
  const on = code === value;
  return `<button type="button" class="sw-btn" role="radio" data-swatch="${code}" data-focus="sw-${code}"
    aria-checked="${on}" tabindex="${on ? 0 : -1}" data-ink="${inkFor(code)}" style="--sw:${NES_RGB[code]}"
    aria-label="${esc(`${row.label} ${describeColor(code)}${extra ? ', outside the basic grid' : ''}`)}"
    title="${esc(describeColor(code))}"></button>`;
}

/** Point the shared palette at `slot` of the shown team, starting a fresh Escape point. */
function aimPicker(slot) {
  const team = state.selected;
  const value = state.teams[team].uniform[slot];
  state.picker = { team, part: slot, opening: value, announced: value, extra: BASIC_COLORS.includes(value) ? null : value };
}

function renderPalette() {
  const { picker } = state;
  const row = rowOf(picker.part);
  const value = pickedColor();
  $('palette').setAttribute('aria-label', `${row.label} color`);
  $('palette').innerHTML = colorCells(picker).map((code) => swatch(row, code, value, code === picker.extra)).join('');
}

function renderColors() {
  const active = document.activeElement;
  const focus = active?.closest?.('#colorsCard') ? active.dataset.focus : undefined;
  aimPicker(state.picker?.part ?? UNIFORM_PARTS[0].slot);
  $('parts').innerHTML = UNIFORM_PARTS.map((row) => `
    <button type="button" class="part" data-part="${row.slot}" data-focus="part-${row.slot}" aria-pressed="false">
      <span class="sw" data-chip></span> <span class="part-label">${esc(row.label)}</span> <span class="visually-hidden part-value"></span>
    </button>`).join('');
  renderPalette();
  updateUniform();
  if (focus) document.querySelector(`[data-focus="${focus}"]`)?.focus();
}

/** Paint the team's colors wherever they appear, in place so focus stays put. */
function updateUniform() {
  const { picker } = state;
  const { uniform } = state.teams[picker.team];
  const value = uniform[picker.part];
  for (const row of UNIFORM_PARTS) {
    const code = uniform[row.slot];
    const button = partButton(row.slot);
    button.setAttribute('aria-pressed', String(row.slot === picker.part));
    if (code === BELOW_BLACK) button.setAttribute('aria-describedby', 'colorWarn');
    else button.removeAttribute('aria-describedby');
    button.title = describeColor(code);
    button.querySelector('[data-chip]').setAttribute('style', `--sw:${NES_RGB[code]}`);
    button.querySelector('.part-value').textContent = describeColor(code);
  }
  if (!colorCells(picker).includes(value)) {
    picker.extra = value;
    renderPalette();
  } else {
    for (const b of $('palette').querySelectorAll('[data-swatch]')) {
      const on = Number(b.dataset.swatch) === value;
      b.setAttribute('aria-checked', String(on));
      b.setAttribute('tabindex', on ? '0' : '-1');
    }
  }
  const { help } = rowOf(picker.part);
  $('partHelp').textContent = help;
  $('partHelp').hidden = !help;
  $('colorWarn').hidden = value !== BELOW_BLACK;
  $('palette').setAttribute('aria-describedby',
    [help && 'partHelp', 'paletteHint', value === BELOW_BLACK && 'colorWarn'].filter(Boolean).join(' '));
  showKeysHint();
  $('resetColorsBtn').disabled = sameTeams(uniform, state.session.baseline[picker.team].uniform);
  renderPreview();
}

function showKeysHint() {
  $('paletteHint').textContent = `Arrow keys move. Enter keeps. Escape puts back ${colorName(state.picker.opening)}.`;
}

function chooseColor(code) {
  const { picker } = state;
  const team = state.teams[picker.team];
  if (team.uniform[picker.part] === code) return false;
  team.uniform = { ...team.uniform, [picker.part]: code };
  state.revision += 1;
  updateUniform();
  renderChrome();
  return true;
}

function announce(text) {
  const el = $('colorStatus');
  el.textContent = '';
  el.textContent = text;
}

/** Say `text` about the shown part's color unless that code was the last one said. */
function announceColor(text) {
  const { picker } = state;
  const code = pickedColor();
  if (picker.announced === code) return;
  picker.announced = code;
  announce(code === BELOW_BLACK ? `${text} ${BELOW_BLACK_NOTE}` : text);
}

/** Keep the shown color as the new Escape point, and say it once. Leaving a part or team keeps it too. */
function keepColor() {
  const { picker } = state;
  if (!picker) return;
  picker.opening = pickedColor();
  announceColor(keptText());
  showKeysHint();
}

/** Put back the color the shown part had when it was chosen or last kept. */
function restoreColor() {
  const { picker } = state;
  if (chooseColor(picker.opening)) {
    picker.announced = picker.opening;
    announce(`${rowOf(picker.part).label} back to ${describeColor(picker.opening)}.`);
  }
  partButton(picker.part).focus();
}

function selectPart(slot) {
  keepColor();
  aimPicker(slot);
  renderPalette();
  updateUniform();
  $('palette').querySelector('[aria-checked="true"]')?.focus();
}

function resetColors() {
  const t = state.selected;
  const base = state.session.baseline[t].uniform;
  if (sameTeams(state.teams[t].uniform, base)) return;
  state.teams[t].uniform = { ...base };
  state.revision += 1;
  renderColors();
  renderChrome();
  partButton(state.picker.part).focus();
  const parts = UNIFORM_PARTS.map((row) => `${row.label} ${describeColor(base[row.slot])}`).join(', ');
  const note = Object.values(base).includes(BELOW_BLACK) ? ` ${BELOW_BLACK_NOTE}` : '';
  announce(`${teamLabel(t)} colors reset: ${parts}.${note}`);
}

function applyCode() {
  const input = $('codeInput');
  const error = $('codeError');
  const parsed = parseColorCode(input.value);
  if (parsed.error) {
    error.textContent = parsed.error;
    error.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    announce(parsed.error);
    return;
  }
  error.textContent = '';
  error.hidden = true;
  input.removeAttribute('aria-invalid');
  chooseColor(parsed.value);
  announceColor(keptText());
}

/**
 * Palette keys, as a radio group: arrows move and choose, Home and End go to the row's ends,
 * Enter keeps, and Escape anywhere in the uniform controls restores. Arrows also step roster numbers.
 */
function onEditorKeydown(e) {
  const el = e.target;
  const stat = STATS.get(el.dataset?.field);
  if (stat && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
    e.preventDefault();
    const player = playerOf(el);
    const step = e.key === 'ArrowUp' ? 1 : -1;
    editStat(player, stat, Math.min(stat.max, Math.max(stat.min, stat.read(player.attrs) + step)));
    el.value = String(stat.read(player.attrs));
    el.removeAttribute('aria-invalid');
    return;
  }
  const { picker } = state;
  if (!picker || !el.closest?.('#colorsCard')) return;
  if (e.key === 'Escape') {
    e.preventDefault();
    restoreColor();
    return;
  }
  if (e.key === 'Enter' && el.id === 'codeInput') {
    e.preventDefault();
    applyCode();
    return;
  }
  const sw = el.closest('[data-swatch]');
  if (!sw) return;
  if (e.key === 'Enter') {
    e.preventDefault();
    keepColor();
    partButton(picker.part).focus();
    return;
  }
  const cells = colorCells(picker);
  const i = cells.indexOf(Number(sw.dataset.swatch));
  const row = Math.floor(i / GRID_COLUMNS);
  const last = cells.length - 1;
  const next = {
    ArrowRight: Math.min(i + 1, last),
    ArrowLeft: Math.max(i - 1, 0),
    ArrowDown: row === Math.floor(last / GRID_COLUMNS) ? i : Math.min(i + GRID_COLUMNS, last),
    ArrowUp: row === 0 ? i : i - GRID_COLUMNS,
    Home: row * GRID_COLUMNS,
    End: Math.min(row * GRID_COLUMNS + GRID_COLUMNS - 1, last),
  }[e.key];
  if (next === undefined) return;
  e.preventDefault();
  chooseColor(cells[next]);
  $('palette').querySelector(`[data-swatch="${cells[next]}"]`)?.focus();
}

const batters = new WeakMap();

function drawBatter(rom, uniform) {
  if (!batters.has(rom.bytes)) batters.set(rom.bytes, batterPicture(rom.bytes));
  const picture = batters.get(rom.bytes);
  const ctx = $('batterCanvas').getContext?.('2d');
  if (!ctx) return;
  const image = ctx.createImageData(picture.width, picture.height);
  picture.pixels.forEach((entry, i) => {
    if (!entry) return;
    const rgb = NES_RGB[batterColor(entry, picture.palette, uniform) & 0x3f];
    image.data.set([1, 3, 5].map((at) => parseInt(rgb.slice(at, at + 2), 16)).concat(255), 4 * i);
  });
  ctx.putImageData(image, 0, 0);
}

/** The batter decoded from the open ROM, or a pointer to open one. Never a stand-in drawing. */
function renderPreview() {
  const t = state.selected;
  const rom = state.session.rom;
  $('batterCanvas').hidden = !rom;
  $('uniformEmpty').hidden = Boolean(rom);
  if (!rom) return;
  const { cap, jersey, hair } = state.teams[t].uniform;
  $('batterCanvas').setAttribute('aria-label', `${teamLabel(t)} colors: cap and trim ${describeColor(cap)}, ` +
    `jersey ${describeColor(jersey)}, hair ${describeColor(hair)}.`);
  drawBatter(rom, state.teams[t].uniform);
}

const playerOf = (el) => state.teams[state.selected].players[Number(el.closest('tr[data-p]').dataset.p)];

function editStat(player, stat, value) {
  const before = player.attrs.join();
  stat.write(player.attrs, value);
  if (player.attrs.join() !== before) changed();
}

function playerRow(player, p) {
  const pitcher = player.attrs[6];
  return `
    <tr data-p="${p}">
      <td class="slot">${pad2(p + 1)}${pitcher ? '<i class="pitch-flag" title="Linked to one of the team’s pitcher records">P</i>' : ''}</td>
      <td>
        <input class="name" data-field="name" value="${esc(player.name)}"
               maxlength="6" spellcheck="false" autocomplete="off" aria-label="Player ${p + 1} name">
      </td>
      ${[...STATS].map(([field, stat]) => `
        <td>
          <input class="num" data-field="${field}" value="${stat.read(player.attrs)}" inputmode="numeric" maxlength="2"
                 autocomplete="off" title="${stat.min} to ${stat.max}" aria-label="Player ${p + 1} ${stat.name}">
        </td>`).join('')}
    </tr>`;
}

function storedRow(player, p) {
  return `
    <tr>
      <td class="slot">${pad2(p + 1)}</td>
      <td>${esc(player.name || '—')}</td>
      ${[...STATS.values()].map((stat) => `<td>${stat.read(player.attrs)}</td>`).join('')}
    </tr>`;
}

function renderEditor() {
  const team = state.teams[state.selected];
  if (!team) return;

  const { profile } = state.session;
  $('teamBadge').textContent = team.code ?? '';
  $('teamBadge').hidden = !team.code;
  $('teamEyebrow').textContent = `Team ${pad2(state.selected + 1)} / ${state.teams.length}${team.region ? ` · ${team.region}` : ''}`;
  $('teamTitle').textContent = team.name || '—';

  const editable = profile.text.filter((f) => f.editable);
  $('identityEdit').hidden = editable.length === 0;
  $('identityNote').hidden = editable.length > 0;
  for (const f of editable) {
    const input = document.querySelector(`[data-text="${f.key}"]`);
    input.value = team[f.key];
    input.maxLength = f.width(state.selected);
  }
  if (team.shortName !== undefined) $('shortLimit').textContent = `${textField('shortName').width(state.selected)} max`;

  renderRatings(team);
  renderColors();
  $('rosterCount').textContent = `${ACTIVE_PLAYERS} active`;
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
  if (el.id === 'codeInput') {
    el.removeAttribute('aria-invalid');
    $('codeError').hidden = true;
    return;
  }

  const field = el.dataset.text && textField(el.dataset.text);
  if (field) {
    const v = clean(el.value, field.width(state.selected));
    if (el.value !== v) el.value = v;
    team[field.key] = v.trimEnd();
    if (field.key === 'name') $('teamTitle').textContent = team.name || '—';
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

  // Digits only. A blank or out-of-range entry keeps the last good value until the field is left.
  const stat = STATS.get(el.dataset.field);
  if (!stat) return;
  const digits = el.value.replace(/\D/g, '').slice(0, 2);
  if (el.value !== digits) el.value = digits;
  const v = digits === '' ? NaN : Number(digits);
  if (!(v >= stat.min && v <= stat.max)) {
    el.setAttribute('aria-invalid', 'true');
    return;
  }
  el.removeAttribute('aria-invalid');
  editStat(player, stat, v);
}

function onEditorChange(e) {
  const team = state.teams[state.selected];
  const el = e.target;
  if (!team || !el.dataset) return;
  if (el.dataset.r !== undefined) {
    const r = Number(el.dataset.r);
    const v = Number(el.value);
    if (team.ratings[r] === v) return;
    team.ratings[r] = v;
    el.parentNode.querySelector('[data-dots]').textContent = dots(v);
    changed();
    return;
  }
  const stat = STATS.get(el.dataset.field);
  if (!stat || !el.closest('tr[data-p]')) return;
  el.value = String(stat.read(playerOf(el).attrs));
  el.removeAttribute('aria-invalid');
}

function onEditorClick(e) {
  if (!state.teams[state.selected]) return;
  const part = e.target.closest('[data-part]');
  if (part) {
    selectPart(part.dataset.part);
    return;
  }
  const chosen = e.target.closest('[data-swatch]');
  if (chosen) {
    chooseColor(Number(chosen.dataset.swatch));
    keepColor();
    return;
  }
  if (e.target.closest('#resetColorsBtn')) {
    resetColors();
    return;
  }
  if (e.target.closest('#codeSetBtn')) applyCode();
}

function closeMenu() {
  $('moreMenu').hidden = true;
  $('moreBtn').setAttribute('aria-expanded', 'false');
}

function bindEvents() {
  const menuAction = (id, action) => $(id).addEventListener('click', () => {
    closeMenu();
    $('moreBtn').focus();
    return action();
  });
  const chooseRom = () => $('romInput').click();
  $('openBtn').addEventListener('click', chooseRom);
  $('fileBtn').addEventListener('click', chooseRom);
  $('uniformOpen').addEventListener('click', chooseRom);
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
    if (card) selectTeam(Number(card.dataset.team));
  });
  $('teamSelect').addEventListener('change', (e) => selectTeam(Number(e.target.value)));
  $('teamSearch').addEventListener('input', filterTeams);
  $('teamSearch').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const first = Array.from(document.querySelectorAll('#teamList [data-team]')).find((card) => !card.hidden);
    if (!first) return;
    e.preventDefault();
    selectTeam(Number(first.dataset.team));
  });

  $('editor').addEventListener('input', onEditorInput);
  $('editor').addEventListener('change', onEditorChange);
  $('editor').addEventListener('click', onEditorClick);
  $('editor').addEventListener('keydown', onEditorKeydown);

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
$('colorWarn').textContent = BELOW_BLACK_NOTE;
renderAll();
showPreview(PREVIEW8);

// Hook for the browser console and automation.
window.rosterLab = { state };
