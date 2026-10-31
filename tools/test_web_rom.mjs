// Behavior tests for web/rom.js.
//
//   node --test tools/test_web_rom.mjs
//   ROSTER_ROM32=build/homerunart32.nes \
//   ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' node --test tools/test_web_rom.mjs
//
// Synthetic images always run. The real-ROM cases are skipped, and reported as
// skipped, unless the two environment variables point at the ROMs.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import {
  ACTIVE_PLAYERS, PALETTE, PREVIEW8, PROFILES, STOCK16, UNIFORM_SLOTS, VARIANTS, fitRoster, needsColorUpgrade, openRom,
  previewRoster, readRom, readRosterFile, rosterJson, sameTeams, skillStars, writeRom,
} from '../web/rom.js';
import {
  LAYOUTS, OWN_TABLE, ROUTINE, ROUTINE_AS_BUILT, ROUTINE_OWN_COLORS, SPARE, STOCK_SHORT_WIDTHS, UPGRADE_CONSTANTS, fixture,
  maskedDigest, p8Code, p8Name, p8OwnColors, p8Record, p8SharedColors, sha256, stockColors, stockName, stockRating,
  stockShortPointer, stockShortText, upgradeImage, writableMask,
} from './web_fixtures.mjs';

const WEB = fileURLToPath(new URL('../web/', import.meta.url));
const webJson = (name) => JSON.parse(readFileSync(`${WEB}${name}`, 'utf8'));
const clone = (v) => structuredClone(v);
const pad2 = (n) => String(n).padStart(2, '0');
const prg = (bank, cpu) => 16 + bank * 0x4000 + cpu - (bank === 15 ? 0xc000 : 0x8000);

