/**
 * ROM parsing / patching for Little League Baseball: Championship Series.
 *
 * Supports both layouts:
 *   - stock 16 teams x 15 players, bank4 $8420, stride $120;
 *   - 32-team bank8 blocks at $8000 + team*$170, 20 players each.
 *
 * Offsets are derived in docs/roster-format.md. Everything is little-endian,
 * plain data in switchable PRG banks, and reachable at fixed file offsets.
 */

const HEADER = 16;
const BANK = 0x4000;
const TEAMS = 16;
const PLAYERS = 15;
const NAME_LEN = 6;
const TEAM_NAME_LEN = 14;
const ATTRS = 10;

/** File offset of a CPU address inside a switchable PRG bank. */
function fileOffset(bank, cpu) {
  return HEADER + bank * BANK + (cpu - 0x8000);
}

const OFF = {
  teamNames: fileOffset(1, 0x9180),
  shortPtr: [fileOffset(1, 0x9280), fileOffset(1, 0x9290)],
  ratings: fileOffset(3, 0xb224),
  roster: fileOffset(4, 0x8420),
};

const OFF32 = {
  roster: HEADER + 8 * BANK,          // bank8 $8000, team 0 block
  stride: 0x170,
  players: 20,
  names32: fileOffset(1, 0xbcc0),     // 16 x 8 bytes (7 chars + FF)
  ratings32: fileOffset(3, 0xbc80),   // 32 x 4 if the 32-team build is present
  bank9Names: HEADER + 9 * BANK + 0x80, // bank9 $8080, 32 x 16
};

function u16(bytes, off) {
  return bytes[off] | (bytes[off + 1] << 8);
}

function ascii(bytes, off, len) {
  let s = '';
  for (let i = 0; i < len; i++) {
    const c = bytes[off + i];
    s += c >= 32 && c < 127 ? String.fromCharCode(c) : ' ';
  }
  return s;
}

function printable(bytes, off, len) {
  if (off < 0 || off + len > bytes.length) return false;
  for (let i = 0; i < len; i++) {
    const c = bytes[off + i];
    if (c < 32 || c > 126) return false;
  }
  return true;
}

/** True when bank8 team 0 starts with a printable roster name. */
function isRoster32(bytes) {
  return bytes.length >= OFF32.roster + 0x170 &&
    bytes[4] >= 16 && printable(bytes, OFF32.roster, 6);
}

/** True when bank9 has the 32-team name table. */
function hasBank9Names(bytes) {
  return bytes.length >= OFF32.bank9Names + 32 * 16 &&
    printable(bytes, OFF32.bank9Names, 6);
}

/** True when bank3 $BC80 looks like the 32 x 4 ratings table. */
function hasRatings32(bytes) {
  const off = OFF32.ratings32;
  if (off + 128 > bytes.length) return false;
  for (let i = 0; i < 128; i++) {
    if (bytes[off + i] < 1 || bytes[off + i] > 4) return false;
  }
  return true;
}

function readRatings(bytes, team, use32) {
  if (team < 16) {
    return Array.from(bytes.slice(OFF.ratings + team * 4, OFF.ratings + team * 4 + 4));
  }
  if (use32 && hasRatings32(bytes)) {
    const off = OFF32.ratings32 + team * 4;
    return Array.from(bytes.slice(off, off + 4));
  }
  return [2, 2, 2, 2];
}

function readTeamName(bytes, team, use32) {
  if (team < 16) return ascii(bytes, OFF.teamNames + team * 16, TEAM_NAME_LEN).trimEnd();
  if (use32 && hasBank9Names(bytes)) {
    return ascii(bytes, OFF32.bank9Names + team * 16, TEAM_NAME_LEN).trimEnd();
  }
  if (use32) {
    const off = OFF32.names32 + (team - 16) * 8;
    if (printable(bytes, off, 7)) return ascii(bytes, off, 7).trimEnd();
  }
  return `TEAM ${team + 1}`;
}

function scanShort(bytes, team) {
  const table = OFF.shortPtr[team < 8 ? 0 : 1];
  const idx = team < 8 ? team : team - 8;
  const ptr = u16(bytes, table + idx * 2);
  const off = fileOffset(1, ptr);
  let end = off + 1;
  while (end < bytes.length && bytes[end] !== 0xff) end++;
  if (end >= bytes.length) throw new Error(`team ${team}: unterminated short name`);
  return {
    attr: bytes[off],
    textOff: off + 1,
    width: end - (off + 1),
    name: ascii(bytes, off + 1, end - (off + 1)).trim(),
  };
}

/**
 * @param {Uint8Array} bytes
 * @returns {{teams: Array, meta: object}}
 */
