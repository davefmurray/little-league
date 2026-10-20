import { parseRom, applyRom, CONST } from './rom.js';

const RATING_LABELS = ['Batting', 'Running', 'Pitching', 'Defense'];
const TEAM_COUNT = CONST.TEAMS;

const state = {
  rom: null,
  romName: null,
  meta: null,
  teams: [],
  baseline: '[]',
  selected: 0,
  playerCount: CONST.PLAYERS,
  dirty: false,
  source: 'demo',
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const clampInt = (v, lo, hi) => {
  const n = Number.isFinite(+v) ? Math.round(+v) : lo;
  return Math.min(hi, Math.max(lo, n));
};

/** Uppercase, strip non-printable, cap length. */
const clean = (text, max) => String(text)
  .toUpperCase()
  .replace(/[^\x20-\x7E]/g, '')
  .slice(0, max);

function currentTeam() {
  return state.teams[state.selected];
}

function normalizeTeam(raw, i) {
  const shortName = String(raw.shortName ?? raw.short_name ?? '');
  const shortWidth = Number.isInteger(raw.shortWidth) ? raw.shortWidth
    : (Number.isInteger(raw.short_width) ? raw.short_width : Math.max(shortName.length, 6));
  const players = Array.isArray(raw.players) ? raw.players : [];
  return {
    id: i,
    name: String(raw.name ?? '').slice(0, CONST.TEAM_NAME_LEN),
    shortName,
    shortWidth,
    shortAttr: Number.isInteger(raw.shortAttr) ? raw.shortAttr : (raw.short_attr ?? 0),
    ratings: Array.from({ length: 4 }, (_, k) => clampInt(raw.ratings?.[k] ?? 2, 1, 4)),
    players: Array.from({ length: state.playerCount || CONST.PLAYERS }, (_, p) => {
      const pl = players[p] ?? {};
      return {
        name: String(pl.name ?? '').slice(0, CONST.NAME_LEN),
        attrs: Array.from({ length: CONST.ATTRS }, (_, k) => clampInt(pl.attrs?.[k] ?? 0, 0, 255)),
      };
    }),
  };
}

/* ---------------- rendering ---------------- */

function renderChrome() {
  const chip = $('statusChip');
  chip.dataset.mode = state.rom ? 'rom' : 'demo';
  chip.dataset.dirty = String(state.dirty);
  chip.textContent = state.rom
    ? (state.dirty ? 'ROM · UNSAVED'
      : (state.meta?.layout === 'bank8-32'
        ? `ROM · ${state.meta.teams}×${state.meta.players}`
        : 'ROM · READY'))
    : (state.dirty ? 'DEMO · UNSAVED' : 'DEMO DATA');

  $('exportRomBtn').disabled = !state.rom;
  $('revertBtn').disabled = !state.dirty;
}

function renderTeamList() {
  $('teamList').innerHTML = state.teams.map((t, i) => `
    <button type="button" class="team-card${i === state.selected ? ' active' : ''}" data-team="${i}">
      <span class="t-num">${String(i + 1).padStart(2, '0')}</span>
      <span class="t-main">
        <span class="t-name">${esc(t.name || '—')}</span>
        <span class="bars" aria-hidden="true">${t.ratings.map((v) => `<i style="--v:${v}"></i>`).join('')}</span>
      </span>
    </button>`).join('');
}

function renderRatings(team) {
  $('ratings').innerHTML = RATING_LABELS.map((label, r) => `
    <div class="rating">
      <span class="r-label">${label}</span>
      <div class="r-pips" data-r="${r}">
        ${[1, 2, 3, 4].map((v) => `
          <button type="button" class="rp${team.ratings[r] === v ? ' on' : ''}"
                  data-rating="${v}" aria-label="${label} ${v}">${v}</button>`).join('')}
      </div>
    </div>`).join('');
}

function playerRow(player, p) {
  const bat = player.attrs[3] >> 4;
  const pit = player.attrs[3] & 0x0f;
  const extra = player.attrs[4] & 0x0f;
  const skill = Math.min(5, player.attrs[5] + 1);
  return `
    <tr data-p="${p}">
      <td class="slot">${String(p + 1).padStart(2, '0')}${player.attrs[6] ? '<i class="pitch-flag" title="Pitcher">P</i>' : ''}</td>
      <td>
        <input class="name-input" data-field="name" value="${esc(player.name)}"
               maxlength="6" spellcheck="false" autocomplete="off" aria-label="Player ${p + 1} name">
      </td>
      <td>
        <div class="pips" data-field="skill">
          ${[1, 2, 3, 4, 5].map((n) => `
            <button type="button" class="pip${n <= skill ? ' on' : ''}" data-skill="${n}"
                    aria-label="Skill ${n}"></button>`).join('')}
        </div>
      </td>
      <td class="stat">
        <div class="stat-inner">
          <input type="range" min="0" max="15" step="1" value="${bat}" data-field="bat" aria-label="Batting">
          <output>${bat}</output>
        </div>
      </td>
      <td class="stat">
        <div class="stat-inner">
          <input type="range" min="0" max="15" step="1" value="${pit}" data-field="pit" aria-label="Pitching">
          <output>${pit}</output>
        </div>
      </td>
      <td class="stat extra">
        <div class="stat-inner">
          <input type="range" min="0" max="15" step="1" value="${extra}" data-field="extra" aria-label="Speed">
          <output>${extra}</output>
        </div>
      </td>
    </tr>`;
}

function renderEditor() {
  const team = currentTeam();
  if (!team) {
    $('emptyState').hidden = false;
    $('teamPanel').hidden = true;
    return;
  }
  $('emptyState').hidden = true;
  $('teamPanel').hidden = false;

  $('teamEyebrow').textContent = `Team ${String(state.selected + 1).padStart(2, '0')} / ${state.teams.length}`;
  $('teamTitle').textContent = team.name || '—';
  $('shortPreview').textContent = team.shortName || '—';
  $('teamName').value = team.name;
  $('shortName').value = team.shortName;
  $('shortName').maxLength = team.shortWidth;
  $('shortLimit').textContent = `${team.shortWidth} max`;

  renderRatings(team);
  $('playerBody').innerHTML = team.players.map(playerRow).join('');
}

function renderAll() {
  renderTeamList();
  renderEditor();
  renderChrome();
}

/* ---------------- state ---------------- */

function markDirty() {
  state.dirty = JSON.stringify(state.teams) !== state.baseline;
  renderChrome();
}

function commitTeams(teams, { baseline = false, selected = 0 } = {}) {
  state.teams = teams.map(normalizeTeam);
  state.selected = Math.min(selected, state.teams.length - 1);
  if (baseline) state.baseline = JSON.stringify(state.teams);
  renderAll();
}

/* ---------------- banner + toast ---------------- */

let bannerTimer = null;
function showBanner(text, kind = 'info', { autoHide = false } = {}) {
  const el = $('banner');
  el.textContent = text;
  el.dataset.kind = kind;
  el.hidden = false;
  clearTimeout(bannerTimer);
  if (autoHide) bannerTimer = setTimeout(() => { el.hidden = true; }, 7000);
}

function hideBanner() {
  clearTimeout(bannerTimer);
  $('banner').hidden = true;
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

/* ---------------- loading ---------------- */

function loadRomBytes(bytes, name) {
  let parsed;
  try {
    parsed = parseRom(bytes);
  } catch (err) {
    toast(err.message, 'error');
    showBanner(`Could not read ${name}: ${err.message}`, 'warn');
    return false;
  }

  state.rom = bytes;
  state.romName = name;
  state.meta = parsed.meta;
  state.source = 'rom';
  state.playerCount = parsed.meta.players || CONST.PLAYERS;
  state.dirty = false;
  commitTeams(parsed.teams, { baseline: true, selected: 0 });

  const layout = parsed.meta.layout === 'bank8-32'
    ? ` · ${parsed.meta.teams}×${parsed.meta.players} bank8` : '';
  const details = `${bytes.length.toLocaleString()} bytes · MMC1 · ${parsed.meta.prg} PRG banks · ${parsed.meta.chr * 8}K CHR${layout}`;
  if (parsed.meta.looksRight) {
    showBanner(`Loaded ${name} — ${details}`, 'ok', { autoHide: true });
  } else {
    showBanner(
      `Loaded ${name} — ${details}. Team 1 reads "${parsed.teams[0].name}", which is not JAPAN; ` +
      'this may not be the expected ROM. Export still writes at the standard offsets.',
      'warn');
  }
  toast(`ROM loaded: ${name}`);
  return true;
}

async function loadRomFile(file) {
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  loadRomBytes(bytes, file.name);
}

async function loadDemo() {
  const res = await fetch('./roster.json', { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status} for roster.json`);
  const doc = await res.json();
  if (!Array.isArray(doc.teams) || doc.teams.length !== TEAM_COUNT) {
    throw new Error('roster.json has the wrong shape');
  }
  state.playerCount = CONST.PLAYERS;
  state.meta = null;
  commitTeams(doc.teams, { baseline: true, selected: 0 });
  state.source = 'demo';
  showBanner(
    'Previewing the extracted roster from the ROM. Load a .nes file to enable Export ROM.',
    'info');
}

async function loadDemo32() {
  const res = await fetch('./roster32.json', { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status} for roster32.json`);
  const doc = await res.json();
  if (!Array.isArray(doc.teams) || doc.teams.length !== 32) {
    throw new Error('roster32.json must have 32 teams');
  }
  state.playerCount = 20;
  state.rom = null;
  state.romName = null;
  state.meta = null;
  state.source = 'demo32';
  commitTeams(doc.teams, { baseline: true, selected: 0 });
  showBanner(
    '32-team roster preview: 32 x 20 players. JSON export works; load a ROM to enable Export ROM.',
    'info');
}

async function importJsonFile(file) {
  if (!file) return;
  try {
    const doc = JSON.parse(await file.text());
    if (!Array.isArray(doc.teams) || ![16, 32].includes(doc.teams.length)) {
      throw new Error('Expected a JSON file with 16 or 32 teams.');
    }
    state.playerCount = doc.teams.reduce(
      (n, t) => Math.max(n, Array.isArray(t.players) ? t.players.length : 0), 0) || 15;
    state.teams = doc.teams.map(normalizeTeam);
    state.selected = 0;
    renderAll();
    markDirty();
    toast(`Imported roster from ${file.name}`);
  } catch (err) {
    toast(`Import failed: ${err.message}`, 'error');
  }
}

function handleFile(file) {
  if (!file) return;
  const name = file.name.toLowerCase();
  if (name.endsWith('.nes')) return loadRomFile(file);
  if (name.endsWith('.json')) return importJsonFile(file);
  toast('Drop a .nes ROM or a roster .json.', 'warn');
}

/* ---------------- export ---------------- */

function exportRom() {
  if (!state.rom) {
    toast('Load a ROM first — export works against the original file.', 'warn');
    return;
  }
  try {
    const out = applyRom(state.rom, state.teams);
    const base = (state.romName || 'little-league').replace(/\.nes$/i, '');
    const filename = `${base}-edited.nes`;
    download(filename, new Blob([out], { type: 'application/octet-stream' }));
    toast(`Exported ${filename} · ${out.length.toLocaleString()} bytes`);
  } catch (err) {
    toast(err.message, 'error');
  }
}

function exportJson() {
  const doc = {
    version: 1,
    source: state.romName || 'sample',
    teams: state.teams.map((t) => ({
      id: t.id,
      name: t.name,
      short_name: t.shortName,
      short_width: t.shortWidth,
      short_attr: t.shortAttr,
      ratings: t.ratings,
      players: t.players.map((p) => ({ name: p.name, attrs: p.attrs })),
    })),
  };
  const base = (state.romName || 'little-league').replace(/\.nes$/i, '');
  const filename = `${base}-roster.json`;
  download(filename, new Blob([JSON.stringify(doc, null, 2) + '\n'], { type: 'application/json' }));
  toast(`Exported ${filename}`);
}

/* ---------------- events ---------------- */

function bindEvents() {
  $('loadBtn').addEventListener('click', () => $('romInput').click());
  $('load32Btn').addEventListener('click', () => {
    $('moreMenu').hidden = true;
    loadDemo32().catch((err) => toast(`32-team demo failed: ${err.message}`, 'error'));
  });
  $('importJsonBtn').addEventListener('click', () => {
    $('moreMenu').hidden = true;
    $('jsonInput').click();
  });
  $('exportJsonBtn').addEventListener('click', () => {
    $('moreMenu').hidden = true;
    exportJson();
  });
  $('exportRomBtn').addEventListener('click', exportRom);

  $('romInput').addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    await loadRomFile(file);
  });
  $('jsonInput').addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    await importJsonFile(file);
  });

  $('repoBtn').addEventListener('click', async () => {
    try {
      const res = await fetch('/rom', { cache: 'no-store' });
      if (!res.ok) {
        throw new Error(`No ROM served at /rom (HTTP ${res.status}). Put a .nes in the repo root or use Load ROM.`);
      }
      const bytes = new Uint8Array(await res.arrayBuffer());
      loadRomBytes(bytes, res.headers.get('X-Rom-Name') || 'repo ROM');
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  $('moreBtn').addEventListener('click', () => {
    const menu = $('moreMenu');
    menu.hidden = !menu.hidden;
    $('moreBtn').setAttribute('aria-expanded', String(!menu.hidden));
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu')) {
      $('moreMenu').hidden = true;
      $('moreBtn').setAttribute('aria-expanded', 'false');
    }
  });

  $('revertBtn').addEventListener('click', () => {
    $('moreMenu').hidden = true;
    if (!state.dirty) return;
    state.teams = JSON.parse(state.baseline);
    state.selected = Math.min(state.selected, state.teams.length - 1);
    state.dirty = false;
    renderAll();
    toast('Reverted to the loaded data.');
  });

  $('resetTeamBtn').addEventListener('click', () => {
    const base = JSON.parse(state.baseline)[state.selected];
    if (!base) return;
    state.teams[state.selected] = JSON.parse(JSON.stringify(base));
    renderEditor();
    renderTeamList();
    markDirty();
    toast(`Reset team ${state.selected + 1}.`);
  });

  $('banner').addEventListener('click', hideBanner);

  $('teamList').addEventListener('click', (e) => {
    const card = e.target.closest('[data-team]');
    if (!card) return;
    state.selected = Number(card.dataset.team);
    renderTeamList();
    renderEditor();
  });

  $('editor').addEventListener('input', onEditorInput);
  $('editor').addEventListener('click', onEditorClick);

  // drag & drop
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
    handleFile(e.dataTransfer?.files?.[0]);
  });

  window.addEventListener('beforeunload', (e) => {
    if (!state.dirty) return;
    e.preventDefault();
    e.returnValue = '';
  });
}