/** The judge's digests (review §5): each variant's mask over the original file, or over its upgrade. */
const JUDGE_DIGESTS = {
  'preview8-legacy': '26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586',
  'preview8-independent-colors-v1': '430000e74c40123c3b404b19858eed507154c3a9843e5963b5ca1ee405050ca7',
  'stock16-native-colors-v1': 'aa7a1e270e6300c6f0bc39be64d9180fe23cf9cb6ec70514d6d854209ccdb2d3',
};
/** The 16-team digest before team colors became writable; the native-colors variant admits a superset. */
const STOCK16_ROSTER_ONLY_DIGEST = '6f4fbd41e6a7235596aef7ce8c13877b1df96731a9a5e21ce4a04268ca176b2a';
const REAL = {
  preview8: { env: 'ROSTER_ROM32', sha: 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b', profile: PREVIEW8, variant: 'preview8-legacy' },
  stock16: { env: 'ROSTER_ROM16', sha: '58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e', profile: STOCK16, variant: 'stock16-native-colors-v1' },
};
const SOURCE_VARIANT = { preview8: 'preview8-legacy', stock16: 'stock16-native-colors-v1' };

function realSubject(kind) {
  const path = process.env[REAL[kind].env];
  if (!path) return { kind, skip: `set ${REAL[kind].env} to run against the real ROM` };
  if (!existsSync(path)) return { kind, skip: `${REAL[kind].env}=${path} does not exist` };
  const bytes = new Uint8Array(readFileSync(path));
  assert.equal(sha256(bytes), REAL[kind].sha, `${path} is not the accepted ${kind} ROM`);
  return { kind, bytes, profile: REAL[kind].profile, variants: VARIANTS, real: true };
}

const SUBJECTS = [
  { name: 'synthetic Preview 8', get: () => ({ kind: 'preview8', ...fixture('preview8') }) },
  { name: 'synthetic 16-team', get: () => ({ kind: 'stock16', ...fixture('stock16') }) },
  { name: 'real Preview 8', get: () => realSubject('preview8') },
  { name: 'real 16-team US', get: () => realSubject('stock16') },
];

function diff(a, b) {
  const out = [];
  for (let i = 0; i < Math.max(a.length, b.length); i++) if (a[i] !== b[i]) out.push(i);
  return out;
}

function assertBytes(actual, expected, label) {
  const at = diff(actual, expected);
  assert.equal(at.length, 0, `${label}: ${at.length} bytes differ, first at 0x${(at[0] ?? 0).toString(16)}`);
}

function writeAscii(bytes, off, width, text) {
  for (let i = 0; i < width; i++) bytes[off + i] = i < text.length ? text.charCodeAt(i) : 0x20;
}

/** Apply `edit(team, t, expected, layout)` to every team and check the exported bytes exactly. */
async function exportMatches(subject, opened, edit) {
  const layout = LAYOUTS[subject.kind];
  const teams = clone(opened.teams);
  const expected = subject.bytes.slice();
  teams.forEach((team, t) => edit(team, t, expected, layout));
  const before = subject.bytes.slice();
  const out = await writeRom(subject.bytes, subject.profile, opened.teams, teams, subject.variants);
  assertBytes(subject.bytes, before, 'source buffer');
  assertBytes(out, expected, 'export');
  const mask = writableMask(SOURCE_VARIANT[subject.kind]);
  assert.ok(diff(out, subject.bytes).every((i) => ((out[i] ^ subject.bytes[i]) & ~mask[i] & 0xff) === 0), 'changed bits stay writable');
  const reopened = await readRom(out, subject.variants);
  assert.equal(reopened.variant, SOURCE_VARIANT[subject.kind], 'roster edits never change the ROM variant');
  assert.equal(reopened.exact, false);
  assert.ok(sameTeams(reopened.teams, teams), 'export reopens as the edited roster');
  return out;
}

function eachActive(team, fn) {
  team.players.slice(0, ACTIVE_PLAYERS).forEach((player, p) => fn(player, p));
}

for (const { name, get } of SUBJECTS) {
  const subject = get();
  const opts = subject.skip ? { skip: subject.skip } : {};
  const isP8 = subject.kind === 'preview8';
  const open = () => readRom(subject.bytes, subject.variants);

  test(`${name}: admits the file and reads every stored record`, opts, async () => {
    const rom = await open();
    assert.equal(rom.profile.id, subject.profile.id);
    assert.equal(rom.variant, SOURCE_VARIANT[subject.kind]);
    assert.equal(rom.exact, true);
    assert.equal(rom.sha256, sha256(subject.bytes));
    const layout = LAYOUTS[subject.kind];
    assert.equal(rom.teams.length, layout.teams);
    rom.teams.forEach((team, t) => {
      assert.equal(team.id, t);
      assert.equal(team.players.length, layout.stored(t));
      team.players.forEach((player, p) => {
        const rec = layout.record(t, p);
        assert.deepEqual(player.attrs, Array.from(subject.bytes.slice(rec + 6, rec + 16)));
        assert.equal(player.name.padEnd(6), Buffer.from(subject.bytes.slice(rec, rec + 6)).toString('latin1'));
      });
      assert.deepEqual(team.ratings, Array.from(subject.bytes.slice(layout.rating(t), layout.rating(t) + 4)));
    });
    assert.equal(rom.teams[4].players[2].attrs[5], 7, 'the source skill 7 is kept as stored');
    assert.equal(skillStars(rom.teams[4].players[2].attrs[5]), 5);
    if (subject.real) {
      assert.equal(rom.teams[4].players[2].name, 'PARK');
      assert.deepEqual(await openRom(subject.bytes).then((r) => [r.profile, r.exact]), [subject.profile, true]);
    } else {
      await assert.rejects(openRom(subject.bytes), /isn’t the .* ROM/, 'production profiles never admit a synthetic image');
    }
  });

  test(`${name}: an unchanged export and JSON round trip are byte-identical`, opts, async () => {
    const rom = await open();
    const before = subject.bytes.slice();
    assertBytes(await writeRom(subject.bytes, subject.profile, rom.teams, clone(rom.teams), subject.variants), subject.bytes, 'no-op export');
    const text = JSON.stringify(rosterJson(subject.profile, rom.teams, { name: 'x.nes' }));
    const teams = fitRoster(readRosterFile(JSON.parse(text)), rom.teams);
    assert.ok(sameTeams(teams, rom.teams));
    assertBytes(await writeRom(subject.bytes, subject.profile, rom.teams, teams, subject.variants), subject.bytes, 'JSON round trip export');
    assertBytes(subject.bytes, before, 'source buffer');
  });

  test(`${name}: each editable field writes only its own bits on every active player`, opts, async () => {
    const rom = await open();
    await exportMatches(subject, rom, (team, t, expected, layout) => eachActive(team, (player, p) => {
      player.name = `N${pad2(t)}${String.fromCharCode(65 + p)}${p % 2 ? '' : 'Z'}`;
      writeAscii(expected, layout.record(t, p), 6, player.name);
    }));
    for (const [field, update] of [
      ['batting', (v) => (((v >> 4) ^ 0x0f) << 4) | (v & 0x0f)],
      ['pitching', (v) => (v & 0xf0) | ((v & 0x0f) ^ 0x0f)],
    ]) {
      const out = await exportMatches(subject, rom, (team, t, expected, layout) => eachActive(team, (player, p) => {
        player.attrs[3] = update(player.attrs[3]);
        expected[layout.record(t, p) + 9] = player.attrs[3];
      }));
      assert.ok(out, field);
    }
    await exportMatches(subject, rom, (team, t, expected, layout) => eachActive(team, (player, p) => {
      player.attrs[4] = (player.attrs[4] & 0xf0) | ((player.attrs[4] & 0x0f) ^ 0x0f);
      expected[layout.record(t, p) + 10] = player.attrs[4];
    }));
    await exportMatches(subject, rom, (team, t, expected, layout) => eachActive(team, (player, p) => {
      player.attrs[5] = player.attrs[5] === 7 ? 0 : (player.attrs[5] + 1) % 5;
      expected[layout.record(t, p) + 11] = player.attrs[5];
    }));
    await exportMatches(subject, rom, (team, t, expected, layout) => {
      team.ratings = team.ratings.map((v) => (v % 4) + 1);
      expected.set(team.ratings, layout.rating(t));
    });
  });

  test(`${name}: single edits land on the right team block`, opts, async () => {
    const rom = await open();
    await exportMatches(subject, rom, (team, t, expected, layout) => {
      if (t !== 15) return;
      team.players[14].name = 'LAST15';
      writeAscii(expected, layout.record(15, 14), 6, 'LAST15');
    });
    if (isP8) {
      const out = await exportMatches(subject, rom, (team, t, expected) => {
        if (t !== 16) return;
        team.players[14].attrs[3] ^= 0x10;
        expected[p8Record(16, 14) + 9] = team.players[14].attrs[3];
      });
      assert.deepEqual(diff(out, subject.bytes), [0x21710 + 14 * 16 + 9]);
      const live = await exportMatches(subject, rom, (team, t, expected) => {
        if (t !== 31) return;
        team.ratings[3] = (team.ratings[3] % 4) + 1;
        expected[0xfc90 + 31 * 4 + 3] = team.ratings[3];
      });
      assert.deepEqual(diff(live, subject.bytes), [0xfd0f]);
      assert.deepEqual(live.slice(stockRating(0), stockRating(16)), subject.bytes.slice(stockRating(0), stockRating(16)), 'the unused 16-team rating table stays');
    }
  });

  test(`${name}: an export that does not read back as the draft is refused`, opts, async () => {
    const rom = await open();
    const edited = clone(rom.teams);
    edited[0].players[0].name = 'XYZ';
    await assert.rejects(writeRom(subject.bytes, subject.profile, edited, edited, subject.variants), /baseline doesn’t describe the open ROM/,
      'a baseline that does not describe the file cannot hide an edit');
    const wrongColors = clone(rom.teams);
    wrongColors[0].uniform.cap ^= 1;
    await assert.rejects(writeRom(subject.bytes, subject.profile, wrongColors, rom.teams, subject.variants), /baseline doesn’t describe the open ROM/,
      'a mismatched color baseline cannot upgrade an unchanged source');
  });

  test(`${name}: read-only bits and records refuse to change`, opts, async () => {
    const rom = await open();
    const refuse = async (edit, pattern) => {
      const teams = clone(rom.teams);
      edit(teams);
      await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams, subject.variants), pattern);
      assert.throws(() => fitRoster(readRosterFile(rosterJson(subject.profile, teams)), rom.teams), pattern);
    };
    await refuse((teams) => { teams[3].players[2].attrs[4] ^= 0x10; }, /only name, skill, batting, pitching and speed/);
    for (const a of [0, 1, 2, 6, 7, 8, 9]) {
      await refuse((teams) => { teams[1].players[1].attrs[a] ^= 1; }, new RegExp(`attrs\\[${a}\\] differs`));
    }
    await refuse((teams) => { teams[0].players.push(clone(teams[0].players[0])); }, /expected 15 players/);
    if (isP8) {
      await refuse((teams) => { teams[16].players[15].name = 'UNUSED'; }, /stored players the game doesn't load/);
      await refuse((teams) => { teams[31].players[19].attrs[5] ^= 1; }, /stored players the game doesn't load/);
      await refuse((teams) => { teams[2].name = 'RENAMED'; }, /team name is built into this ROM/);
      await refuse((teams) => { teams[20].code = 'ZZZ'; }, /team code is built into this ROM/);
      await refuse((teams) => { teams[9].region = 'MARS'; }, /team region is built into this ROM/);
    }
  });

  test(`${name}: field values outside the game's ranges are refused`, opts, async () => {
    const rom = await open();
    const refuse = async (edit, pattern) => {
      const teams = clone(rom.teams);
      edit(teams);
      await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams, subject.variants), pattern);
    };
    await refuse((teams) => { teams[0].players[0].name = 'lower'; }, /names are up to 6 letters/);
    await refuse((teams) => { teams[0].players[0].name = 'TOOLONG'; }, /names are up to 6 letters/);
    await refuse((teams) => { teams[0].players[0].name = 'TRAIL '; }, /names are up to 6 letters/);
    await refuse((teams) => { teams[0].players[0].name = 'A.B'; }, /names are up to 6 letters/);
    await refuse((teams) => { teams[0].players[0].attrs[5] = 5; }, /skill 5 is out of range/);
    await refuse((teams) => { teams[0].players[0].attrs[5] = 7; }, /skill 7 is out of range/);
    await refuse((teams) => { teams[4].players[2].attrs[5] = 6; }, /skill 6 is out of range/);
    await refuse((teams) => { teams[1].ratings[0] = 0; }, /four whole numbers from 1 to 4/);
    await refuse((teams) => { teams[1].ratings[0] = 2.5; }, /four whole numbers from 1 to 4/);
    await refuse((teams) => { teams[1].players[3].attrs[3] = 256; }, /ten whole numbers from 0 to 255/);
  });

  test(`${name}: the source skill exception survives and can be edited deliberately`, opts, async () => {
    const rom = await open();
    const park = LAYOUTS[subject.kind].record(4, 2) + 11;
    const edited = clone(rom.teams);
    edited[4].players[2].attrs[5] = 2;
    const out = await writeRom(subject.bytes, subject.profile, rom.teams, edited, subject.variants);
    assert.deepEqual(diff(out, subject.bytes), [park]);
    assert.equal(out[park], 2);
    const reopened = await readRom(out, subject.variants);
    assert.throws(
      () => fitRoster(readRosterFile(rosterJson(subject.profile, rom.teams)), reopened.teams),
      /skill exception can only be kept unchanged/);
    await assert.rejects(writeRom(out, subject.profile, reopened.teams, rom.teams, subject.variants),
      /skill exception can only be kept unchanged/);
    assertBytes(await writeRom(out, subject.profile, reopened.teams, reopened.teams, subject.variants), out, 'unchanged edited export');
    const stray = rosterJson(subject.profile, rom.teams);
    stray.teams[4].players[3].attrs[5] = 7;
    assert.throws(() => fitRoster(readRosterFile(stray), rom.teams), /skill 7 is out of range/);
  });

  test(`${name}: files with changes outside the editable fields are refused`, opts, async () => {
    const refuse = async (mutate, pattern) => {
      const bytes = mutate(subject.bytes.slice()) ?? null;
      await assert.rejects(readRom(bytes, subject.variants), pattern);
    };
    const flip = (off, bits = 1) => (b) => { b[off] ^= bits; return b; };
    const notThisRom = /isn’t the .* ROM, or it has changes outside/;
    const layout = LAYOUTS[subject.kind];
    await refuse(flip(7, 0x08), /NES 2.0/);
    await refuse(flip(7, 0x04), /nonstandard headers/);
    await refuse(flip(6, 0x04), /trainer/);
    await refuse(flip(6, 0x10), /mapper 0/);
    await refuse(flip(4, 0x01), /neither/);
    await refuse((b) => b.slice(0, -1), /truncated or carry extra data/);
    await refuse((b) => { const out = new Uint8Array(b.length + 1); out.set(b); return out; }, /truncated or carry extra data/);
    await refuse((b) => b.slice(0, 15), /isn’t an NES ROM/);
    await refuse(flip(0), /isn’t an NES ROM/);
    await refuse(flip(8), notThisRom);
    await refuse(flip(layout.record(3, 2) + 10, 0x10), notThisRom);
    await refuse(flip(layout.record(3, 2) + 12, 0x08), notThisRom);
    await refuse(flip(layout.record(7, 14) + 16), notThisRom);
    await refuse(flip(layout.rating(0) - 1), notThisRom);
    await refuse(flip(layout.size - 0x20000), notThisRom);
    if (isP8) {
      for (const [label, off] of [
        ['cache entry $FC4A', prg(15, 0xfc4a)],
        ['low-pointer restore $FF00', prg(15, 0xff00)],
        ['centered-name pointer $BE70', prg(1, 0xbe70)],
        ['Analysis rating reader $BD47', prg(3, 0xbd46) + 1],
        ['first CHR byte', 16 + 16 * 0x4000],
        ['unused record name', p8Record(16, 15)],
        ['pitcher trailer', 0x21710 + 0x140],
        ['old 16-team ratings', stockRating(5)],
        ['team name', p8Name(18)],
        ['bracket code', p8Code(25)],
        ['lineup $FD80', prg(15, 0xfd80)],
      ]) await refuse(flip(off), notThisRom).catch((err) => assert.fail(`${label}: ${err.message}`));
    } else {
      await refuse(flip(stockShortPointer(4)), notThisRom);
      await refuse(flip(stockShortText(4) + STOCK_SHORT_WIDTHS[4]), notThisRom);
      await refuse(flip(stockShortText(4) - 1), notThisRom);
      await refuse(flip(stockName(9) + 14), notThisRom);
    }
    const value = async (off, byte, pattern) => refuse((b) => { b[off] = byte; return b; }, pattern);
    await value(layout.record(2, 5), 0xff, /names are up to 6 letters/);
    await value(layout.record(2, 5) + 3, 0x61, /names are up to 6 letters/);
    await value(layout.record(2, 5) + 11, 0xff, /skill 255 is out of range/);
    await value(layout.record(4, 3) + 11, 7, /skill 7 is out of range/);
    await value(layout.rating(6) + 2, 0, /four whole numbers from 1 to 4/);
    await value(layout.rating(6) + 2, 5, /four whole numbers from 1 to 4/);
    if (!isP8) {
      await value(stockName(3) + 2, 0x2e, /name must be up to 14/);
      await value(stockShortText(3) + 1, 0x00, /short name must be up to 14/);
    }
  });

  if (subject.kind === 'stock16') {
    test(`${name}: team and scoreboard names stay inside their stored widths`, opts, async () => {
      const rom = await open();
      const out = await exportMatches(subject, rom, (team, t, expected) => {
        team.name = `CITY ${t}`.padEnd(t % 3 ? 7 : 14, 'X');
        writeAscii(expected, stockName(t), 14, team.name);
        team.shortName = 'S'.repeat(STOCK_SHORT_WIDTHS[t]);
        writeAscii(expected, stockShortText(t), STOCK_SHORT_WIDTHS[t], team.shortName);
      });
      for (let t = 0; t < 16; t++) {
        assert.deepEqual([out[stockName(t) + 14], out[stockName(t) + 15]], [0xff, 0xff]);
        assert.equal(out[stockShortText(t) + STOCK_SHORT_WIDTHS[t]], 0xff);
        assert.equal(out[stockShortText(t) - 1], subject.bytes[stockShortText(t) - 1]);
      }
      const refuse = async (edit, pattern) => {
        const teams = clone(rom.teams);
        edit(teams);
        await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams, subject.variants), pattern);
      };
      await refuse((teams) => { teams[0].shortName = 'S'.repeat(STOCK_SHORT_WIDTHS[0] + 1); }, /short name must be up to 10/);
      await refuse((teams) => { teams[0].name = 'N'.repeat(15); }, /name must be up to 14/);
      await refuse((teams) => { teams[0].name = 'Japan'; }, /name must be up to 14/);
    });
  }

  test(`${name}: roster files keep or refuse data without guessing`, opts, async () => {
    const rom = await open();
    const base = () => rosterJson(subject.profile, rom.teams, { name: 'x.nes', sha256: 'claimed' });
    const fit = (doc) => fitRoster(readRosterFile(doc), rom.teams);
    assert.ok(sameTeams(fit(JSON.parse(JSON.stringify(base()))), rom.teams));

    const claims = base();
    claims.permissions = { all: true };
    claims.teams[0].editable = true;
    claims.teams[0].short_width = 99;
    claims.teams[0].active = 20;
    claims.teams[0].players[0].readonly = false;
    assert.ok(sameTeams(fit(claims), rom.teams), 'permission claims in a file are ignored');

    const refuse = (edit, pattern) => {
      const doc = base();
      edit(doc);
      assert.throws(() => fit(doc), pattern);
    };
    refuse((d) => { d.version = 4; }, /version isn’t supported/);
    refuse((d) => { d.version = 2; }, /Team colors need roster version 3/);
    refuse((d) => { d.profile = 'historical-32x20'; }, /Unknown roster layout/);
    refuse((d) => { d.profile = 'toString'; }, /Unknown roster layout/);
    refuse((d) => { d.teams.pop(); }, /Expected \d+ teams/);
    refuse((d) => { [d.teams[0], d.teams[1]] = [d.teams[1], d.teams[0]]; }, /teams must be listed in order/);
    refuse((d) => { d.teams[1].id = 0; }, /teams must be listed in order/);
    refuse((d) => { d.teams[2].players.pop(); }, /expected 15 players, found 14/);
    refuse((d) => { delete d.teams[2].players; }, /players are missing/);
    refuse((d) => { delete d.teams[2].ratings; }, /ratings are missing/);
    refuse((d) => { d.teams[2].ratings = [1, 2, 3]; }, /four whole numbers/);
    refuse((d) => { d.teams[2].ratings[1] = '3'; }, /four whole numbers/);
    refuse((d) => { d.teams[2].players[0].attrs[3] = 2.7; }, /ten whole numbers/);
    refuse((d) => { d.teams[2].players[0].attrs[3] = 'X'; }, /ten whole numbers/);
    refuse((d) => { d.teams[2].players[0].attrs[3] = -1; }, /ten whole numbers/);
    refuse((d) => { d.teams[2].players[0].attrs.pop(); }, /ten whole numbers/);
    refuse((d) => { delete d.teams[2].players[0].attrs; }, /attrs are missing/);
    refuse((d) => { d.teams[2].players[0].name = 'abc'; }, /capital letters/);
    refuse((d) => { delete d.teams[2].players[0].name; }, /capital letters/);
    refuse((d) => { d.teams[2].players[0].attrs[5] = 9; }, /skill 9 is out of range/);
    refuse((d) => { d.teams[2].players[0].attrs[0] ^= 1; }, /attrs\[0\] differs/);

    const padded = base();
    padded.teams[1].players[2].name = `${padded.teams[1].players[2].name.slice(0, 3)}   `;
    assert.equal(fit(padded)[1].players[2].name, padded.teams[1].players[2].name.trimEnd(), 'stored padding is canonicalized');

    if (isP8) {
      const read = readRosterFile(rosterJson(STOCK16, rom.teams.slice(0, 16)));
      assert.equal(read.profile, STOCK16);
      assert.throws(() => fitRoster(read, rom.teams), /for the original 16-team layout, not the open one/);
    }

    if (isP8) {
      const partial = base();
      for (const team of partial.teams) { delete team.code; delete team.region; }
      assert.ok(sameTeams(fit(partial), rom.teams), 'missing identity comes from the open roster');
    } else {
      const partial = base();
      for (const team of partial.teams) delete team.short_name;
      const teams = fit(partial);
      assert.deepEqual(teams.map((t) => t.shortName), rom.teams.map((t) => t.shortName), 'missing scoreboard names are kept, never blanked');
      const legacy = { version: 1, teams: base().teams };
      for (const team of legacy.teams) { team.short_name = ''; delete team.uniform; }
      assert.deepEqual(fit(legacy).map((t) => t.shortName), rom.teams.map((t) => t.shortName), 'legacy empty scoreboard names keep the baseline');
      const explicit = base();
      for (const team of explicit.teams) team.short_name = '';
      assert.ok(fit(explicit).every((t) => t.shortName === ''), 'version 2 still supports intentional empty names');
    }
  });

  if (isP8) {
    test(`${name}: legacy 32-team files drop only the old blank padding`, opts, async () => {
      const rom = await open();
      const legacy = () => ({
        version: 1,
        source: 'old editor',
        teams: rom.teams.map((team, t) => ({
          id: t,
          name: team.name,
          short_name: team.name.slice(0, 3),
          short_width: 3,
          short_attr: 0,
          ratings: [...team.ratings],
          players: [
            ...team.players.map((p) => ({ name: p.name.padEnd(6), attrs: [...p.attrs] })),
            ...(t < 16 ? Array.from({ length: 5 }, () => ({ name: '', attrs: Array(10).fill(0) })) : []),
          ],
        })),
      });
      const read = readRosterFile(legacy());
      assert.deepEqual(read.notices, ['Removed 80 blank placeholder players that an older editor added to the original 16 teams.']);
      assert.ok(sameTeams(fitRoster(read, rom.teams), rom.teams));

      const nonblank = legacy();
      nonblank.teams[3].players[17].name = 'KEEPME';
      assert.throws(() => readRosterFile(nonblank), /Team 4 .* has 20 players, but Preview 8 stores 15 .* can’t be converted/);
      const zeroish = legacy();
      zeroish.teams[0].players[19].attrs[9] = 1;
      assert.throws(() => readRosterFile(zeroish), /can’t be converted/);
      const v2 = rosterJson(PREVIEW8, rom.teams);
      v2.teams[0].players.push(...Array.from({ length: 5 }, () => ({ name: '', attrs: Array(10).fill(0) })));
      assert.throws(() => readRosterFile(v2), /expected 15 players, found 20/, 'version 2 files get no padding migration');
      const highShort = legacy();
      highShort.teams[20].players.pop();
      assert.throws(() => readRosterFile(highShort), /expected 20 players, found 19/);
      const renamed = legacy();
      renamed.teams[17].name = 'CUBA LIBRE';
      assert.throws(() => fitRoster(readRosterFile(renamed), rom.teams), /team name is built into this ROM/);
    });
  }
}

