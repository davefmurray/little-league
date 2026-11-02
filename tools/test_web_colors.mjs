// Behavior tests for web/colors.js: the swatch palette, names, the strict code
// parser and the batter preview decoded from a ROM.
//
//   node --test tools/test_web_colors.mjs
//   ROSTER_ROM32=build/homerunart32.nes \
//   ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
//   ROSTER_BATTER_JSON=/tmp/roster-lab-comps/batter.json node --test tools/test_web_colors.mjs
//
// The real-ROM cases are skipped, and reported as skipped, without the ROMs.
// They render the batter's palette roles from each ROM and compare their
// SHA-256 with the role map of the approved workspace design; set
// ROSTER_BATTER_JSON to compare every pixel and the palette record against
// that design's decode too. They also check that the page's bundled batter,
// web/assets/game/batter.json, equals each ROM's decode and that
// tools/build_batter_asset.mjs rebuilds it byte for byte. Without ROMs, the
// bundled batter is still checked against the approved role map.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import {
  BASIC_COLORS, BATTER, BELOW_BLACK_NOTE, NES_RGB, batterColor, batterPicture, colorName, describeColor, hexCode,
  parseColorCode, readBatterAsset,
} from '../web/colors.js';
import { batterAssetText } from './build_batter_asset.mjs';

