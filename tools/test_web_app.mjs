// Behavior tests for web/app.js: real index.html, real event handlers, a DOM
// stub, fake fetch/files, and a WebCrypto wrapper whose digests can be held
// back to finish out of order. The ROM images are synthetic and carry the
// bundled preview rosters. The wrapper reports their digests as the pinned
// production ones, so the app's unmodified open path admits them.
import { test as nodeTest } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { webcrypto } from 'node:crypto';
import { createDom, event } from './web_dom_stub.mjs';
import { STOCK_SHORT_WIDTHS, fixture, lowRecord, p8Record, stockName, writableMask, maskedDigest, sha256 } from './web_fixtures.mjs';
import { PREVIEW8, STOCK16, previewRoster, rosterJson } from '../web/rom.js';

const WEB = new URL('../web/', import.meta.url);
const read = (name) => readFileSync(new URL(name, WEB), 'utf8');
const INDEX = read('index.html');
const RELEASE = 'https://github.com/davefmurray/little-league/releases/download/32-team-preview-8/little-league-32-team.nes';

// A broken flow tends to wait forever on a prompt; fail it instead of hanging.
const test = (name, fn) => nodeTest(name, { timeout: 20000 }, fn);

const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...args) => {
  const handle = realSetTimeout(fn, ms, ...args);
  handle.unref?.();
  return handle;
};

const blobs = new Map();
URL.createObjectURL = (blob) => {
  const url = `blob:test/${blobs.size}`;
  blobs.set(url, blob);
  return url;
};
URL.revokeObjectURL = () => {};

const PREVIEW = {
  preview8: previewRoster(PREVIEW8, JSON.parse(read('roster32.json')), JSON.parse(read('teams32.json'))),
  stock16: previewRoster(STOCK16, JSON.parse(read('roster.json')), null),
};
const P8 = fixture('preview8', PREVIEW.preview8).bytes;
const US = fixture('stock16', PREVIEW.stock16).bytes;

const SWAP = new Map([
  [maskedDigest(P8, writableMask('preview8')), PREVIEW8.maskedSha256],
  [sha256(P8), PREVIEW8.originalSha256],
  [maskedDigest(US, writableMask('stock16')), STOCK16.maskedSha256],
  [sha256(US), STOCK16.originalSha256],
]);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const heldDigests = [];
Object.defineProperty(globalThis, 'crypto', {
  configurable: true,
  value: {
    subtle: {
      async digest(algorithm, data) {
        const gate = heldDigests.shift();
        if (gate) {
          gate.reached.resolve();
          await gate.release.promise;
        }
        const hex = Buffer.from(await webcrypto.subtle.digest(algorithm, data)).toString('hex');
        return Uint8Array.from(Buffer.from(SWAP.get(hex) ?? hex, 'hex')).buffer;
      },
    },
  },
});

/** Hold the next digest call until `release.resolve()`; `reached` settles when it starts. */
function holdNextDigest() {
  const gate = { reached: deferred(), release: deferred() };
  heldDigests.push(gate);
  return gate;
}

const romFile = (name, bytes, gate) => ({
  name,
  arrayBuffer: async () => {
    if (gate) await gate.promise;
    return bytes.slice().buffer;
  },
});

const jsonFile = (name, doc, gate) => ({
  name,
  text: async () => {
    if (gate) await gate.promise;
    return typeof doc === 'string' ? doc : JSON.stringify(doc);
  },
});

async function until(condition, label) {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > 3000) assert.fail(`timed out waiting for ${label}`);
    await new Promise((r) => setImmediate(r));
  }
}

let instance = 0;

/** Load a fresh copy of the app on a fresh page. `gates` hold back bundled-file fetches. */
async function boot({ gates = {}, wait = true } = {}) {
  const dom = createDom(INDEX);
  globalThis.document = dom.document;
  globalThis.window = dom.window;
  globalThis.fetch = async (url) => {
    const name = String(url).replace('./', '');
    const status = gates[name] ? await gates[name].promise : 200;
    return { ok: status === 200, status, json: async () => JSON.parse(read(name)) };
  };
  await import(`../web/app.js?instance=${++instance}`);
  const page = helpers(dom);
  if (wait) await page.ready();
  return page;
}