// ---------- team colors ----------

const ALIASES = [0x0d, 0x0e, 0x0f, 0x1d, 0x1e, 0x1f, 0x2e, 0x2f, 0x3e, 0x3f, 0x20, 0x30, 0x2d, 0x3d];
const range = (start, end) => Array.from({ length: end - start }, (_, i) => start + i);
const LEDGER = [...UPGRADE_CONSTANTS, ...range(OWN_TABLE[0], OWN_TABLE[1])];
const OWN = 'preview8-independent-colors-v1';
const VENEZUELA = { cap: 0x16, jersey: 0x30, hair: 0x38 };
const VENEZUELA_SHA = 'f861d9674507165d371676e431e05351b36045fedd5546fadd2fed8cb17521b2';
const SEEDED_SHA = 'dbb5c3da49b1463290da4a77f42e0c34ce20487fdbd05cc1cd268455068dea6f';
const uniformAt = (bytes, off) => ({ cap: bytes[off], jersey: bytes[off + 1], hair: bytes[off + 2] });
const recolor = (teams, t, uniform) => {
  const out = clone(teams);
  out[t].uniform = { ...out[t].uniform, ...uniform };
  return out;
};
const colorsAt = (variant) => ({ 'preview8-legacy': p8SharedColors, [OWN]: p8OwnColors, 'stock16-native-colors-v1': stockColors })[variant];
const objects = (teams) => new Set(teams.map((t) => t.uniform)).size;

