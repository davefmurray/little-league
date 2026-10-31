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
import {
  STOCK_SHORT_WIDTHS, fixture, lowRecord, maskedDigest, p8OwnColors, p8Record, sha256, stockColors, stockName, upgradeImage,
  writableMask,
} from './web_fixtures.mjs';
import { PREVIEW8, STOCK16, VARIANTS, previewRoster, rosterJson, sameTeams } from '../web/rom.js';
import { BASIC_COLORS, NES_RGB, batterColor, batterPicture } from '../web/colors.js';

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

const variant = (id) => VARIANTS.find((v) => v.id === id);
const SWAP = new Map([
  [maskedDigest(P8, writableMask('preview8-legacy')), variant('preview8-legacy').maskedSha256],
  [sha256(P8), variant('preview8-legacy').originalSha256],
  [maskedDigest(upgradeImage(P8), writableMask('preview8-independent-colors-v1')), variant('preview8-independent-colors-v1').maskedSha256],
  [maskedDigest(US, writableMask('stock16-native-colors-v1')), variant('stock16-native-colors-v1').maskedSha256],
  [sha256(US), variant('stock16-native-colors-v1').originalSha256],
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
    // team colors
    state: () => window.rosterLab.state,
    active: () => document.activeElement,
    colorRow: (slot) => document.querySelector(`[data-color-row="${slot}"]`),
    colorText: (slot) => document.querySelector(`[data-color-row="${slot}"] .cr-value`).textContent,
    colorLabels: () => document.querySelectorAll('#colorRows .cr-label').map((el) => el.textContent),
    pick: (slot) => document.querySelector(`[data-pick="${slot}"]`).click(),
    picker: (slot) => document.querySelector(`[data-picker="${slot}"]`),
    swatches: (slot) => document.querySelectorAll(`[data-picker="${slot}"] [role="radio"]`),
    checked: (slot) => document.querySelectorAll(`[data-picker="${slot}"] [aria-checked="true"]`).map((el) => Number(el.dataset.swatch)),
    swatch: (slot, code) => document.querySelector(`[data-picker="${slot}"] [data-swatch="${code}"]`),
    key: (key) => document.activeElement.dispatchEvent(event('keydown', { key })),
    resetColor: (slot) => document.querySelector(`[data-color-reset="${slot}"]`).click(),
    typeCode: (slot, text) => {
      const input = document.querySelector(`[data-code-input="${slot}"]`);
      input.value = text;
      input.dispatchEvent(event('input'));
      return document.querySelector(`[data-code-set="${slot}"]`).click();
    },
    announced: () => $('colorStatus').textContent,
    canvas: () => $('batterCanvas').context?.image ?? null,
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
  assert.deepEqual([doc.format, doc.version, doc.profile, doc.source.name], ['little-league-roster', 3, 'preview8-32-v1', 'p8.nes']);
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

// ---------- team colors ----------

const LEDGER = [0x3c712, 0x3c719, 0x3c71f, ...Array.from({ length: 96 }, (_, i) => 0x3f390 + i)];
const toasts = (page) => page.$('toasts').children.map((el) => el.textContent);

/** The canvas pixels the app should put for `uniform`, from the ROM's own batter. */
function batterImage(rom, uniform) {
  const picture = batterPicture(rom);
  const data = new Uint8ClampedArray(picture.width * picture.height * 4);
  picture.pixels.forEach((entry, i) => {
    if (!entry) return;
    const rgb = NES_RGB[batterColor(entry, picture.palette, uniform) & 0x3f];
    data.set([parseInt(rgb.slice(1, 3), 16), parseInt(rgb.slice(3, 5), 16), parseInt(rgb.slice(5, 7), 16), 255], 4 * i);
  });
  return data;
}

test('the team colors card shows cap and trim, jersey and hair for both layouts', async () => {
  const page = await boot();
  assert.deepEqual(page.colorLabels(), ['Cap & trim', 'Jersey', 'Hair']);
  assert.deepEqual(['cap', 'jersey', 'hair'].map(page.colorText), ['$05 (5) crimson', '$20 (32) white', '$0F (15) black']);
  assert.match(page.colorRow('cap').textContent, /Cap, helmet, socks and belt trim\./);
  assert.equal(page.colorRow('jersey').querySelector('.cr-help'), null, 'Jersey has no help text');
  assert.match(page.colorRow('hair').textContent,
    /Batter’s hair while this team bats, and hair in ending scenes\. While this team bats, the other team’s pitcher shows a little of this color too\./);
  for (const [slot, code] of [['cap', 0x05], ['jersey', 0x20], ['hair', 0x0f]]) {
    const row = page.colorRow(slot);
    assert.equal(row.querySelector('[data-chip]').getAttribute('style'), `--sw:${NES_RGB[code]}`);
    assert.equal(row.querySelector('[data-color-reset]').disabled, true);
    assert.equal(row.querySelector('[data-pick]').getAttribute('aria-expanded'), 'false');
    assert.equal(page.picker(slot).hidden, true);
    assert.equal(page.swatches(slot).length, 0, 'a closed picker leaves no focusable swatches');
  }
  assert.match(page.$('colorsCard').textContent, /Approximate NES colors/);
  await page.selectTeam(19);
  assert.equal(page.colorText('cap'), '$1B (27) sea green');
  await page.click('preview16Btn');
  assert.equal(page.chip(), '16-team · ROSTER ONLY');
  assert.deepEqual(page.colorLabels(), ['Cap & trim', 'Jersey', 'Hair']);
  await page.selectTeam(5);
  assert.deepEqual(['cap', 'jersey', 'hair'].map(page.colorText), ['$15 (21) raspberry', '$11 (17) azure', '$38 (56) cream']);
});

test('the basic picker is a 53-swatch radio group with arrows, Home, End, Enter and Escape', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(19);
  await page.pick('cap');
  const button = page.colorRow('cap').querySelector('[data-pick]');
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.equal(page.picker('cap').querySelector('[role="radiogroup"]').getAttribute('aria-label'), 'Cap & trim color');
  const radios = page.swatches('cap');
  assert.equal(radios.length, 53);
  assert.deepEqual(radios.map((r) => Number(r.dataset.swatch)), [...BASIC_COLORS]);
  assert.deepEqual(page.checked('cap'), [0x1b]);
  assert.equal(radios.filter((r) => r.getAttribute('tabindex') === '0').length, 1, 'one tab stop in the group');
  assert.equal(page.active(), page.swatch('cap', 0x1b), 'focus moves to the chosen swatch');
  assert.equal(page.swatch('cap', 0x1b).getAttribute('aria-label'), 'Cap & trim $1B (27) sea green');
  assert.equal(page.swatch('cap', 0x0f).getAttribute('aria-label'), 'Cap & trim $0F (15) black');

  await page.key('ArrowRight');
  assert.deepEqual(page.checked('cap'), [0x1c]);
  assert.equal(page.active(), page.swatch('cap', 0x1c));
  assert.equal(page.colorText('cap'), '$1C (28) teal');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.equal(page.state().teams[3].uniform.cap, 0x1b, 'the old partner keeps its color');
  for (const [key, code] of [['ArrowDown', 0x2c], ['Home', 0x20], ['End', 0x2c], ['ArrowDown', 0x3c], ['ArrowDown', 0x0f],
    ['ArrowDown', 0x0f], ['ArrowRight', 0x0f], ['ArrowUp', 0x30], ['ArrowLeft', 0x2c], ['ArrowUp', 0x1c], ['Home', 0x10], ['ArrowLeft', 0x0c]]) {
    await page.key(key);
    assert.deepEqual(page.checked('cap'), [code], `${key} -> ${code.toString(16)}`);
    assert.equal(page.active(), page.swatch('cap', code));
  }
  assert.equal(page.announced(), '', 'moving inside the group relies on each swatch\'s name');
  await page.key('Escape');
  assert.equal(page.picker('cap').hidden, true);
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  assert.equal(page.state().teams[19].uniform.cap, 0x1b, 'Escape restores the opening value');
  assert.equal(page.active(), button, 'focus returns to the row');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  assert.equal(page.announced(), 'Cap & trim back to $1B (27) sea green.');

  await page.pick('cap');
  await page.key('ArrowLeft');
  await page.key('Enter');
  assert.equal(page.picker('cap').hidden, true);
  assert.equal(page.state().teams[19].uniform.cap, 0x1a);
  assert.equal(page.active(), button);
  assert.equal(page.announced(), 'VENEZUELA Cap & trim: $1A (26) bright green.');

  await page.pick('jersey');
  await page.swatch('jersey', 0x30).click();
  assert.equal(page.state().teams[19].uniform.jersey, 0x30);
  assert.equal(page.picker('jersey').hidden, true);
  assert.equal(page.active(), page.colorRow('jersey').querySelector('[data-pick]'));
  await page.pick('hair');
  await page.pick('jersey');
  assert.equal(page.picker('hair').hidden, true, 'one picker at a time');
  assert.equal(page.picker('jersey').hidden, false);
  assert.equal(page.dialogOpen(), false);
});

test('kept color edits announce once across Advanced, picker changes and team navigation', async () => {
  const page = await boot();
  const status = page.$('colorStatus');
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(status), 'textContent');
  const messages = [];
  Object.defineProperty(status, 'textContent', {
    get() { return descriptor.get.call(this); },
    set(value) {
      if (value) messages.push(value);
      descriptor.set.call(this, value);
    },
  });
  await page.pick('cap');
  await page.typeCode('cap', '$16');
  await page.pick('jersey');
  assert.deepEqual(messages, ['JAPAN Cap & trim: $16 (22) red.']);
  await page.key('Escape');
  messages.length = 0;
  await page.pick('cap');
  await page.key('ArrowRight');
  await page.selectTeam(1);
  assert.equal(page.state().teams[0].uniform.cap, 0x17);
  assert.deepEqual(messages, ['JAPAN Cap & trim: $17 (23) burnt orange.']);
  await page.selectTeam(0);
  await page.pick('cap');
  await page.typeCode('cap', '$18');
  await page.resetColor('cap');
  const count = messages.length;
  await page.pick('hair');
  assert.equal(messages.length, count, 'closing does not repeat the reset announcement');
});