function helpers({ document, window }) {
  const $ = (id) => document.getElementById(id);
  const row = (p) => document.querySelector(`#playerBody tr[data-p="${p}"]`);
  const lastDownload = async () => {
    const { filename, href } = document.downloads.at(-1);
    return { filename, bytes: new Uint8Array(await blobs.get(href).arrayBuffer()), text: await blobs.get(href).text() };
  };
  return {
    $,
    ready: () => window.rosterLab.ready,
    chip: () => $('statusChip').textContent,
    banner: () => ($('banner').hidden ? '' : $('banner').textContent),
    teams: () => document.querySelectorAll('#teamList [data-team]').length,
    rows: () => document.querySelectorAll('#playerBody tr[data-p]').length,
    title: () => $('teamTitle').textContent,
    dialogOpen: () => $('replaceDialog').open,
    downloads: () => document.downloads.length,
    openRom: (file) => { $('romInput').files = [file]; return $('romInput').dispatchEvent(event('change')); },
    importJson: (file) => { $('jsonInput').files = [file]; return $('jsonInput').dispatchEvent(event('change')); },
    selectTeam: (t) => document.querySelector(`[data-team="${t}"]`).click(),
    name: (p) => row(p).querySelector('input[data-field="name"]').value,
    setName: (p, value) => {
      const input = row(p).querySelector('input[data-field="name"]');
      input.value = value;
      return input.dispatchEvent(event('input'));
    },
    setStat: (p, field, value) => {
      const input = row(p).querySelector(`input[data-field="${field}"]`);
      input.value = String(value);
      return input.dispatchEvent(event('input'));
    },
    stars: (p) => row(p).querySelectorAll('.pip.on').length,
    clickSkill: (p, n) => row(p).querySelector(`[data-skill="${n}"]`).click(),
    clickRating: (r, v) => document.querySelector(`[data-r="${r}"] [data-rating="${v}"]`).click(),
    setText: (key, value) => {
      const input = document.querySelector(`[data-text="${key}"]`);
      input.value = value;
      return input.dispatchEvent(event('input'));
    },
    click: (id) => $(id).click(),
    keep: () => $('keepBtn').click(),
    replace: () => $('replaceBtn').click(),
    exportRom: async () => { await $('exportRomBtn').click(); return lastDownload(); },
    exportJson: async () => { await $('exportJsonBtn').click(); return lastDownload(); },
  };
}

const diff = (a, b) => a.reduce((out, v, i) => (v === b[i] ? out : [...out, i]), []);

function draftJson(kind, edit) {
  const profile = kind === 'preview8' ? PREVIEW8 : STOCK16;
  const doc = rosterJson(profile, structuredClone(PREVIEW[kind]));
  edit?.(doc);
  return doc;
}

test('boots into the Preview 8 roster with honest counts and no ROM claims', async () => {
  const page = await boot();
  assert.equal(page.chip(), 'Preview 8 · ROSTER ONLY');
  assert.equal(page.teams(), 32);
  assert.equal(page.$('teamCount').textContent, '32');
  assert.equal(page.rows(), 15);
  assert.equal(page.$('storedBox').hidden, true, 'low teams store no extra players');
  assert.equal(page.$('identityEdit').hidden, true);
  assert.equal(page.$('identityNote').hidden, false);
  assert.equal(page.$('exportRomBtn').disabled, true);
  assert.match(page.banner(), /Get Preview 8, then Open ROM\. The file is read in this browser and never uploaded/);
  assert.equal(page.$('getRomLink').href, RELEASE);
  assert.equal(page.$('repoBtn'), null);
  assert.match(page.$('rosterHint').textContent, /^15 players/);

  await page.selectTeam(16);
  assert.equal(page.title(), 'AUSTRALIA');
  assert.match(page.$('teamEyebrow').textContent, /Team 17 \/ 32 · AUS · ASIA/);
  assert.equal(page.rows(), 15);
  assert.equal(page.$('storedBox').hidden, false);
  assert.equal(page.$('storedBody').querySelectorAll('tr').length, 5);
  assert.equal(page.$('storedBody').querySelectorAll('input').length + page.$('storedBody').querySelectorAll('button').length, 0,
    'unused records have no controls');
  await page.selectTeam(31);
  assert.equal(page.title(), 'CZECH REPUBLIC');
  await page.selectTeam(4);
  assert.equal(page.name(2), 'PARK');
  assert.equal(page.stars(2), 5, 'a stored skill of 7 shows as 5 stars');
});