for (const { name, get } of SUBJECTS) {
  const subject = get();
  const opts = subject.skip ? { skip: subject.skip } : {};
  const isP8 = subject.kind === 'preview8';
  const open = () => readRom(subject.bytes, subject.variants);
  const exportOf = (source, baseline, teams) => writeRom(source, subject.profile, baseline, teams, subject.variants);

  test(`${name}: team colors read from the variant's own records, one object per team`, opts, async () => {
    const rom = await open();
    const at = colorsAt(SOURCE_VARIANT[subject.kind]);
    rom.teams.forEach((team, t) => assert.deepEqual(team.uniform, uniformAt(subject.bytes, at(t)), `team ${t + 1}`));
    assert.deepEqual(Object.keys(rom.teams[0].uniform), UNIFORM_SLOTS);
    assert.equal(objects(rom.teams), rom.teams.length, 'no two teams share a color object');
    if (isP8) assert.ok(rom.teams.slice(0, 16).every((team, t) => sameTeams(team.uniform, rom.teams[t + 16].uniform)), 'as built, team t + 16 wears team t\'s record');
    if (subject.real) {
      assert.deepEqual(rom.teams[3].uniform, { cap: 0x1b, jersey: 0x2b, hair: 0x0f });
      assert.equal(sha256(await exportOf(subject.bytes, rom.teams, clone(rom.teams))), REAL[subject.kind].sha);
    }
  });

  test(`${name}: ROMs exported before team colors open unchanged with their native colors`, opts, async () => {
    const rom = await open();
    const layout = LAYOUTS[subject.kind];
    const older = subject.bytes.slice();
    writeAscii(older, layout.record(isP8 ? 20 : 9, 1), 6, 'OLDED');
    older[layout.rating(isP8 ? 31 : 15)] = (older[layout.rating(isP8 ? 31 : 15)] % 4) + 1;
    older[layout.record(2, 3) + 9] ^= 0x5a;
    const reopened = await readRom(older, subject.variants);
    assert.equal(reopened.variant, SOURCE_VARIANT[subject.kind]);
    assert.ok(sameTeams(reopened.teams.map((t) => t.uniform), rom.teams.map((t) => t.uniform)), 'colors equal the native records');
    assertBytes(await exportOf(older, reopened.teams, clone(reopened.teams)), older, 'unchanged export');
    const more = clone(reopened.teams);
    more[0].players[0].name = 'MORE';
    const out = await exportOf(older, reopened.teams, more);
    assert.deepEqual(diff(out, older), range(layout.record(0, 0), layout.record(0, 0) + 6).filter((i) => out[i] !== older[i]));
  });

  if (isP8) {
    test(`${name}: a color edit on as-built Preview 8 adds exactly the 99-byte upgrade`, opts, async () => {
      const rom = await open();
      const before = subject.bytes.slice();
      const out = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 19, VENEZUELA));
      assertBytes(subject.bytes, before, 'source buffer');
      assert.deepEqual(diff(out, subject.bytes), LEDGER, 'the three constants and the 96-byte table');
      assert.equal(Buffer.from(out.subarray(ROUTINE, ROUTINE + 21)).toString('hex'), ROUTINE_OWN_COLORS);
      if (subject.real) assert.equal(sha256(out), VENEZUELA_SHA);
      const up = await readRom(out, subject.variants);
      assert.equal(up.variant, OWN);
      assert.equal(up.exact, false);
      assert.deepEqual(up.teams[19].uniform, VENEZUELA);
      assert.deepEqual(up.teams[3].uniform, rom.teams[3].uniform, 'the old partner keeps its colors');
      up.teams.forEach((team, t) => t === 19 || assert.deepEqual(team.uniform, rom.teams[t].uniform));
      assert.deepEqual(diff(upgradeImage(subject.bytes), out), range(p8OwnColors(19), p8OwnColors(19) + 3).filter((i) => out[i] !== upgradeImage(subject.bytes)[i]),
        'the table is seeded from the source records and only team 20 differs');

      const low = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 3, { cap: 0x16 }));
      assert.deepEqual(diff(low, subject.bytes), LEDGER, 'a low-team edit adds the same 99 bytes');
      const lowUp = await readRom(low, subject.variants);
      assert.deepEqual(lowUp.teams[19].uniform, rom.teams[19].uniform, 'team 20 keeps the shared colors');
      assert.equal(lowUp.teams[3].uniform.cap, 0x16);
      assertBytes(low.subarray(p8SharedColors(3), p8SharedColors(3) + 3), subject.bytes.subarray(p8SharedColors(3), p8SharedColors(3) + 3),
        'the old shared record stays as built');
    });

    test(`${name}: restoring colors or editing only the roster never upgrades`, opts, async () => {
      const rom = await open();
      const restored = recolor(recolor(rom.teams, 19, VENEZUELA), 19, rom.teams[19].uniform);
      assertBytes(await exportOf(subject.bytes, rom.teams, restored), subject.bytes, 'color changed and changed back');
      assert.equal(needsColorUpgrade(SOURCE_VARIANT.preview8, rom.teams, restored), false);
      const roster = clone(rom.teams);
      roster[25].players[4].name = 'ROSTER';
      const out = await exportOf(subject.bytes, rom.teams, roster);
      assert.deepEqual(diff(out, subject.bytes), range(p8Record(25, 4), p8Record(25, 4) + 6).filter((i) => out[i] !== subject.bytes[i]));
      assert.equal((await readRom(out, subject.variants)).variant, 'preview8-legacy');
      assert.equal(needsColorUpgrade(SOURCE_VARIANT.preview8, rom.teams, roster), false);
      assert.equal(needsColorUpgrade(SOURCE_VARIANT.preview8, rom.teams, recolor(rom.teams, 0, { hair: 0x30 })), true);
    });

    test(`${name}: an upgraded copy exports byte for byte, one slot at a time, and never downgrades`, opts, async () => {
      const rom = await open();
      const up = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 19, VENEZUELA));
      const upRom = await readRom(up, subject.variants);
      assertBytes(await exportOf(up, upRom.teams, clone(upRom.teams)), up, 'no-op export');
      assert.equal(needsColorUpgrade(OWN, upRom.teams, recolor(upRom.teams, 1, { cap: 0x01 })), false);
      await Promise.all(range(0, 96).map(async (i) => {
        const [t, s] = [Math.floor(i / 3), i % 3];
        const value = upRom.teams[t].uniform[UNIFORM_SLOTS[s]] ^ 0x21;
        const out = await exportOf(up, upRom.teams, recolor(upRom.teams, t, { [UNIFORM_SLOTS[s]]: value }));
        assert.deepEqual(diff(out, up), [p8OwnColors(t) + s], `team ${t + 1} ${UNIFORM_SLOTS[s]}`);
        assert.equal(out[p8OwnColors(t) + s], value);
      }));
      const donor = recolor(upRom.teams, 19, rom.teams[19].uniform);
      const back = await exportOf(up, upRom.teams, donor);
      assert.deepEqual(diff(back, up), range(p8OwnColors(19), p8OwnColors(19) + 3).filter((i) => back[i] !== up[i]), 'only team 20\'s bytes');
      assert.equal((await readRom(back, subject.variants)).variant, OWN, 'colors equal to the old partners keep the upgrade');
      assert.deepEqual(back.subarray(ROUTINE, ROUTINE + 21), up.subarray(ROUTINE, ROUTINE + 21));
      if (subject.real) assert.equal(sha256(back), SEEDED_SHA, 'the seeded image the designs measured');
      const seeded = await readRom(back, subject.variants);
      assertBytes(await exportOf(back, seeded.teams, clone(seeded.teams)), back, 'an upgraded source whose partners match exports unchanged');
    });

    test(`${name}: each team's colors land in its own record and its old partner keeps theirs`, opts, async () => {
      const rom = await open();
      const up = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 0, { cap: rom.teams[0].uniform.cap ^ 1 }));
      const upRom = await readRom(up, subject.variants);
      for (let t = 0; t < 32; t++) {
        const fresh = { cap: (t + 1) & 0x3f, jersey: (t * 2 + 0x21) & 0x3f, hair: (63 - t) & 0x3f };
        const legacyOut = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, t, fresh));
        assert.ok(diff(legacyOut, subject.bytes).every((i) => LEDGER.includes(i)), `team ${t + 1}: only ledger bytes`);
        const legacyBack = await readRom(legacyOut, subject.variants);
        assert.deepEqual(legacyBack.teams[t].uniform, fresh);
        assert.deepEqual(legacyBack.teams[t ^ 16].uniform, rom.teams[t ^ 16].uniform, `team ${(t ^ 16) + 1} keeps its colors`);
        const upOut = await exportOf(up, upRom.teams, recolor(upRom.teams, t, fresh));
        assert.deepEqual(diff(upOut, up), range(p8OwnColors(t), p8OwnColors(t) + 3).filter((i) => upOut[i] !== up[i]), `team ${t + 1} upgraded`);
      }
    });

    test(`${name}: an upgrade keeps roster edits already in the source`, opts, async () => {
      const rom = await open();
      const roster = clone(rom.teams);
      roster[16].players[0].name = 'KEPT';
      roster[31].ratings = roster[31].ratings.map((v) => (v % 4) + 1);
      const edited = await exportOf(subject.bytes, rom.teams, roster);
      const editedRom = await readRom(edited, subject.variants);
      assert.equal(editedRom.variant, 'preview8-legacy');
      const out = await exportOf(edited, editedRom.teams, recolor(editedRom.teams, 16, { jersey: 0x2d }));
      assert.deepEqual(diff(out, edited), LEDGER.filter((i) => out[i] !== edited[i]));
      const back = await readRom(out, subject.variants);
      assert.equal(back.teams[16].players[0].name, 'KEPT');
      assert.deepEqual(back.teams[31].ratings, roster[31].ratings);
      assert.equal(back.teams[16].uniform.jersey, 0x2d);
      assert.deepEqual(back.teams[0].uniform, rom.teams[0].uniform);
    });

    test(`${name}: code, table and spare-space bytes refuse admission in either variant`, opts, async () => {
      const rom = await open();
      const up = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 19, VENEZUELA));
      const notThisRom = /isn’t the .* ROM, or it has changes outside/;
      const refuse = async (label, bytes, mutate) => {
        const copy = bytes.slice();
        mutate(copy);
        await assert.rejects(readRom(copy, subject.variants), notThisRom, label);
      };
      for (const [label, image] of [['as built', subject.bytes], ['upgraded', up]]) {
        for (let i = 0; i < 21; i++) {
          for (let bit = 0; bit < 8; bit++) await refuse(`${label} routine byte ${i} bit ${bit}`, image, (b) => { b[ROUTINE + i] ^= 1 << bit; });
        }
        for (const off of [...range(SPARE[0], OWN_TABLE[0]), ...range(OWN_TABLE[1], SPARE[1])]) {
          await refuse(`${label} spare byte 0x${off.toString(16)}`, image, (b) => { b[off] ^= 0x01; });
        }
        await refuse(`${label} header`, image, (b) => { b[9] ^= 1; });
        await refuse(`${label} CHR`, image, (b) => { b[image.length - 0x1000] ^= 1; });
        await refuse(`${label} color pointer $FFF4`, image, (b) => { b[0x40004] ^= 1; });
      }
      const asBuilt = Uint8Array.from(Buffer.from(ROUTINE_AS_BUILT, 'hex'));
      const own = Uint8Array.from(Buffer.from(ROUTINE_OWN_COLORS, 'hex'));
      for (const at of UPGRADE_CONSTANTS) {
        await refuse(`only constant 0x${at.toString(16)} upgraded`, subject.bytes, (b) => { b[at] = own[at - ROUTINE]; });
        await refuse(`only constant 0x${at.toString(16)} reverted`, up, (b) => { b[at] = asBuilt[at - ROUTINE]; });
      }
      await refuse('table filled but routine as built', subject.bytes, (b) => b.set(up.subarray(OWN_TABLE[0], OWN_TABLE[1]), OWN_TABLE[0]));
      await refuse('routine upgraded but table empty', subject.bytes, (b) => b.set(own, ROUTINE));
      for (const off of [OWN_TABLE[0], OWN_TABLE[0] + 47, OWN_TABLE[1] - 1]) {
        await refuse(`as-built table byte 0x${off.toString(16)} not $FF`, subject.bytes, (b) => { b[off] = 0x0f; });
        await refuse(`upgraded table byte 0x${off.toString(16)} bit 6`, up, (b) => { b[off] |= 0x40; });
        await refuse(`upgraded table byte 0x${off.toString(16)} bit 7`, up, (b) => { b[off] |= 0x80; });
        await refuse(`upgraded table byte 0x${off.toString(16)} $FF`, up, (b) => { b[off] = 0xff; });
      }
      for (const off of [p8SharedColors(0), p8SharedColors(3) + 2, p8SharedColors(15) + 2]) {
        await refuse(`upgraded old shared record 0x${off.toString(16)}`, up, (b) => { b[off] ^= 0x01; });
        await refuse(`as-built shared record 0x${off.toString(16)}`, subject.bytes, (b) => { b[off] ^= 0x01; });
      }
      const both = [maskedDigest(up, writableMask('preview8-legacy')), maskedDigest(up, writableMask(OWN))];
      assert.deepEqual(both.map((d) => subject.variants.filter((v) => v.maskedSha256 === d).map((v) => v.id)), [[], [OWN]],
        'the upgraded copy matches exactly one variant');
      const asBuiltDigests = [maskedDigest(subject.bytes, writableMask('preview8-legacy')), maskedDigest(subject.bytes, writableMask(OWN))];
      assert.deepEqual(asBuiltDigests.map((d) => subject.variants.filter((v) => v.maskedSha256 === d).map((v) => v.id)), [['preview8-legacy'], []]);
    });
  } else {
    test(`${name}: each color byte writes in place, with no upgrade`, opts, async () => {
      const rom = await open();
      const out = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, 5, { jersey: 0x30 }));
      assert.deepEqual(diff(out, subject.bytes), [0x1fae0]);
      await Promise.all(range(0, 48).map(async (i) => {
        const [t, s] = [Math.floor(i / 3), i % 3];
        const value = rom.teams[t].uniform[UNIFORM_SLOTS[s]] ^ 0x33;
        const edited = await exportOf(subject.bytes, rom.teams, recolor(rom.teams, t, { [UNIFORM_SLOTS[s]]: value }));
        assert.deepEqual(diff(edited, subject.bytes), [stockColors(t) + s], `team ${t + 1} ${UNIFORM_SLOTS[s]}`);
      }));
      const reopened = await readRom(out, subject.variants);
      assert.equal(reopened.variant, 'stock16-native-colors-v1');
      assert.equal(reopened.teams[5].uniform.jersey, 0x30);
      for (let i = 0; i < 21; i++) {
        const bad = subject.bytes.slice();
        bad[0x1c70e + i] ^= 0x10;
        await assert.rejects(readRom(bad, subject.variants), /isn’t the .* ROM, or it has changes outside/, `routine byte ${i}`);
      }
      for (const [off, bits] of [[stockColors(0), 0x40], [stockColors(15) + 2, 0x80], [stockColors(16), 0x01], [stockColors(0) - 1, 0x01]]) {
        const bad = subject.bytes.slice();
        bad[off] ^= bits;
        await assert.rejects(readRom(bad, subject.variants), /isn’t the .* ROM, or it has changes outside/, `0x${off.toString(16)}`);
      }
      if (subject.real) {
        assert.equal(maskedDigest(subject.bytes, writableMask('stock16-native-colors-v1')), JUDGE_DIGESTS['stock16-native-colors-v1']);
        const rosterOnly = writableMask('stock16-native-colors-v1').map((m, i) => (i >= stockColors(0) && i < stockColors(16) ? 0 : m));
        assert.equal(maskedDigest(subject.bytes, rosterOnly), STOCK16_ROSTER_ONLY_DIGEST, 'the old 16-team digest is the same image with colors pinned');
      }
    });
  }

  test(`${name}: every code 0-63, black aliases and below-black round-trip exactly`, opts, async () => {
    const rom = await open();
    const codes = [...range(0, 64), ...ALIASES];
    const slots = rom.teams.length * 3;
    for (let start = 0; start < codes.length; start += slots) {
      const teams = clone(rom.teams);
      teams.forEach((team, t) => UNIFORM_SLOTS.forEach((slot, s) => { team.uniform[slot] = codes[(start + 3 * t + s) % codes.length]; }));
      const out = await exportOf(subject.bytes, rom.teams, teams);
      const back = await readRom(out, subject.variants);
      assert.ok(sameTeams(back.teams, teams), 'every code reads back as written, never normalized');
      assertBytes(await exportOf(out, back.teams, clone(back.teams)), out, 'unchanged export of stored aliases');
    }
  });

  test(`${name}: colors that aren't whole numbers 0-63 are refused, never clamped`, opts, async () => {
    const rom = await open();
    const before = subject.bytes.slice();
    const team = isP8 ? 20 : 7;
    const label = `Team ${team + 1} \\(${rom.teams[team].name}\\)`;
    for (const [value, shown] of [[64, '64'], [-1, '-1'], [1.5, '1.5'], ['15', '"15"'], [null, 'null'], [NaN, 'NaN'], [true, 'true'], [255, '255']]) {
      const pattern = new RegExp(`${label}: the jersey color must be a whole NES color number from 0 to 63, not ${shown.replace('.', '\\.')}\\.`);
      const teams = clone(rom.teams);
      teams[team].uniform.jersey = value;
      await assert.rejects(exportOf(subject.bytes, rom.teams, teams), pattern);
      const doc = rosterJson(subject.profile, rom.teams);
      doc.teams[team].uniform.jersey = value;
      assert.throws(() => readRosterFile(doc), pattern);
    }
    const missing = clone(rom.teams);
    delete missing[team].uniform.hair;
    await assert.rejects(exportOf(subject.bytes, rom.teams, missing), new RegExp(`${label}: the hair color is missing`));
    const extra = clone(rom.teams);
    extra[team].uniform.trim = 3;
    await assert.rejects(exportOf(subject.bytes, rom.teams, extra), new RegExp(`${label}: team colors have an unknown field "trim"`));
    const tuple = clone(rom.teams);
    tuple[team].uniform = [1, 2, 3];
    await assert.rejects(exportOf(subject.bytes, rom.teams, tuple), /team colors must be an object with cap, jersey and hair/);
    assertBytes(subject.bytes, before, 'source buffer after refusals');
  });

  test(`${name}: roster files carry every team's colors in version 3`, opts, async () => {
    const rom = await open();
    const edited = recolor(rom.teams, 1, { cap: 0x0d, jersey: 0x3e });
    const doc = JSON.parse(JSON.stringify(rosterJson(subject.profile, edited, { name: 'x.nes', sha256: 'claimed', variant: 'claimed' })));
    assert.deepEqual(Object.keys(doc), ['format', 'version', 'profile', 'palette', 'source', 'teams']);
    assert.deepEqual([doc.format, doc.version, doc.profile, doc.palette], ['little-league-roster', 3, subject.profile.id, PALETTE]);
    assert.ok(doc.teams.every((t, i) => sameTeams(t.uniform, edited[i].uniform) && Object.keys(t).includes('uniform')));
    assert.deepEqual(doc.teams[1].uniform, { cap: 0x0d, jersey: 0x3e, hair: edited[1].uniform.hair });
    const fitted = fitRoster(readRosterFile(doc), rom.teams, recolor(rom.teams, 1, { hair: 0x01 }));
    assert.ok(sameTeams(fitted, edited), 'version 3 colors replace the draft\'s');
    const reordered = JSON.parse(JSON.stringify(doc));
    reordered.teams[2].uniform = { hair: 1, jersey: 2, cap: 3 };
    assert.deepEqual(Object.keys(readRosterFile(reordered).teams[2].uniform), UNIFORM_SLOTS, 'colors are stored in record order');

    const refuse = (edit, pattern) => {
      const bad = JSON.parse(JSON.stringify(doc));
      edit(bad);
      assert.throws(() => fitRoster(readRosterFile(bad), rom.teams), pattern);
    };
    refuse((d) => { delete d.palette; }, /Version 3 rosters must name their color palette, "nes-2c02-6bit-v1"/);
    refuse((d) => { d.palette = 'rgb'; }, /palette "rgb"/);
    refuse((d) => { delete d.teams[4].uniform; }, /Team 5 \(.+\): team colors must be an object/);
    refuse((d) => { d.teams[4].uniform = { cap: 1, jersey: 2 }; }, /Team 5 \(.+\): the hair color is missing/);
    refuse((d) => { d.teams[4].uniform.cap = 64; }, /Team 5 \(.+\): the cap color must be a whole NES color number from 0 to 63, not 64/);
    refuse((d) => { d.teams[4].id = 5; }, /teams must be listed in order/);
    refuse((d) => { d.profile = isP8 ? STOCK16.id : PREVIEW8.id; }, /Expected \d+ teams/);
    if (isP8) refuse((d) => { d.teams[17].name = 'FORGED'; }, /team name is built into this ROM/);
    else refuse((d) => { d.teams[3].players[0].attrs[0] ^= 1; }, /attrs\[0\] differs/);
  });

  test(`${name}: files without team colors keep the draft's colors`, opts, async () => {
    const rom = await open();
    const draft = recolor(rom.teams, isP8 ? 20 : 3, { cap: 0x01, jersey: 0x21, hair: 0x07 });
    const roster = clone(rom.teams);
    roster[2].players[0].name = 'TESTER';
    const v3 = rosterJson(subject.profile, roster);
    const v2 = { ...v3, version: 2, teams: v3.teams.map(({ uniform, ...team }) => team) };
    delete v2.palette;
    const v1 = { version: 1, teams: v2.teams };
    const unversioned = { rom: 'old.nes', teams: v2.teams };
    for (const [label, doc] of [['version 2', v2], ['version 1', v1], ['unversioned', unversioned]]) {
      const read = readRosterFile(JSON.parse(JSON.stringify(doc)));
      assert.ok(read.teams.every((t) => t.uniform === undefined), `${label} carries no colors`);
      const fitted = fitRoster(read, rom.teams, draft);
      assert.equal(fitted[2].players[0].name, 'TESTER', `${label} roster applied`);
      assert.ok(sameTeams(fitted.map((t) => t.uniform), draft.map((t) => t.uniform)), `${label} keeps the draft's colors`);
      assert.equal(objects(fitted), fitted.length, `${label} fitted teams own their colors`);
      assert.ok(sameTeams(fitRoster(read, rom.teams).map((t) => t.uniform), rom.teams.map((t) => t.uniform)), `${label} on a new session keeps the baseline's`);
    }
    for (const [label, doc] of [['version 2', v2], ['version 1', v1]]) {
      const withUniform = JSON.parse(JSON.stringify(doc));
      withUniform.teams[0].uniform = { cap: 1, jersey: 2, hair: 3 };
      assert.throws(() => readRosterFile(withUniform), /Team colors need roster version 3/, `${label} uniform`);
      const withPalette = { ...JSON.parse(JSON.stringify(doc)), palette: PALETTE };
      assert.throws(() => readRosterFile(withPalette), /Team colors need roster version 3/, `${label} palette`);
    }
    const cli = JSON.parse(JSON.stringify(unversioned));
    cli.teams.forEach((team, t) => { team.uniform = { cap: t, jersey: 0x20, hair: 0x0f }; });
    const cliTeams = fitRoster(readRosterFile(cli), rom.teams, draft);
    assert.ok(cliTeams.every((team, t) => sameTeams(team.uniform, { cap: t, jersey: 0x20, hair: 0x0f })), 'a roster.py uniform is read');
    cli.palette = 'rgb';
    assert.throws(() => readRosterFile(cli), /palette "rgb"/);
  });

  test(`${name}: the old two-color fields are ignored with a notice, never read`, opts, async () => {
    const rom = await open();
    const draft = recolor(rom.teams, 0, { cap: 0x2a });
    const old = rosterJson(subject.profile, rom.teams);
    const extract = {
      rom: 'roster.py.nes',
      teams: old.teams.map(({ uniform, ...team }) => ({ ...team, colors: { primary: 0x30, secondary: 0x16 }, lineup: [], pitchers: [] })),
    };
    const read = readRosterFile(extract);
    assert.deepEqual(read.notices, ['Ignored the old two-color fields; they don’t match the game’s cap, jersey and hair records.']);
    const fitted = fitRoster(read, rom.teams, draft);
    assert.ok(sameTeams(fitted.map((t) => t.uniform), draft.map((t) => t.uniform)), 'primary and secondary never become colors');
    assert.ok(fitted.every((t) => !('colors' in t)));
  });

  test(`${name}: JSON provenance never chooses the ROM variant`, opts, async () => {
    const rom = await open();
    const doc = rosterJson(subject.profile, recolor(rom.teams, 3, { cap: 0x05 }), { variant: OWN, sha256: REAL.preview8.sha });
    const teams = fitRoster(readRosterFile(doc), rom.teams);
    const out = await exportOf(subject.bytes, rom.teams, teams);
    const back = await readRom(out, subject.variants);
    assert.equal(back.variant, isP8 ? OWN : 'stock16-native-colors-v1', 'the variant comes from the bytes and the export rule');
    if (isP8) assert.deepEqual(diff(out, subject.bytes), LEDGER.filter((i) => out[i] !== subject.bytes[i]));
  });
}