test('a stored code outside the basic grid stays the current choice and exports unchanged', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(19);
  await page.pick('jersey');
  await page.typeCode('jersey', '$3E');
  assert.equal(page.state().teams[19].uniform.jersey, 0x3e);
  assert.deepEqual(page.checked('jersey'), [0x3e]);
  assert.equal(page.swatches('jersey').length, 54);
  const out = await page.exportRom();
  assert.equal(out.bytes[p8OwnColors(19) + 1], 0x3e);

  const again = await boot();
  await again.openRom(romFile('own-colors.nes', out.bytes));
  assert.equal(again.chip(), 'Preview 8 · own team colors · EDITED ROM');
  assert.match(again.banner(), /an edited copy of the Preview 8 ROM where every team has its own colors/);
  await again.selectTeam(19);
  assert.equal(again.colorText('jersey'), '$3E (62) black, same as $0F');
  await again.pick('jersey');
  assert.equal(again.swatches('jersey').length, 54);
  assert.deepEqual(again.checked('jersey'), [0x3e]);
  assert.equal(again.swatch('jersey', 0x3e).getAttribute('aria-label'), 'Jersey $3E (62) black, same as $0F, outside the basic grid');
  await again.key('ArrowLeft');
  assert.deepEqual(again.checked('jersey'), [0x0f]);
  await again.key('ArrowRight');
  assert.deepEqual(again.checked('jersey'), [0x3e]);
  await again.key('ArrowUp');
  assert.deepEqual(again.checked('jersey'), [0x31]);
  await again.key('Escape');
  assert.equal(again.state().teams[19].uniform.jersey, 0x3e);
  assert.equal(again.chip(), 'Preview 8 · own team colors · EDITED ROM');
  assert.deepEqual(diff((await again.exportRom()).bytes, out.bytes), [], 'the stored code exports unchanged');
});