function onEditorInput(e) {
  const team = currentTeam();
  if (!team) return;
  const el = e.target;

  if (el.id === 'teamName') {
    const v = clean(el.value, CONST.TEAM_NAME_LEN);
    if (el.value !== v) el.value = v;
    team.name = v;
    $('teamTitle').textContent = v || '—';
    renderTeamList();
    markDirty();
    return;
  }

  if (el.id === 'shortName') {
    const v = clean(el.value, team.shortWidth);
    if (el.value !== v) el.value = v;
    team.shortName = v;
    $('shortPreview').textContent = v || '—';
    markDirty();
    return;
  }

  const tr = el.closest('tr[data-p]');
  if (!tr) return;
  const player = team.players[Number(tr.dataset.p)];

  if (el.dataset.field === 'name') {
    const v = clean(el.value, CONST.NAME_LEN);
    if (el.value !== v) el.value = v;
    player.name = v;
    markDirty();
    return;
  }

  if (el.type === 'range') {
    const v = Number(el.value);
    const field = el.dataset.field;
    if (field === 'bat') player.attrs[3] = (v << 4) | (player.attrs[3] & 0x0f);
    if (field === 'pit') player.attrs[3] = (player.attrs[3] & 0xf0) | v;
    if (field === 'extra') player.attrs[4] = (player.attrs[4] & 0xf0) | v;
    if (el.nextElementSibling) el.nextElementSibling.textContent = String(v);
    markDirty();
  }
}