test('previews and fitted rosters never share a color object between teams', async () => {
  for (const [profile, doc, meta] of [
    [PREVIEW8, webJson('roster32.json'), webJson('teams32.json')],
    [STOCK16, webJson('roster.json'), null],
  ]) {
    const preview = previewRoster(profile, doc, meta);
    assert.equal(objects(preview), preview.length, `${profile.name} preview`);
    const draft = structuredClone(preview);
    assert.equal(objects(draft), draft.length, 'a structured clone keeps them apart');
    draft[profile.teamCount === 32 ? 19 : 3].uniform.cap = 0x16;
    assert.ok(preview.every((team) => team.uniform.cap !== 0x16), 'the preview is untouched');
    if (profile === PREVIEW8) {
      assert.deepEqual(draft[3].uniform, preview[3].uniform, 'an in-place edit to team 20 never reaches team 4');
      assert.deepEqual(preview[19].uniform, preview[3].uniform, 'as built the pair shares values');
    }
    const fitted = fitRoster(readRosterFile(rosterJson(profile, preview)), preview);
    assert.equal(objects([...fitted, ...preview]), 2 * preview.length, 'fitting copies colors');
    const colorless = fitRoster(readRosterFile({ rom: 'x', teams: rosterJson(profile, preview).teams.map(({ uniform, ...t }) => t) }), preview, draft);
    assert.equal(objects([...colorless, ...draft]), 2 * draft.length, 'colors taken from the draft are copies');
  }
});