test('advanced code entry takes exact decimal or $HH codes and notes below-black inline', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.pick('hair');
  const input = page.picker('hair').querySelector('[data-code-input="hair"]');
  for (const bad of ['15junk', '1.5', '-1', '64', '$40', '', '0x0D']) {
    await page.typeCode('hair', bad);
    assert.equal(page.$('code-error-hair').hidden, false, JSON.stringify(bad));
    assert.equal(input.getAttribute('aria-invalid'), 'true');
    assert.equal(page.state().teams[0].uniform.hair, 0x0f, 'the draft keeps its last valid value');
    assert.equal(page.announced(), page.$('code-error-hair').textContent);
  }
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  await page.typeCode('hair', '$0d');
  assert.equal(page.state().teams[0].uniform.hair, 0x0d);
  assert.equal(page.$('code-error-hair').hidden, true);
  assert.equal(input.getAttribute('aria-invalid'), null);
  const warn = page.colorRow('hair').querySelector('[data-color-warn]');
  assert.equal(warn.hidden, false);
  assert.equal(warn.textContent, 'Below-black $0D can cause display issues on some original hardware; $0F is the usual black.');
  assert.equal(page.dialogOpen(), false, 'the note never asks');
  assert.equal(page.announced(), `JAPAN Hair: $0D (13) below black. ${warn.textContent}`);
  assert.equal(page.colorRow('hair').querySelector('[data-pick]').getAttribute('aria-describedby'), 'color-help-hair color-warn-hair');
  assert.deepEqual(page.checked('hair'), [0x0d], 'the exact code joins the group as the current choice');
  await page.typeCode('hair', '07');
  assert.equal(page.state().teams[0].uniform.hair, 7);
  assert.equal(warn.hidden, true);
  assert.equal(page.colorRow('hair').querySelector('[data-pick]').getAttribute('aria-describedby'), 'color-help-hair');
  assert.deepEqual(page.checked('hair'), [7]);
  input.value = '27';
  await input.dispatchEvent(event('keydown', { key: 'Enter' }));
  assert.equal(page.state().teams[0].uniform.hair, 27, 'Enter in the field uses the code');
  assert.equal(page.picker('hair').hidden, false, 'and leaves the picker open');
  const out = await page.exportRom();
  assert.equal(out.bytes[p8OwnColors(0) + 2], 27);
  assert.equal(out.bytes[p8OwnColors(16) + 2], 0x0f, 'Australia keeps the shared hair');
});