test('an original ROM opens, exports unchanged, and edits touch only their bytes', async () => {
  const page = await boot();
  await page.openRom(romFile('little-league-32-team.nes', P8));
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.match(page.banner(), /the original Preview 8 ROM/);
  const unchanged = await page.exportRom();
  assert.equal(unchanged.filename, 'little-league-32-team-edited.nes');
  assert.deepEqual(diff(unchanged.bytes, P8), []);

  await page.selectTeam(16);
  await page.setName(14, 'zed!');
  assert.equal(page.name(14), 'ZED', 'input keeps only game glyphs');
  await page.setStat(14, 'speed', 3);
  await page.setStat(14, 'bat', 15);
  await page.clickRating(0, 4);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  const edited = await page.exportRom();
  assert.equal(page.dialogOpen(), false, 'export never asks');
  const rec = p8Record(16, 14);
  assert.deepEqual(diff(edited.bytes, P8), [0xfc90 + 64, rec, rec + 1, rec + 2, rec + 3, rec + 4, rec + 5, rec + 9, rec + 10]
    .filter((i) => edited.bytes[i] !== P8[i]));
  assert.equal(String.fromCharCode(...edited.bytes.slice(rec, rec + 6)), 'ZED   ');
  assert.equal(edited.bytes[rec + 10], (P8[rec + 10] & 0xf0) | 3, 'speed keeps the high nibble');
  assert.equal(edited.bytes[rec + 9] >> 4, 15);
  assert.equal(edited.bytes[0xfc90 + 64], 4);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED', 'a download does not mark the draft saved');
});

test('an edited copy opens with an honest label', async () => {
  const copy = P8.slice();
  copy.set([0x41, 0x42, 0x20, 0x20, 0x20, 0x20], lowRecord(0, 0));
  const page = await boot();
  await page.openRom(romFile('mine.nes', copy));
  assert.equal(page.chip(), 'Preview 8 · EDITED ROM');
  assert.match(page.banner(), /an edited copy of the Preview 8 ROM\. It matches the original everywhere Roster Lab doesn't edit/);
  assert.equal(page.name(0), 'AB');
});

test('the stored skill of 7 survives until someone picks a skill on purpose', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(4);
  const park = lowRecord(4, 2) + 11;
  await page.clickSkill(2, 5);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM', 'clicking the shown value changes nothing');
  assert.equal((await page.exportRom()).bytes[park], 7);
  await page.clickSkill(2, 3);
  await page.clickSkill(2, 5);
  assert.equal(page.stars(2), 5);
  assert.equal((await page.exportRom()).bytes[park], 4, 'a deliberate choice stores 0-4');
  await page.click('revertBtn');
  assert.equal((await page.exportRom()).bytes[park], 7);
});

test('a slow boot preview never replaces a ROM opened first, and its failure stays quiet', async () => {
  for (const outcome of [200, 500]) {
    const gate = deferred();
    const page = await boot({ gates: { 'roster32.json': gate }, wait: false });
    assert.equal(page.chip(), 'LOADING');
    await page.openRom(romFile('first.nes', US));
    assert.equal(page.chip(), '16-team · ORIGINAL ROM');
    gate.resolve(outcome);
    await page.ready();
    assert.equal(page.chip(), '16-team · ORIGINAL ROM');
    assert.equal(page.teams(), 16);
    assert.match(page.banner(), /Opened first\.nes/);
  }
});