/** The previous editor's adapter (e0c0853), when git history is checked out. CI checks out one commit. */
function previousAdapter() {
  try {
    const source = execFileSync('git', ['show', 'e0c0853:web/rom.js'], { cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    const dir = mkdtempSync(join(tmpdir(), 'roster-lab-e0c0853-'));
    writeFileSync(join(dir, 'rom.mjs'), source, { flag: 'wx' });
    after(() => rmSync(dir, { recursive: true, force: true }));
    return pathToFileURL(join(dir, 'rom.mjs'));
  } catch {
    return null;
  }
}
const PREVIOUS = previousAdapter();

test('ROMs written by the previous editor open as their original variant, colors untouched', { skip: PREVIOUS ? false : 'git history for e0c0853 is not checked out' }, async () => {
  const OLD = await import(PREVIOUS);
  for (const { get } of SUBJECTS) {
    const subject = get();
    if (subject.skip) continue;
    const isP8 = subject.kind === 'preview8';
    const oldMask = writableMask(SOURCE_VARIANT[subject.kind]).map((m, i) => (!isP8 && i >= stockColors(0) && i < stockColors(16) ? 0 : m));
    const oldProfile = subject.real
      ? (isP8 ? OLD.PREVIEW8 : OLD.STOCK16)
      : { ...(isP8 ? OLD.PREVIEW8 : OLD.STOCK16), maskedSha256: maskedDigest(subject.bytes, oldMask), originalSha256: sha256(subject.bytes) };
    const opened = await OLD.readRom(subject.bytes, oldProfile);
    const draft = clone(opened.teams);
    draft[isP8 ? 20 : 9].players[1].name = 'OLDED';
    draft[0].ratings[2] = (draft[0].ratings[2] % 4) + 1;
    const older = await OLD.writeRom(subject.bytes, oldProfile, opened.teams, draft);
    const rom = await readRom(older, subject.variants);
    const native = await readRom(subject.bytes, subject.variants);
    assert.equal(rom.variant, SOURCE_VARIANT[subject.kind], `${subject.kind}${subject.real ? ' real' : ''}`);
    assert.ok(sameTeams(rom.teams.map((t) => t.uniform), native.teams.map((t) => t.uniform)));
    assert.equal(rom.teams[isP8 ? 20 : 9].players[1].name, 'OLDED');
    assertBytes(await writeRom(older, subject.profile, rom.teams, clone(rom.teams), subject.variants), older, 'unchanged export');
  }
});

test('bundled previews read as their profiles with honest counts', () => {
  const p8 = previewRoster(PREVIEW8, webJson('roster32.json'), webJson('teams32.json'));
  assert.equal(p8.length, 32);
  assert.deepEqual(p8.map((t) => t.players.length), [...Array(16).fill(15), ...Array(16).fill(20)]);
  assert.equal(p8[16].name, 'AUSTRALIA');
  assert.equal(p8[31].name, 'CZECH REPUBLIC');
  assert.deepEqual([p8[5].code, p8[8].region], ['NY', 'HAWAII']);
  assert.equal(p8[4].players[2].attrs[5], 7);
  const stock = previewRoster(STOCK16, webJson('roster.json'), null);
  assert.equal(stock.length, 16);
  assert.ok(stock.every((t) => t.players.length === 15 && t.shortName));

  const noShort = webJson('roster.json');
  delete noShort.teams[2].short_name;
  assert.throws(() => previewRoster(STOCK16, noShort, null), /short name must be up to/);
  const wrongMeta = webJson('teams32.json');
  wrongMeta.teams[3].name = 'ELSEWHERE';
  assert.throws(() => previewRoster(PREVIEW8, webJson('roster32.json'), wrongMeta), /disagrees with the team metadata/);
  const padded = webJson('roster32.json');
  padded.teams[0].players.push({ name: '', attrs: Array(10).fill(0) });
  assert.throws(() => previewRoster(PREVIEW8, padded, webJson('teams32.json')), /expected 15 players, found 16/);
});

test('the shipped profiles pin two layouts and nothing else', () => {
  assert.deepEqual(PROFILES.map((p) => p.id), ['preview8-32-v1', 'stock16-v1']);
  assert.ok(PROFILES.every(Object.isFrozen));
  assert.ok(PROFILES.every((p) => !('maskedSha256' in p) && !('originalSha256' in p)), 'digests belong to ROM variants, not layouts');
  assert.deepEqual(VARIANTS.map((v) => [v.id, v.layout, v.maskedSha256]), [
    ['preview8-legacy', PREVIEW8, JUDGE_DIGESTS['preview8-legacy']],
    ['preview8-independent-colors-v1', PREVIEW8, JUDGE_DIGESTS['preview8-independent-colors-v1']],
    ['stock16-native-colors-v1', STOCK16, JUDGE_DIGESTS['stock16-native-colors-v1']],
  ]);
  assert.ok(Object.isFrozen(VARIANTS) && VARIANTS.every(Object.isFrozen));
  assert.deepEqual(VARIANTS.map((v) => v.originalSha256), [REAL.preview8.sha, undefined, REAL.stock16.sha],
    'only the original files are labeled original; an upgraded copy never is');
});

test('a page without WebCrypto refuses ROMs instead of skipping the check', async () => {
  const saved = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
  try {
    const { bytes, variants } = fixture('preview8');
    await assert.rejects(readRom(bytes, variants), /can’t check ROM files on this page/);
  } finally {
    Object.defineProperty(globalThis, 'crypto', saved);
  }
});

test('real ROMs: digests recompute independently and previews equal the ROMs', { skip: realSubject('preview8').skip || realSubject('stock16').skip }, async () => {
  for (const kind of ['preview8', 'stock16']) {
    const subject = realSubject(kind);
    const variant = REAL[kind].variant;
    assert.equal(maskedDigest(subject.bytes, writableMask(variant)), JUDGE_DIGESTS[variant], `${variant} masked digest`);
    const rom = await openRom(subject.bytes);
    const preview = kind === 'preview8'
      ? previewRoster(PREVIEW8, webJson('roster32.json'), webJson('teams32.json'))
      : previewRoster(STOCK16, webJson('roster.json'), null);
    assert.ok(sameTeams(preview, rom.teams), `${kind} bundled preview equals the ROM`);
  }
  const p8 = await openRom(realSubject('preview8').bytes);
  const meta = webJson('teams32.json').teams;
  assert.deepEqual(p8.teams.map((t) => [t.name, t.code, t.region]), meta.map((t) => [t.name, t.code, t.region]));
  assert.deepEqual([p8.teams[16].name, p8.teams[31].name], ['AUSTRALIA', 'CZECH REPUBLIC']);
});
