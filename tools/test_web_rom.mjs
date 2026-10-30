// Behavior tests for web/rom.js.
//
//   node --test tools/test_web_rom.mjs
//   ROSTER_ROM32=build/homerunart32.nes \
//   ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' node --test tools/test_web_rom.mjs
//
// Synthetic images always run. The real-ROM cases are skipped, and reported as
// skipped, unless the two environment variables point at the ROMs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  ACTIVE_PLAYERS, PREVIEW8, PROFILES, STOCK16, fitRoster, openRom, previewRoster, readRom,
  readRosterFile, rosterJson, sameTeams, skillStars, writeRom,
} from '../web/rom.js';
import {
  LAYOUTS, STOCK_SHORT_WIDTHS, fixture, maskedDigest, p8Code, p8Name, p8Record, sha256,
  stockName, stockRating, stockShortPointer, stockShortText, writableMask,
} from './web_fixtures.mjs';

const WEB = fileURLToPath(new URL('../web/', import.meta.url));
const webJson = (name) => JSON.parse(readFileSync(`${WEB}${name}`, 'utf8'));
const clone = (v) => structuredClone(v);
const pad2 = (n) => String(n).padStart(2, '0');
const prg = (bank, cpu) => 16 + bank * 0x4000 + cpu - (bank === 15 ? 0xc000 : 0x8000);

const JUDGE_DIGESTS = {
  preview8: '26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586',
  stock16: '6f4fbd41e6a7235596aef7ce8c13877b1df96731a9a5e21ce4a04268ca176b2a',
};
const REAL = {
  preview8: { env: 'ROSTER_ROM32', sha: 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b', profile: PREVIEW8 },
  stock16: { env: 'ROSTER_ROM16', sha: '58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e', profile: STOCK16 },
};

function realSubject(kind) {
  const path = process.env[REAL[kind].env];
  if (!path) return { kind, skip: `set ${REAL[kind].env} to run against the real ROM` };
  if (!existsSync(path)) return { kind, skip: `${REAL[kind].env}=${path} does not exist` };
  const bytes = new Uint8Array(readFileSync(path));
  assert.equal(sha256(bytes), REAL[kind].sha, `${path} is not the accepted ${kind} ROM`);
  return { kind, bytes, profile: REAL[kind].profile, real: true };
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
  const out = await writeRom(subject.bytes, subject.profile, opened.teams, teams);
  assertBytes(subject.bytes, before, 'source buffer');
  assertBytes(out, expected, 'export');
  const mask = writableMask(subject.kind);
  assert.ok(diff(out, subject.bytes).every((i) => ((out[i] ^ subject.bytes[i]) & ~mask[i] & 0xff) === 0), 'changed bits stay writable');
  const reopened = await readRom(out, subject.profile);
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
  const open = () => readRom(subject.bytes, subject.profile);

  test(`${name}: admits the file and reads every stored record`, opts, async () => {
    const rom = await open();
    assert.equal(rom.profile.id, subject.profile.id);
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
    assertBytes(await writeRom(subject.bytes, subject.profile, rom.teams, clone(rom.teams)), subject.bytes, 'no-op export');
    const text = JSON.stringify(rosterJson(subject.profile, rom.teams, { name: 'x.nes' }));
    const teams = fitRoster(readRosterFile(JSON.parse(text)), rom.teams);
    assert.ok(sameTeams(teams, rom.teams));
    assertBytes(await writeRom(subject.bytes, subject.profile, rom.teams, teams), subject.bytes, 'JSON round trip export');
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
    await assert.rejects(writeRom(subject.bytes, subject.profile, edited, edited), /did not read back as the edited roster/,
      'a baseline that does not describe the file cannot hide an edit');
  });

  test(`${name}: read-only bits and records refuse to change`, opts, async () => {
    const rom = await open();
    const refuse = async (edit, pattern) => {
      const teams = clone(rom.teams);
      edit(teams);
      await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams), pattern);
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
      await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams), pattern);
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
    const out = await writeRom(subject.bytes, subject.profile, rom.teams, edited);
    assert.deepEqual(diff(out, subject.bytes), [park]);
    assert.equal(out[park], 2);
    const reopened = await readRom(out, subject.profile);
    assert.throws(
      () => fitRoster(readRosterFile(rosterJson(subject.profile, rom.teams)), reopened.teams),
      /skill exception can only be kept unchanged/);
    await assert.rejects(writeRom(out, subject.profile, reopened.teams, rom.teams),
      /skill exception can only be kept unchanged/);
    assertBytes(await writeRom(out, subject.profile, reopened.teams, reopened.teams), out, 'unchanged edited export');
    const stray = rosterJson(subject.profile, rom.teams);
    stray.teams[4].players[3].attrs[5] = 7;
    assert.throws(() => fitRoster(readRosterFile(stray), rom.teams), /skill 7 is out of range/);
  });

  test(`${name}: files with changes outside the editable fields are refused`, opts, async () => {
    const refuse = async (mutate, pattern) => {
      const bytes = mutate(subject.bytes.slice()) ?? null;
      await assert.rejects(readRom(bytes, subject.profile), pattern);
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
        await assert.rejects(writeRom(subject.bytes, subject.profile, rom.teams, teams), pattern);
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
    refuse((d) => { d.version = 3; }, /version isn’t supported/);
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
      for (const team of legacy.teams) team.short_name = '';
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
  assert.equal(PREVIEW8.maskedSha256, JUDGE_DIGESTS.preview8);
  assert.equal(STOCK16.maskedSha256, JUDGE_DIGESTS.stock16);
});

test('a page without WebCrypto refuses ROMs instead of skipping the check', async () => {
  const saved = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
  try {
    const { bytes, profile } = fixture('preview8');
    await assert.rejects(readRom(bytes, profile), /can’t check ROM files on this page/);
  } finally {
    Object.defineProperty(globalThis, 'crypto', saved);
  }
});

test('real ROMs: digests recompute independently and previews equal the ROMs', { skip: realSubject('preview8').skip || realSubject('stock16').skip }, async () => {
  for (const kind of ['preview8', 'stock16']) {
    const subject = realSubject(kind);
    assert.equal(maskedDigest(subject.bytes, writableMask(kind)), JUDGE_DIGESTS[kind], `${kind} masked digest`);
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