test('the preview draws the batter from the open ROM, or a labeled illustration without one', async () => {
  const page = await boot();
  assert.equal(page.$('uniformCaption').textContent, 'Illustration, not game art.');
  assert.equal(page.$('illustration').hidden, false);
  assert.equal(page.$('batterCanvas').hidden, true);
  assert.equal(page.$('uniformArt').getAttribute('role'), 'img');
  assert.equal(page.$('uniformArt').getAttribute('aria-label'),
    'JAPAN colors: cap and trim $05 (5) crimson, jersey $20 (32) white, hair $0F (15) black.');
  const fills = (part) => page.$('illustration').querySelectorAll(`[data-part="${part}"]`).map((el) => el.getAttribute('fill'));
  assert.deepEqual([fills('cap'), fills('jersey'), fills('hair')], [Array(4).fill(NES_RGB[5]), [NES_RGB[0x20]], [NES_RGB[0x0f]]],
    'cap, brim, belt and socks wear the cap color');
  await page.pick('jersey');
  await page.key('ArrowLeft');
  assert.deepEqual(fills('jersey'), [NES_RGB[0x1c]], 'the illustration follows each choice');
  assert.match(page.$('uniformArt').getAttribute('aria-label'), /jersey \$1C \(28\) teal/);

  const withRom = await boot();
  await withRom.openRom(romFile('p8.nes', P8));
  assert.equal(withRom.$('uniformCaption').textContent, 'Batter at the plate, drawn from your ROM. Colors approximate.');
  assert.equal(withRom.$('batterCanvas').hidden, false);
  assert.equal(withRom.$('illustration').hidden, true);
  const japan = PREVIEW.preview8[0].uniform;
  assert.deepEqual(withRom.canvas().data, batterImage(P8, japan));
  await withRom.pick('cap');
  await withRom.key('ArrowRight');
  assert.deepEqual(withRom.canvas().data, batterImage(P8, { ...japan, cap: 0x06 }), 'redrawn at once');
  assert.equal(withRom.active(), withRom.swatch('cap', 0x06), 'focus stays on the swatch');
  await withRom.setName(3, 'FOCUS');
  assert.equal(withRom.picker('cap').hidden, false, 'a roster edit leaves the picker open');
  assert.equal(withRom.active(), withRom.swatch('cap', 0x06));
  await withRom.key('Enter');
  assert.equal(withRom.announced(), 'JAPAN Cap & trim: $06 (6) dark red.');
  assert.equal(withRom.$('colorStatus').getAttribute('aria-live'), 'polite');
  await withRom.selectTeam(16);
  assert.deepEqual(withRom.canvas().data, batterImage(P8, PREVIEW.preview8[16].uniform), 'Australia keeps the shared colors');
});