function onEditorClick(e) {
  const team = currentTeam();
  if (!team) return;

  const pip = e.target.closest('[data-skill]');
  if (pip) {
    const tr = pip.closest('tr[data-p]');
    const n = Number(pip.dataset.skill);
    team.players[Number(tr.dataset.p)].attrs[5] = n - 1;
    tr.querySelectorAll('.pip').forEach((b) => {
      b.classList.toggle('on', Number(b.dataset.skill) <= n);
    });
    markDirty();
    return;
  }

  const rating = e.target.closest('[data-rating]');
  if (rating) {
    const box = rating.closest('[data-r]');
    const r = Number(box.dataset.r);
    const v = Number(rating.dataset.rating);
    team.ratings[r] = v;
    box.querySelectorAll('.rp').forEach((b) => {
      b.classList.toggle('on', Number(b.dataset.rating) === v);
    });
    renderTeamList();
    markDirty();
  }
}

/* ---------------- boot ---------------- */

bindEvents();
renderAll();

loadDemo().catch((err) => {
  showBanner(
    `Could not load roster.json (${err.message}). Serve this folder over HTTP, e.g. ` +
    '`python3 tools/serve.py`, then open http://127.0.0.1:8080.',
    'warn');
});

// Test hook for the browser console / automation.
window.rosterLab = { state, parseRom, applyRom };
