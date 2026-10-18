/**
 * ROM parsing / patching for Little League Baseball: Championship Series.
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
  const teams = [];

  for (let t = 0; t < TEAMS; t++) {
    const nameOff = OFF.teamNames + t * 16;
    const short = scanShort(bytes, t);
    const players = [];

    for (let p = 0; p < PLAYERS; p++) {
      const rec = OFF.roster + t * 0x120 + p * 16;
      players.push({
        name: ascii(bytes, rec, NAME_LEN).trimEnd(),
        attrs: Array.from(bytes.slice(rec + NAME_LEN, rec + 16)),
      });
    }

    teams.push({
      id: t,
      name: ascii(bytes, nameOff, TEAM_NAME_LEN).trimEnd(),
      shortName: short.name,
      shortWidth: short.width,
      shortAttr: short.attr,
      ratings: Array.from(bytes.slice(OFF.ratings + t * 4, OFF.ratings + t * 4 + 4)),
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
      looksRight: teams[0].name.toUpperCase().startsWith('JAPAN'),
    },
  };
}

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
  if (teams.length !== TEAMS) throw new Error(`Expected ${TEAMS} teams, got ${teams.length}`);
  const out = new Uint8Array(bytes);

  for (let t = 0; t < TEAMS; t++) {
    const team = teams[t];
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

    for (let r = 0; r < 4; r++) {
      const v = team.ratings[r];
      if (!Number.isInteger(v) || v < 1 || v > 4) {
        throw new Error(`team ${t + 1} rating ${r + 1} must be 1..4`);
      }
      out[OFF.ratings + t * 4 + r] = v;
    }

    if (team.players.length !== PLAYERS) {
      throw new Error(`team ${t + 1} has ${team.players.length} players, expected ${PLAYERS}`);
    }
    for (let p = 0; p < PLAYERS; p++) {
      const player = team.players[p];
      const rec = OFF.roster + t * 0x120 + p * 16;
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

export const CONST = { TEAMS, PLAYERS, NAME_LEN, TEAM_NAME_LEN, ATTRS, OFF };