test('the export note appears only while an export will give teams their own colors', async () => {
  const page = await boot();
  assert.equal(page.$('upgradeNote').hidden, true, 'no note without a ROM');
  await page.pick('cap');
  await page.key('ArrowRight');
  assert.equal(page.$('upgradeNote').hidden, true, 'a preview session exports no ROM');
  await page.key('Escape');
  await page.openRom(romFile('p8.nes', P8));
  assert.equal(page.$('upgradeNote').hidden, true);
  await page.setName(0, 'ROSTER');
  assert.equal(page.$('upgradeNote').hidden, true, 'roster edits need no note');
  const rosterOnly = await page.exportRom();
  assert.ok(diff(rosterOnly.bytes, P8).every((i) => i >= lowRecord(0, 0) && i < lowRecord(0, 0) + 6), 'no upgrade bytes');
  assert.match(toasts(page).at(-1), /with your edits\.$/);
  await page.selectTeam(17);
  await page.pick('cap');
  await page.key('ArrowRight');
  await page.key('Enter');
  const note = page.$('upgradeNote');
  assert.equal(note.hidden, false);
  assert.equal(note.querySelector('p').textContent, 'This export gives all 32 teams their own colors.');
  assert.match(note.querySelector('details').textContent, /99 bytes in all/, 'byte counts sit in the optional details');
  const out = await page.exportRom();
  assert.equal(page.dialogOpen(), false, 'exports never ask');
  assert.match(toasts(page).at(-1), /with your edits\. In this copy all 32 teams have their own colors\.$/);
  assert.deepEqual(diff(out.bytes, P8).filter((i) => i < lowRecord(0, 0) || i >= lowRecord(0, 0) + 6), LEDGER.filter((i) => out.bytes[i] !== P8[i]));
  await page.selectTeam(16);
  await page.selectTeam(17);
  assert.equal(note.hidden, false, 'the note is about the export, whichever team is shown');
  await page.resetColor('cap');
  assert.equal(note.hidden, true, 'colors back at the baseline need no upgrade');

  const own = await boot();
  await own.openRom(romFile('own.nes', out.bytes));
  await own.pick('jersey');
  await own.key('ArrowRight');
  assert.equal(own.$('upgradeNote').hidden, true, 'an upgraded ROM already gives every team its own colors');
  const ownOut = await own.exportRom();
  assert.deepEqual(diff(ownOut.bytes, out.bytes), [p8OwnColors(0) + 1]);
  assert.doesNotMatch(toasts(own).at(-1), /own colors/);

  const us = await boot();
  await us.openRom(romFile('us.nes', US));
  await us.selectTeam(5);
  await us.pick('jersey');
  await us.swatch('jersey', 0x30).click();
  assert.equal(us.$('upgradeNote').hidden, true, 'the 16-team ROM has a record per team');
  assert.deepEqual(diff((await us.exportRom()).bytes, US), [stockColors(5) + 1]);
});