const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const ROLES = { 1: 'k', 2: 'J', 3: 'C', 9: 'k', 10: 's', 11: 'H', 13: 'k', 14: 'w', 15: 'g' };
/** SHA-256 of the approved batter role map's rows, each followed by a newline. */
const BATTER_ROLE_MAP_SHA256 = 'd37bcdaa806348e5f01823271d5e9009e34d60034bbc6dbba746e90153517af9';
const REAL = [
  ['ROSTER_ROM32', 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b'],
  ['ROSTER_ROM16', '58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e'],
];
const BATTER_FILE = new URL('../web/assets/game/batter.json', import.meta.url);
const roleRows = (picture) => Array.from({ length: picture.height }, (_, y) =>
  Array.from(picture.pixels.subarray(y * picture.width, (y + 1) * picture.width), (e) => (e ? ROLES[e] ?? '?' : '.')).join(''));
/** RGB bytes for a picture in `uniform`, clear pixels zero: what the page puts on its canvas. */
const render = (picture, uniform) => Buffer.from(Array.from(picture.pixels, (e) => {
  const rgb = NES_RGB[batterColor(e, picture.palette, uniform) & 0x3f];
  return e ? [1, 3, 5].map((at) => parseInt(rgb.slice(at, at + 2), 16)) : [0, 0, 0];
}).flat());

test('swatch colors are the repo\'s FCEUX table, expanded the same way', () => {
  const source = readFileSync(new URL('./menu32_convert.py', import.meta.url), 'utf8');
  const table = source.match(/FCEUX_6BIT = \(([\s\S]*?)\n\)/)[1];
  const triples = [...table.matchAll(/\((\d+), (\d+), (\d+)\)/g)].map((m) => m.slice(1, 4).map(Number));
  assert.equal(triples.length, 64);
  const expanded = triples.map((rgb) => `#${rgb.map((v) => ((v << 2) | (v >> 4)).toString(16).padStart(2, '0')).join('')}`);
  assert.deepEqual([...NES_RGB], expanded);
  assert.ok(Object.isFrozen(NES_RGB));
});

test('every code has a name, and aliases say what they alias', () => {
  for (let code = 0; code < 64; code++) assert.ok(colorName(code), hexCode(code));
  assert.equal(colorName(0x0f), 'black');
  assert.equal(colorName(0x0d), 'below black');
  for (const alias of [0x0e, 0x1d, 0x1e, 0x1f, 0x2e, 0x2f, 0x3e, 0x3f]) assert.equal(colorName(alias), 'black, same as $0F');
  assert.equal(colorName(0x20), 'white');
  assert.equal(colorName(0x30), 'white, same as $20');
  assert.match(colorName(0x2d), /gray, varies by TV/);
  assert.match(colorName(0x3d), /light gray, varies by TV/);
  assert.equal(describeColor(0x1b), '$1B (27) sea green');
  assert.equal(hexCode(5), '$05');
  assert.match(BELOW_BLACK_NOTE, /^Below-black \$0D can cause display issues on some original hardware; \$0F is the usual black\.$/);
});

test('the basic grid is 52 hues plus black $0F, with no alias or below-black code', () => {
  assert.equal(BASIC_COLORS.length, 53);
  assert.equal(new Set(BASIC_COLORS).size, 53);
  for (let row = 0; row < 4; row++) {
    assert.deepEqual(BASIC_COLORS.slice(13 * row, 13 * row + 13), Array.from({ length: 13 }, (_, c) => 16 * row + c));
  }
  assert.equal(BASIC_COLORS[52], 0x0f);
  assert.ok(!BASIC_COLORS.some((c) => c === 0x0d || (c & 0x0f) >= 0x0d && c !== 0x0f));
});

test('exact codes parse strictly: decimal or $HH from 0 to 63, nothing else', () => {
  for (const [text, value] of [['0', 0], ['7', 7], ['07', 7], ['63', 63], ['$3F', 63], ['$3f', 63], ['$0d', 13], ['$D', 13], [' 27 ', 27], ['$1B', 27]]) {
    assert.deepEqual(parseColorCode(text), { value }, text);
  }
  for (const text of ['', '$', '27x', 'x27', '1.5', '-1', '+1', '0x1B', '1e1', '1 2', '$1G', '$100', '063', 'NaN', '٣']) {
    assert.match(parseColorCode(text).error, /^Type a code from 0 to 63, or \$00 to \$3F\.$/, JSON.stringify(text));
  }
  for (const text of ['64', '99', '$40', '$FF']) assert.match(parseColorCode(text).error, /is past the last NES color code, 63 \(\$3F\)/, text);
});

test('the batter decodes sprites with flips and priority, and colors only its three team slots', () => {
  const rom = new Uint8Array(16 + 16 * 0x4000 + 16 * 0x2000);
  rom.set([0x4e, 0x45, 0x53, 0x1a, 16, 16, 0x10]);
  const chr = 16 + 16 * 0x4000 + BATTER.chrBank * 0x1000;
  // Every tile: color 1 at its top-left pixel and color 2 along its bottom row.
  for (let tile = 0; tile < 256; tile++) {
    rom[chr + 16 * tile] = 0x80;
    rom[chr + 16 * tile + 8 + 7] = 0xff;
  }
  const record = 16 + 15 * 0x4000 + BATTER.paletteRecord - 0xc000;
  rom.set(Array.from({ length: 16 }, (_, i) => 0x20 + i), record);
  const picture = batterPicture(rom);
  assert.deepEqual([picture.width, picture.height], [49, 58]);
  assert.deepEqual(picture.palette, Array.from({ length: 16 }, (_, i) => 0x20 + i));
  const expected = new Uint8Array(49 * 58);
  for (const [x, y, , attr] of [...BATTER.sprites].reverse()) {
    const put = (px, py, color) => {
      if (px >= 0 && px < 49 && py >= 0 && py < 58) expected[py * 49 + px] = 4 * (attr & 3) + color;
    };
    for (let c = 0; c < 8; c++) put(x + c, y + 7, 2);
    put(attr & 0x40 ? x + 7 : x, y, 1);
  }
  assert.deepEqual(picture.pixels, expected);
  const uniform = { cap: 0x16, jersey: 0x30, hair: 0x38 };
  assert.deepEqual([2, 3, 11].map((e) => batterColor(e, picture.palette, uniform)), [0x30, 0x16, 0x38]);
  assert.deepEqual([1, 9, 10, 13, 14, 15].map((e) => batterColor(e, picture.palette, uniform)), [0x21, 0x29, 0x2a, 0x2d, 0x2e, 0x2f]);
  assert.ok(BATTER.sprites.every((s) => Object.isFrozen(s) && s.length === 4));
});

test('the bundled batter is the approved role map with the field palette, and needs no ROM', () => {
  const doc = JSON.parse(readFileSync(BATTER_FILE, 'utf8'));
  const picture = readBatterAsset(doc);
  assert.deepEqual([picture.width, picture.height], [BATTER.width, BATTER.height]);
  assert.ok(picture.pixels instanceof Uint8Array && picture.pixels.length === BATTER.width * BATTER.height);
  assert.equal(sha256(`${roleRows(picture).join('\n')}\n`), BATTER_ROLE_MAP_SHA256);
  assert.deepEqual([1, 9, 10, 13, 14, 15].map((e) => picture.palette[e]), [0x0f, 0x0f, 0x36, 0x0f, 0x30, 0x10]);
  assert.equal(doc.source.sha256, REAL[0][1], 'decoded from the pinned Preview 8 ROM');
  const base = { cap: 0x05, jersey: 0x20, hair: 0x0f };
  const before = render(picture, base);
  for (const [slot, entry] of [['jersey', 2], ['cap', 3], ['hair', 11]]) {
    const after = render(picture, { ...base, [slot]: 0x16 });
    const changed = [...picture.pixels.keys()].filter((i) => !before.subarray(3 * i, 3 * i + 3).equals(after.subarray(3 * i, 3 * i + 3)));
    const owned = [...picture.pixels.keys()].filter((i) => picture.pixels[i] === entry);
    assert.ok(owned.length > 0, `${slot} has pixels`);
    assert.deepEqual(changed, owned, `${slot} recolors exactly its own pixels`);
  }
});

test('the batter reader refuses anything but a 49 x 58 picture of palette entries', () => {
  const doc = JSON.parse(readFileSync(BATTER_FILE, 'utf8'));
  for (const [why, edit] of [
    ['format', (d) => { d.format = 'roster-lab-sprite'; }],
    ['version', (d) => { d.version = 2; }],
    ['width', (d) => { d.width = 48; }],
    ['height', (d) => { d.height = 57; }],
    ['a row short', (d) => { d.rows.pop(); }],
    ['a short row', (d) => { d.rows[3] = d.rows[3].slice(1); }],
    ['clear is ".", never 0', (d) => { d.rows[3] = `0${d.rows[3].slice(1)}`; }],
    ['not hex', (d) => { d.rows[3] = `g${d.rows[3].slice(1)}`; }],
    ['color 0 of a sprite palette', (d) => { d.rows[3] = `4${d.rows[3].slice(1)}`; }],
    ['upper-case hex', (d) => { d.rows[3] = `F${d.rows[3].slice(1)}`; }],
    ['15 palette bytes', (d) => { d.palette.pop(); }],
    ['palette byte past 255', (d) => { d.palette[0] = 256; }],
    ['fractional palette byte', (d) => { d.palette[0] = 1.5; }],
    ['palette byte as text', (d) => { d.palette[0] = '15'; }],
  ]) {
    const bad = structuredClone(doc);
    edit(bad);
    assert.throws(() => readBatterAsset(bad), /^Error: The batter file is not a 49 x 58 batter picture\.$/, why);
  }
  for (const bad of [null, undefined, [], 'batter']) assert.throws(() => readBatterAsset(bad), /49 x 58/);
});

const missing = REAL.map(([env]) => (!process.env[env] ? `set ${env}` : !existsSync(process.env[env]) ? `${env} does not exist` : null)).find(Boolean);

test('real ROMs: the batter drawn from each ROM is the approved role map, without the field markers', { skip: missing }, () => {
  const approved = process.env.ROSTER_BATTER_JSON && JSON.parse(readFileSync(process.env.ROSTER_BATTER_JSON, 'utf8'));
  assert.ok(BATTER.sprites.every(([, , tile]) => tile !== 0xfd && tile !== 0xff), 'overlay tiles $FD and $FF are not batter sprites');
  for (const [env, sha] of REAL) {
    const rom = new Uint8Array(readFileSync(process.env[env]));
    assert.equal(sha256(rom), sha, `${env} is not the accepted ROM`);
    const picture = batterPicture(rom);
    assert.equal(sha256(`${roleRows(picture).join('\n')}\n`), BATTER_ROLE_MAP_SHA256, env);
    if (approved) {
      assert.deepEqual([picture.width, picture.height], [approved.width, approved.height], env);
      assert.deepEqual([...picture.pixels], approved.pixels, `${env} pixels match the approved decode`);
      assert.deepEqual(picture.palette, approved.palette, `${env} palette record matches the approved decode`);
    }
    assert.deepEqual([1, 9, 10, 13, 14, 15].map((e) => picture.palette[e]), [0x0f, 0x0f, 0x36, 0x0f, 0x30, 0x10],
      'outline, skin, bat white and gray from the field sprite palette');
  }
});

test('real ROMs: the bundled batter equals each ROM decode, recolors the same, and rebuilds byte for byte', { skip: missing }, () => {
  const text = readFileSync(BATTER_FILE, 'utf8');
  const bundled = readBatterAsset(JSON.parse(text));
  const uniforms = Array.from({ length: 64 }, (_, c) => ({ cap: c, jersey: 63 - c, hair: (7 * c) & 63 }));
  for (const [env, sha] of REAL) {
    const rom = new Uint8Array(readFileSync(process.env[env]));
    assert.equal(sha256(rom), sha, `${env} is not the accepted ROM`);
    const decoded = batterPicture(rom);
    assert.deepEqual([bundled.width, bundled.height], [decoded.width, decoded.height], env);
    assert.ok(Buffer.from(bundled.pixels).equals(Buffer.from(decoded.pixels)), `${env}: every pixel`);
    assert.deepEqual(bundled.palette, decoded.palette, `${env}: palette record`);
    for (const uniform of uniforms) assert.ok(render(bundled, uniform).equals(render(decoded, uniform)), `${env}: ${JSON.stringify(uniform)}`);
  }
  assert.equal(batterAssetText(new Uint8Array(readFileSync(process.env.ROSTER_ROM32))), text, 'the builder reproduces the committed file');
  assert.throws(() => batterAssetText(new Uint8Array(readFileSync(process.env.ROSTER_ROM16))), /Expected the Preview 8 ROM/);
});
