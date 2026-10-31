// Behavior tests for web/colors.js: the swatch palette, names, the strict code
// parser and the batter preview decoded from a ROM.
//
//   node --test tools/test_web_colors.mjs
//   ROSTER_ROM32=build/homerunart32.nes \
//   ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \
//   ROSTER_BATTER_JSON=/tmp/ll-webcolors-opus/proto-ui/batter.json node --test tools/test_web_colors.mjs
//
// The real-ROM case is skipped, and reported as skipped, without the ROMs. It
// renders the batter's palette roles from each ROM and compares their SHA-256
// with the role map measured during design review (kept outside the repo; set
// ROSTER_BATTER_JSON to compare against that file too). No pixels are stored here.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import {
  BASIC_COLORS, BATTER, BELOW_BLACK_NOTE, NES_RGB, batterColor, batterPicture, colorName, describeColor, hexCode,
  parseColorCode,
} from '../web/colors.js';

const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const ROLES = { 1: 'k', 2: 'J', 3: 'C', 9: 'k', 10: 's', 11: 'H', 13: 'k', 14: 'w', 15: 'g' };
/** SHA-256 of the reviewed batter role map's rows, each followed by a newline. */
const BATTER_ROLE_MAP_SHA256 = '5d901be89b3575ffaddda28d91770e3ccc2e663162ff7da7f135f179b7a94ad7';
const REAL = [
  ['ROSTER_ROM32', 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b'],
  ['ROSTER_ROM16', '58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e'],
];

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

const missing = REAL.map(([env]) => (!process.env[env] ? `set ${env}` : !existsSync(process.env[env]) ? `${env} does not exist` : null)).find(Boolean);

test('real ROMs: the batter drawn from each ROM is the reviewed role map', { skip: missing }, () => {
  const reviewed = process.env.ROSTER_BATTER_JSON && JSON.parse(readFileSync(process.env.ROSTER_BATTER_JSON, 'utf8')).rows;
  if (reviewed) assert.equal(sha256(`${reviewed.join('\n')}\n`), BATTER_ROLE_MAP_SHA256, 'the reviewed file');
  for (const [env, sha] of REAL) {
    const rom = new Uint8Array(readFileSync(process.env[env]));
    assert.equal(sha256(rom), sha, `${env} is not the accepted ROM`);
    const picture = batterPicture(rom);
    const rows = Array.from({ length: picture.height }, (_, y) =>
      Array.from(picture.pixels.subarray(y * picture.width, (y + 1) * picture.width), (e) => (e ? ROLES[e] ?? '?' : '.')).join(''));
    assert.equal(sha256(`${rows.join('\n')}\n`), BATTER_ROLE_MAP_SHA256, env);
    if (reviewed) assert.deepEqual(rows, reviewed, env);
    assert.deepEqual([1, 9, 10, 13, 14, 15].map((e) => picture.palette[e]), [0x0f, 0x0f, 0x36, 0x0f, 0x30, 0x10],
      'outline, skin, bat white and gray from the field sprite palette');
  }
});