test('the colors card adds its own styles and leaves the rating overflow repair alone', () => {
  const css = read('styles.css');
  assert.match(css, /\.ratings \{\n  --focus: var\(--cream\);\n  display: grid;\n  grid-template-columns: repeat\(auto-fit, minmax\(min\(100%, 190px\), 1fr\)\);\n/);
  assert.match(css, /\n  \.rating \{ flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: space-between; \}\n/);
  assert.doesNotMatch(css.match(/@media \(max-width: 1080px\) \{[\s\S]*?\n\}/)[0], /\.ratings/);
  assert.match(css, /\.picker \{[^}]*overflow-x: auto;/, 'the picker scrolls inside its box on narrow screens');
  assert.match(css, /\.swatches \{[^}]*grid-template-columns: repeat\(13, minmax\(24px, 1fr\)\);[^}]*max-width: calc\(13 \* 30px \+ 12 \* 4px\);/,
    'swatches stay between 24px and 30px');
  assert.match(css, /\.cr-value \{[^}]*overflow-wrap: anywhere;/, 'long color names wrap');
  assert.match(css, /\.sw-btn\[aria-checked="true"\]::after \{\n  content: "\\2713";/, 'the chosen swatch shows a check mark');
});

test('a roster file without colors keeps your color edits and says so', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(20);
  await page.pick('cap');
  for (const [slot, code] of [['cap', '1'], ['jersey', '33'], ['hair', '$07']]) {
    if (page.picker(slot).hidden) await page.pick(slot);
    await page.typeCode(slot, code);
  }
  assert.deepEqual(page.state().teams[20].uniform, { cap: 1, jersey: 33, hair: 7 });
  const v2 = draftJson('preview8', (d) => {
    d.version = 2;
    delete d.palette;
    for (const team of d.teams) delete team.uniform;
    d.teams[2].players[0].name = 'TESTER';
  });
  const importing = page.importJson(jsonFile('v2.json', v2));
  await until(page.dialogOpen, 'replace prompt for the unsaved edits');
  await page.replace();
  await importing;
  assert.deepEqual(page.state().teams[20].uniform, { cap: 1, jersey: 33, hair: 7 }, 'dirty colors kept');
  assert.equal(page.state().teams[2].players[0].name, 'TESTER', 'roster applied');
  assert.match(page.banner(), /Imported v2\.json into the open ROM\. It has no team colors, so your color edits stay\./);
  const out = await page.exportRom();
  assert.deepEqual([...out.bytes.subarray(p8OwnColors(20), p8OwnColors(20) + 3)], [1, 33, 7]);
  assert.deepEqual([...out.bytes.subarray(p8OwnColors(4), p8OwnColors(4) + 3)], [...P8.subarray(0x3fad0 + 12, 0x3fad0 + 15)]);

  const extract = {
    rom: 'old.nes',
    teams: draftJson('preview8', (d) => { d.teams[2].players[0].name = 'TESTER'; }).teams
      .map(({ uniform, ...team }) => ({ ...team, colors: { primary: 0x30, secondary: 0x16 } })),
  };
  await page.importJson(jsonFile('extract.json', extract));
  assert.match(page.banner(), /Ignored the old two-color fields; they don’t match the game’s cap, jersey and hair records\./);
  assert.deepEqual(page.state().teams[20].uniform, { cap: 1, jersey: 33, hair: 7 }, 'primary and secondary never become colors');
  const v1 = { version: 1, teams: draftJson('preview8').teams };
  await page.importJson(jsonFile('v1.json', v1));
  assert.match(page.banner(), /Couldn't import v1\.json\. Team colors need roster version 3\./);
});

test('row Reset, Reset team and Revert return colors to the baseline across imports and exports', async () => {
  const page = await boot();
  await page.openRom(romFile('p8.nes', P8));
  await page.selectTeam(3);
  await page.pick('cap');
  await page.key('ArrowRight');
  await page.key('Enter');
  await page.pick('jersey');
  await page.key('ArrowLeft');
  await page.key('Enter');
  assert.deepEqual(page.state().teams[3].uniform, { cap: 0x1c, jersey: 0x2a, hair: 0x0f });
  assert.equal(page.colorRow('cap').querySelector('[data-color-reset]').disabled, false);
  page.colorRow('cap').querySelector('[data-color-reset]').focus();
  await page.resetColor('cap');
  assert.equal(page.active(), page.colorRow('cap').querySelector('[data-pick]'), 'Reset moves focus to the enabled color control');
  assert.deepEqual(page.state().teams[3].uniform, { cap: 0x1b, jersey: 0x2a, hair: 0x0f }, 'a row reset touches one slot');
  assert.equal(page.colorRow('cap').querySelector('[data-color-reset]').disabled, true);
  assert.equal(page.announced(), 'Cap & trim reset to $1B (27) sea green.');
  const saved = await page.exportJson();
  const doc = JSON.parse(saved.text);
  assert.deepEqual([doc.version, doc.palette, doc.source.variant], [3, 'nes-2c02-6bit-v1', 'preview8-legacy']);
  assert.deepEqual(doc.teams[3].uniform, { cap: 0x1b, jersey: 0x2a, hair: 0x0f });
  assert.deepEqual(doc.teams[19].uniform, { cap: 0x1b, jersey: 0x2b, hair: 0x0f });
  await page.exportRom();
  await page.click('revertBtn');
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  await page.importJson(jsonFile('saved.json', saved.text));
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.equal(page.colorText('jersey'), '$2A (42) light green');
  await page.click('resetTeamBtn');
  assert.deepEqual(page.state().teams[3].uniform, { cap: 0x1b, jersey: 0x2b, hair: 0x0f });
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM');
  await page.importJson(jsonFile('saved.json', saved.text));
  await page.exportRom();
  await page.click('revertBtn');
  assert.deepEqual(diff((await page.exportRom()).bytes, P8), []);
  assert.equal(new Set(page.state().teams.map((t) => t.uniform)).size, 32, 'no two teams share a color object');
  assert.ok(page.state().session.baseline.every((t, i) => sameTeams(t.uniform, PREVIEW.preview8[i].uniform)), 'the baseline never changed');
});

test('color edits made while a file loads keep the replace prompt honest', async () => {
  const page = await boot();
  await page.openRom(romFile('a.nes', P8));
  const gate = deferred();
  const loading = page.openRom(romFile('b.nes', US, gate));
  await page.pick('hair');
  await page.key('ArrowUp');
  await page.key('Enter');
  gate.resolve();
  await until(page.dialogOpen, 'replace prompt');
  await page.keep();
  await loading;
  assert.equal(page.state().teams[0].uniform.hair, 0x30);
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');

  const again = page.openRom(romFile('b.nes', US));
  await until(page.dialogOpen, 'second prompt');
  await page.pick('cap');
  await page.typeCode('cap', '$16');
  await page.replace();
  await until(page.dialogOpen, 'the prompt returns after a new color edit');
  assert.equal(page.state().teams[0].uniform.cap, 0x16);
  await page.keep();
  await again;
  assert.equal(page.chip(), 'Preview 8 · ORIGINAL ROM · UNSAVED');
  assert.equal(page.state().teams[0].uniform.cap, 0x16);
});

test('the page links the pinned release and ships no ROM', () => {
  assert.ok(readFileSync(new URL('../README.md', import.meta.url), 'utf8').includes(RELEASE));
  assert.deepEqual(readdirSync(WEB, { recursive: true }).filter((f) => /\.nes$/i.test(f)), []);
  const docker = readFileSync(new URL('../Dockerfile', import.meta.url), 'utf8');
  assert.deepEqual(docker.match(/^COPY .*/gm), ['COPY web ./web', 'COPY tools/serve.py ./tools/serve.py']);
  assert.doesNotMatch(INDEX, /Repo ROM|repoBtn/);
});