export function parseRom(bytes) {
  if (bytes.length < HEADER + BANK || bytes[0] !== 0x4e || bytes[1] !== 0x45 ||
      bytes[2] !== 0x53 || bytes[3] !== 0x1a) {
    throw new Error('Not an iNES ROM (missing NES\\x1A header).');
  }
  const prg = bytes[4];
  const chr = bytes[5];
  if (prg < 8) throw new Error(`Only ${prg} PRG banks; expected at least 8.`);
  const need = HEADER + prg * BANK + chr * 0x2000;
  if (bytes.length < need) {
    throw new Error(`Truncated ROM: ${bytes.length} bytes, header says ${need}.`);
  }

  if (bytes[6] & 0x04) {
    throw new Error('ROM has a 512-byte trainer; offsets would shift. Not supported.');
  }
  const mapper = (bytes[7] & 0xf0) | (bytes[6] >> 4);
  const use32 = isRoster32(bytes);
  const teamCount = use32 ? 32 : TEAMS;
  const playerCount = use32 ? OFF32.players : PLAYERS;
  const stride = use32 ? OFF32.stride : 0x120;
  const roster = use32 ? OFF32.roster : OFF.roster;
  const teams = [];

  for (let t = 0; t < teamCount; t++) {
    const short = t < 16 ? scanShort(bytes, t)
      : { attr: 0, textOff: 0, width: 3, name: ascii(bytes, OFF32.names32 + (t - 16) * 8, 7).trim() };
    const players = [];

    for (let p = 0; p < playerCount; p++) {
      const rec = roster + t * stride + p * RECORD_SIZE;
      players.push({
        name: ascii(bytes, rec, NAME_LEN).trimEnd(),
        attrs: Array.from(bytes.slice(rec + NAME_LEN, rec + 16)),
      });
    }

    teams.push({
      id: t,
      name: readTeamName(bytes, t, use32),
      shortName: short.name,
      shortWidth: short.width,
      shortAttr: short.attr,
      ratings: readRatings(bytes, t, use32),
      players,
    });
  }

  return {
    teams,
    meta: {
      size: bytes.length,
      prg,
      chr,
      mapper,
      mirroring: bytes[6] & 1 ? 'vertical' : 'horizontal',
      layout: use32 ? 'bank8-32' : 'stock-16',
      teams: teamCount,
      players: playerCount,
      looksRight: teams[0].name.toUpperCase().startsWith('JAPAN'),
    },
  };
}

const RECORD_SIZE = 16;

function assertChars(text, label) {
  for (const ch of text) {
    const c = ch.charCodeAt(0);
    if (c < 32 || c > 126) throw new Error(`${label}: "${text}" has non-ASCII characters`);
  }
}

function writeAscii(out, off, text, width, label) {
  if (text.length > width) throw new Error(`${label}: "${text}" is longer than ${width} characters`);
  assertChars(text, label);
  for (let i = 0; i < width; i++) out[off + i] = i < text.length ? text.charCodeAt(i) : 0x20;
}

/**
 * Apply roster state to a copy of the ROM bytes.
 * @param {Uint8Array} bytes original ROM
 * @param {Array} teams edited teams
 * @returns {Uint8Array} patched ROM
 */
export function applyRom(bytes, teams) {
  const use32 = teams.length === 32 && isRoster32(bytes);
  if (!use32 && teams.length !== TEAMS) {
    throw new Error(`Expected ${TEAMS} teams, got ${teams.length}`);
  }
  const teamCount = use32 ? 32 : TEAMS;
  const playerCount = use32 ? OFF32.players : PLAYERS;
  const stride = use32 ? OFF32.stride : 0x120;
  const roster = use32 ? OFF32.roster : OFF.roster;
  const haveBank9 = use32 && hasBank9Names(bytes);
  const haveRatings32 = use32 && hasRatings32(bytes);
  const out = new Uint8Array(bytes);

  for (let t = 0; t < teamCount; t++) {
    const team = teams[t];
    if (!team) throw new Error(`missing team ${t + 1}`);

    if (t < 16) {
      const nameOff = OFF.teamNames + t * 16;
      writeAscii(out, nameOff, team.name, TEAM_NAME_LEN, `team ${t + 1} name`);
      out[nameOff + 14] = 0xff;
      out[nameOff + 15] = 0xff;

      const short = scanShort(bytes, t);
      if (team.shortName.length > short.width) {
        throw new Error(
          `team ${t + 1} scoreboard name "${team.shortName}" needs ${team.shortName.length} ` +
          `characters but only ${short.width} fit`);
      }
      writeAscii(out, short.textOff, team.shortName, short.width, `team ${t + 1} scoreboard`);
      if (team.shortName.length < short.width) {
        for (let i = short.textOff + team.shortName.length; i < short.textOff + short.width; i++) {
          out[i] = 0x20;
        }
      }
    } else if (haveBank9) {
      const off = OFF32.bank9Names + t * 16;
      writeAscii(out, off, team.name, TEAM_NAME_LEN, `team ${t + 1} name`);
      out[off + 14] = 0xff;
      out[off + 15] = 0xff;
    } else if (use32) {
      const off = OFF32.names32 + (t - 16) * 8;
      writeAscii(out, off, team.name, 7, `team ${t + 1} name`);
      out[off + 7] = 0xff;
    }

    if (t < 16 || haveRatings32) {
      for (let r = 0; r < 4; r++) {
        const v = team.ratings[r];
        if (!Number.isInteger(v) || v < 1 || v > 4) {
          throw new Error(`team ${t + 1} rating ${r + 1} must be 1..4`);
        }
        const off = (t < 16 ? OFF.ratings : OFF32.ratings32) + t * 4 + r;
        out[off] = v;
      }
    }

    if (team.players.length !== playerCount) {
      throw new Error(`team ${t + 1} has ${team.players.length} players, expected ${playerCount}`);
    }
    for (let p = 0; p < playerCount; p++) {
      const player = team.players[p];
      const rec = roster + t * stride + p * RECORD_SIZE;
      writeAscii(out, rec, player.name, NAME_LEN, `team ${t + 1} player ${p + 1} name`);
      if (!Array.isArray(player.attrs) || player.attrs.length !== ATTRS) {
        throw new Error(`team ${t + 1} player ${p + 1} needs ${ATTRS} attribute bytes`);
      }
      for (let a = 0; a < ATTRS; a++) {
        const v = player.attrs[a];
        if (!Number.isInteger(v) || v < 0 || v > 255) {
          throw new Error(`team ${t + 1} player ${p + 1} attribute ${a} is not a byte`);
        }
        out[rec + NAME_LEN + a] = v;
      }
    }
  }
  return out;
}

export const CONST = { TEAMS, PLAYERS, NAME_LEN, TEAM_NAME_LEN, ATTRS, OFF, OFF32 };