test('a failed startup leaves an empty state that can open a ROM', async () => {
  const gate = deferred();
  const page = await boot({ gates: { 'teams32.json': gate }, wait: false });
  gate.resolve(404);
  await page.ready();
  assert.equal(page.chip(), 'NO ROSTER');
  assert.match(page.banner(), /Couldn't load/);
  assert.equal(page.$('exportRomBtn').disabled, true);
  await page.openRom(romFile('good.nes', P8));
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
});

test('switching sessions asks even when the new roster equals the dirty draft', async () => {
  const page = await boot();
  const edited = P8.slice();
  edited[lowRecord(0, 0)] = 'Z'.charCodeAt(0);
  await page.openRom(romFile('edited.nes', edited));
  await page.setName(0, PREVIEW.preview8[0].players[0].name);
  assert.equal(page.chip(), 'Preview 8 · EDITED ROM · UNSAVED');
  for (const load of [() => page.click('preview32Btn'), () => page.openRom(romFile('original.nes', P8))]) {
    const pending = load();
    await until(page.dialogOpen, 'same-roster session replacement prompt');
    await page.keep();
    await pending;
    assert.equal(page.chip(), 'Preview 8 · EDITED ROM · UNSAVED');
    assert.deepEqual((await page.exportRom()).bytes, P8, 'the unsaved restoration still exports');
  }
});

test('the newest file wins when reads finish backwards', async () => {
  const page = await boot();
  const first = deferred();
  const second = deferred();
  const a = page.openRom(romFile('a.nes', P8, first));
  const b = page.openRom(romFile('b.nes', US, second));
  second.resolve();
  await b;
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  first.resolve();
  await a;
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  assert.match(page.banner(), /Opened b\.nes/);
});

test('the newest file wins when hashing finishes backwards', async () => {
  const page = await boot();
  const gate = holdNextDigest();
  const a = page.openRom(romFile('a.nes', P8));
  await gate.reached.promise;
  await page.openRom(romFile('b.nes', US));
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  gate.release.resolve();
  await a;
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  assert.match(page.banner(), /Opened b\.nes/);
});

test('a stale load cannot take over the newer load\'s replace prompt', async () => {
  const page = await boot();
  await page.setName(0, 'DIRTY');
  const gate = holdNextDigest();
  const a = page.openRom(romFile('a.nes', US));
  await gate.reached.promise;
  const b = page.openRom(romFile('b.nes', P8));
  await until(page.dialogOpen, 'prompt for b');
  gate.release.resolve();
  await a;
  assert.equal(page.dialogOpen(), true, 'the older load leaves the prompt alone');
  assert.match(page.$('replaceText').textContent, /Opening b\.nes/);
  await page.replace();
  await b;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.match(page.banner(), /Opened b\.nes/);
});

test('a failed newest load keeps the session, and an older load cannot land after it', async () => {
  const page = await boot();
  await page.openRom(romFile('good.nes', P8));
  const slow = deferred();
  const older = page.openRom(romFile('older.nes', US, slow));
  const broken = P8.slice();
  broken[0x21710 + 0x140] ^= 1;
  await page.openRom(romFile('broken.nes', broken));
  assert.match(page.banner(), /Couldn't open broken\.nes\. This isn’t the Preview 8 ROM, or it has changes outside/);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  slow.resolve();
  await older;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.match(page.banner(), /Couldn't open broken\.nes/);
  await page.importJson(jsonFile('bad.json', '{not json'));
  assert.match(page.banner(), /Couldn't import bad\.json\. The file isn’t valid JSON/);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
});

test('edits made while a file loads are protected by an explicit choice', async () => {
  const page = await boot();
  await page.openRom(romFile('a.nes', P8));
  const gate = deferred();
  const loading = page.openRom(romFile('b.nes', US, gate));
  await page.setName(0, 'WHILE');
  gate.resolve();
  await until(page.dialogOpen, 'replace prompt');
  assert.match(page.$('replaceText').textContent, /Opening b\.nes replaces the edits you haven't exported/);
  await page.keep();
  await loading;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.equal(page.name(0), 'WHILE');

  const again = page.openRom(romFile('b.nes', US));
  await until(page.dialogOpen, 'second prompt');
  await page.replace();
  await again;
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  assert.equal(page.teams(), 16);
});

test('a replace answer only applies to its own load and current edits', async () => {
  const page = await boot();
  await page.setName(0, 'DIRTY');
  const b = page.openRom(romFile('b.nes', US));
  await until(page.dialogOpen, 'prompt for b');
  const gate = deferred();
  const c = page.openRom(romFile('c.nes', P8, gate));
  await b;
  assert.equal(page.dialogOpen(), false, 'a newer load withdraws the older prompt');
  assert.equal(page.chip(), 'Preview 8 · ROSTER ONLY · UNSAVED');
  gate.resolve();
  await until(page.dialogOpen, 'prompt for c');
  await page.setName(1, 'LATER');
  await page.replace();
  await until(page.dialogOpen, 'prompt again after new edits');
  await new Promise((r) => setImmediate(r));
  assert.equal(page.dialogOpen(), true, 'the first prompt closing late does not dismiss the second');
  await page.replace();
  await c;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.match(page.banner(), /Opened c\.nes/);
});

test('JSON without a ROM stays a draft; opening a ROM needs an explicit re-import', async () => {
  const page = await boot();
  const doc = draftJson('preview8', (d) => { d.teams[16].players[0].name = 'DRAFT'; });
  await page.importJson(jsonFile('draft.json', doc));
  assert.equal(page.chip(), 'Preview 8 · ROSTER ONLY · UNSAVED');
  assert.match(page.banner(), /To export a ROM, open the ROM, then import this file again/);
  assert.equal(page.$('exportRomBtn').disabled, true);
  await page.selectTeam(16);
  assert.equal(page.name(0), 'DRAFT');

  const opening = page.openRom(romFile('p8.nes', P8));
  await until(page.dialogOpen, 'prompt before dropping the draft');
  await page.replace();
  await opening;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.equal(page.name(0), 'HARRIS', 'the draft is not merged into the ROM');
  await page.importJson(jsonFile('draft.json', doc));
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.equal(page.name(0), 'DRAFT');
  const out = await page.exportRom();
  assert.equal(String.fromCharCode(...out.bytes.slice(p8Record(16, 0), p8Record(16, 0) + 6)), 'DRAFT ');
});

test('a 16-team file switches the preview, but cannot land on an open Preview 8 ROM', async () => {
  const page = await boot();
  const doc = draftJson('stock16', (d) => { d.teams[0].short_name = 'NIPPON'; });
  await page.importJson(jsonFile('us.json', doc));
  assert.equal(page.chip(), '16-team · ROSTER ONLY · UNSAVED');
  assert.equal(page.teams(), 16);
  assert.equal(page.$('identityEdit').hidden, false);
  assert.equal(page.$('shortName').value, 'NIPPON');
  assert.equal(page.$('shortName').maxLength, STOCK_SHORT_WIDTHS[0]);

  const opening = page.openRom(romFile('p8.nes', P8));
  await until(page.dialogOpen, 'prompt');
  await page.replace();
  await opening;
  await page.importJson(jsonFile('us.json', doc));
  assert.match(page.banner(), /Couldn't import us\.json\. It is a 16-team US roster, but the open ROM is Preview 8/);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.equal(page.teams(), 32);
});

test('imports keep the ROM as the baseline for Reset team and Revert', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(16);
  await page.setName(0, 'EDITED');
  await page.selectTeam(0);
  await page.clickRating(1, 1);
  const saved = await page.exportJson();
  assert.equal(saved.filename, 'p8-roster.json');
  const doc = JSON.parse(saved.text);
  assert.deepEqual([doc.format, doc.version, doc.profile, doc.source.name], ['little-league-roster', 2, 'preview8-32-v1', 'p8.nes']);
  assert.equal(doc.teams[16].players.length, 20);
  assert.equal(doc.teams[0].players.length, 15);

  await page.click('revertBtn');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  await page.importJson(jsonFile('p8-roster.json', saved.text));
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  await page.selectTeam(16);
  assert.equal(page.name(0), 'EDITED');
  await page.click('resetTeamBtn');
  assert.equal(page.name(0), 'HARRIS');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED', 'team 1 rating is still edited');
  await page.click('revertBtn');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.deepEqual(diff((await page.exportRom()).bytes, P8), []);
});

test('re-importing your own JSON keeps dirty state and export bytes', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  const clean = await page.exportJson();
  await page.importJson(jsonFile('clean.json', clean.text));
  assert.equal(page.dialogOpen(), false);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.deepEqual(diff((await page.exportRom()).bytes, P8), []);

  await page.setName(3, 'MINE');
  const before = await page.exportRom();
  const saved = await page.exportJson();
  await page.importJson(jsonFile('mine.json', saved.text));
  assert.equal(page.dialogOpen(), false, 'importing the current draft asks nothing');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.deepEqual(diff((await page.exportRom()).bytes, before.bytes), []);
});

test('imports that change read-only data are refused without touching the session', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.setName(0, 'KEPT');
  for (const [edit, reason] of [
    [(d) => { d.teams[16].players[17].name = 'GHOST'; }, /stored players the game doesn't load/],
    [(d) => { d.teams[2].name = 'ELSEWHERE'; }, /team name is built into this ROM/],
    [(d) => { d.teams[2].players[0].attrs[6] ^= 8; }, /attrs\[6\] differs/],
    [(d) => { d.teams[2].players[0].attrs[3] = 999; }, /ten whole numbers from 0 to 255/],
    [(d) => { d.teams[2].ratings = [1, 2, 3, 9]; }, /four whole numbers from 1 to 4/],
  ]) {
    await page.importJson(jsonFile('x.json', draftJson('preview8', edit)));
    assert.match(page.banner(), reason);
    assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
    assert.equal(page.name(0), 'KEPT');
  }
});

test('an old 32-team export loses only its blank padding, with a notice', async () => {
  const page = await boot();
  const legacy = {
    version: 1,
    source: 'sample',
    teams: PREVIEW.preview8.map((team, t) => ({
      id: t,
      name: team.name,
      short_name: team.name,
      short_width: 14,
      short_attr: 0,
      ratings: team.ratings,
      players: [...team.players, ...(t < 16 ? Array.from({ length: 5 }, () => ({ name: '', attrs: Array(10).fill(0) })) : [])],
    })),
  };
  legacy.teams[16].players[1].name = 'NEWGUY';
  await page.importJson(jsonFile('old.json', legacy));
  assert.match(page.banner(), /Imported old\.json .* Removed 80 blank placeholder players/);
  await page.selectTeam(0);
  assert.equal(page.rows(), 15);
  await page.selectTeam(16);
  assert.equal(page.name(1), 'NEWGUY');
});

test('16-team names edit within their stored widths', async () => {
  const page = await boot();
  await page.click('preview16Btn');
  assert.equal(page.chip(), '16-team · ROSTER ONLY');
  await page.openRom(romFile('us.nes', US));
  assert.equal(page.chip(), '16-team · ORIGINAL ROM');
  await page.setText('name', 'osaka team');
  assert.equal(page.title(), 'OSAKA TEAM');
  await page.setText('shortName', 'OSAKA OSAKA OSAKA');
  assert.equal(page.$('shortName').value, 'OSAKA OSAK', 'the input stops at the stored width');
  const out = (await page.exportRom()).bytes;
  assert.equal(String.fromCharCode(...out.slice(stockName(0), stockName(0) + 16)), 'OSAKA TEAM    \xff\xff');
  const changed = diff(out, US);
  assert.ok(changed.length > 0 && changed.every((i) => (i >= stockName(0) && i < stockName(0) + 14) || (i >= 0x52b1 && i < 0x52b1 + 10)));
});

test('switching rosters with unsaved edits asks first', async () => {
  const page = await boot();
  await page.setName(0, 'STAY');
  const switching = page.click('preview16Btn');
  await until(page.dialogOpen, 'prompt');
  assert.match(page.$('replaceText').textContent, /Switching to the 16-team US roster/);
  await page.keep();
  await switching;
  assert.equal(page.chip(), 'Preview 8 · ROSTER ONLY · UNSAVED');
  assert.equal(page.name(0), 'STAY');
});

test('the page links the pinned release and ships no ROM', () => {
  assert.ok(readFileSync(new URL('../README.md', import.meta.url), 'utf8').includes(RELEASE));
  assert.deepEqual(readdirSync(WEB, { recursive: true }).filter((f) => /\.nes$/i.test(f)), []);
  const docker = readFileSync(new URL('../Dockerfile', import.meta.url), 'utf8');
  assert.deepEqual(docker.match(/^COPY .*/gm), ['COPY web ./web', 'COPY tools/serve.py ./tools/serve.py']);
  assert.doesNotMatch(INDEX, /Repo ROM|repoBtn/);
});
