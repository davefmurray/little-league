/**
 * ROM and roster-file adapter for Roster Lab. DOM-free, so Node tests import it.
 *
 * Two logical layouts describe the rosters: the original US cartridge and the
 * 32-team Preview 8 release. Below them, a ROM opens only as one of the pinned
 * ROM variants in VARIANTS. Admission needs the layout's exact iNES geometry
 * plus the SHA-256 of every bit that variant never writes, and exactly one
 * variant must match. Edited copies reopen, while code, graphics, pointers,
 * trailers and unused records stay pinned. Editable fields are range-checked
 * separately.
 *
 * Team shape: { id, ...profile text fields, ratings[4], uniform, players[] }.
 * `uniform` is { cap, jersey, hair }: the team's three NES color numbers, 0-63.
 * `players` holds every stored record: 15 per team, or 20 on Preview 8 teams
 * 16-31 where the game loads only the first 15. A player is { name, attrs },
 * and `attrs` holds record bytes 6-15 exactly as stored.
 */

const HEADER = 16;
const PRG_BANK = 0x4000;
const CHR_BANK = 0x2000;
const RECORD = 16;
const NAME_LEN = 6;
const ATTR_COUNT = 10;
const RATING_COUNT = 4;
const TEXT = /^[A-Z0-9 ]*$/;
const FORMAT = 'little-league-roster';

export const ACTIVE_PLAYERS = 15;

/** A team's color record, in ROM order: cap and trim, jersey, hair. */
export const UNIFORM_SLOTS = Object.freeze(['cap', 'jersey', 'hair']);

/** Roster files name the color numbering they store: the NES PPU's 64 codes. */
export const PALETTE = 'nes-2c02-6bit-v1';

/** Writable bits of each attrs byte: byte 9 bat/pitch, byte 10 low nibble speed, byte 11 skill. */
const ATTR_BITS = [0, 0, 0, 0xff, 0x0f, 0xff, 0, 0, 0, 0];

/** File offset of a CPU address in a switchable 16K PRG bank. */
const prg = (bank, cpu) => HEADER + bank * PRG_BANK + cpu - 0x8000;

/** File offset of a CPU address in the fixed last PRG bank. */
const fixed = (prgBanks, cpu) => HEADER + (prgBanks - 1) * PRG_BANK + cpu - 0xc000;

/** Stock scoreboard names: bank 1 text address and width. Pointers and terminators stay pinned. */
const STOCK_SHORT = [
  [0x92a1, 10], [0x92ad, 11], [0x92ba, 13], [0x92c9, 14],
  [0x92d9, 10], [0x92e5, 11], [0x92f2, 12], [0x9300, 10],
  [0x930c, 10], [0x9318, 10], [0x9324, 12], [0x9332, 10],
  [0x933e, 10], [0x934a, 10], [0x9356, 11], [0x9363, 10],
];

export const STOCK16 = deepFreeze({
  id: 'stock16-v1',
  name: 'original 16-team',
  prgBanks: 8,
  chrBanks: 16,
  teamCount: 16,
  storedCount: () => 15,
  record: (t, p) => prg(4, 0x8420 + 0x120 * t) + RECORD * p,
  rating: (t) => prg(3, 0xb224 + 4 * t),
  text: [
    { key: 'name', json: 'name', at: (t) => prg(1, 0x9180 + 16 * t), width: () => 14, editable: true },
    { key: 'shortName', json: 'short_name', at: (t) => prg(1, STOCK_SHORT[t][0]), width: (t) => STOCK_SHORT[t][1], editable: true },
  ],
  sourceSkills: [{ team: 4, slot: 2, value: 7 }],
});

export const PREVIEW8 = deepFreeze({
  id: 'preview8-32-v1',
  name: 'Preview 8',
  prgBanks: 16,
  chrBanks: 16,
  teamCount: 32,
  storedCount: (t) => (t < 16 ? 15 : 20),
  record: (t, p) => (t < 16 ? prg(4, 0x8420 + 0x120 * t) : prg(8, 0x8000 + 0x170 * t)) + RECORD * p,
  rating: (t) => prg(3, 0xbc80 + 4 * t),
  text: [
    { key: 'name', json: 'name', at: (t) => prg(1, t < 16 ? 0x9180 + 16 * t : 0xbcc0 + 16 * (t - 16)), width: () => 14 },
    { key: 'code', json: 'code', at: (t) => prg(11, 0xb000 + 4 * t), width: () => 4 },
    { key: 'region', json: 'region', at: (t) => prg(10, 0xaa00 + 8 * t), width: () => 8, centered: true },
  ],
  sourceSkills: [{ team: 4, slot: 2, value: 7 }],
});

export const PROFILES = Object.freeze([PREVIEW8, STOCK16]);

/**
 * The 16 three-byte color records at fixed-bank $FAC0, identical in both
 * original ROMs. The game's palette routine reads team t's record at
 * $FAC0 + 3t; Preview 8 reads team t at $FAC0 + 3(t & 15), so teams t and
 * t + 16 share one. Used only for ROM-less previews; an opened ROM supplies
 * its own bytes.
 */
const NATIVE_UNIFORMS = deepFreeze([
  [0x05, 0x20, 0x0f], [0x26, 0x20, 0x38], [0x02, 0x22, 0x38], [0x1b, 0x2b, 0x0f],
  [0x12, 0x20, 0x0f], [0x15, 0x11, 0x38], [0x11, 0x15, 0x38], [0x00, 0x10, 0x38],
  [0x14, 0x12, 0x0f], [0x15, 0x15, 0x0f], [0x15, 0x25, 0x0f], [0x05, 0x26, 0x0f],
  [0x18, 0x28, 0x38], [0x11, 0x31, 0x0f], [0x09, 0x27, 0x38], [0x0a, 0x2b, 0x38],
]);

const COLOR_TABLE = 0xfac0;
const OWN_COLOR_TABLE = 0xf380;

/**
 * Every ROM Roster Lab opens is exactly one of these. `uniform(t)` is the file
 * offset of team t's three color bytes. Where colors are writable, only their
 * low six bits are; the high two bits stay pinned to zero by the digest.
 * Preview 8's original variant shares records between teams t and t + 16, so a
 * color change there needs the guarded upgrade to the own-colors variant.
 */
export const VARIANTS = deepFreeze([
  {
    id: 'preview8-legacy',
    layout: PREVIEW8,
    uniform: (t) => fixed(16, COLOR_TABLE) + 3 * (t & 15),
    writableColors: false,
    upgrade: 'preview8-independent-colors-v1',
    originalSha256: 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b',
    maskedSha256: '26c6558167b3b84d597141fb9e1f38556d2b6532456674f16b7cc644950d2586',
  },
  {
    id: 'preview8-independent-colors-v1',
    layout: PREVIEW8,
    uniform: (t) => fixed(16, OWN_COLOR_TABLE) + 3 * t,
    writableColors: true,
    maskedSha256: '430000e74c40123c3b404b19858eed507154c3a9843e5963b5ca1ee405050ca7',
  },
  {
    id: 'stock16-native-colors-v1',
    layout: STOCK16,
    uniform: (t) => fixed(8, COLOR_TABLE) + 3 * t,
    writableColors: true,
    originalSha256: '58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e',
    maskedSha256: 'aa7a1e270e6300c6f0bc39be64d9180fe23cf9cb6ec70514d6d854209ccdb2d3',
  },
]);

const hexBytes = (text) => Array.from(text.match(/../g), (h) => parseInt(h, 16));

/**
 * The own-colors upgrade for Preview 8 (fixed bank 15). The palette routine at
 * $C6FE keeps its 21 bytes, timing and exits; three operands change so it
 * reads team t & 31 from a 96-byte table at $F380 instead of team t & 15 from
 * $FAC0. The table fills padding nothing reads and is seeded from the source's
 * own records. $FAC0 stays pinned and unread afterwards.
 */
const OWN_COLORS = deepFreeze({
  routine: fixed(16, 0xc6fe),
  before: hexBytes('b9ef04290f85050a650569c08504a000a9fa850560'),
  after: hexBytes('b9ef04291f85050a650569808504a000a9f3850560'),
  padding: [fixed(16, 0xf379), fixed(16, 0xf400)],
  pointer: fixed(16, 0xfff4),
});

export function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value)) deepFreeze(item);
  }
  return value;
}

export const sameTeams = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Stars shown for a skill byte; the game's lookup is "12345555". */
export const skillStars = (raw) => Math.min(raw, 4) + 1;

const romSize = (profile) => HEADER + profile.prgBanks * PRG_BANK + profile.chrBanks * CHR_BANK;

function fail(message) {
  throw new Error(message);
}

const where = (t, team, p) =>
  `Team ${t + 1}${team?.name ? ` (${team.name})` : ''}${p === undefined ? '' : `, player ${p + 1}`}`;

/** Space padding is storage, not content. */
const canonical = (text, centered) => (centered ? text.replace(/^ +| +$/g, '') : text.replace(/ +$/, ''));

function readText(bytes, off, width, centered) {
  return canonical(String.fromCharCode(...bytes.subarray(off, off + width)), centered);
}

function writeText(out, off, width, text) {
  for (let i = 0; i < width; i++) out[off + i] = i < text.length ? text.charCodeAt(i) : 0x20;
}

const isText = (value, width, centered) =>
  typeof value === 'string' && value.length <= width && TEXT.test(value) && value === canonical(value, centered);

const isByte = (v) => Number.isInteger(v) && v >= 0 && v <= 255;

const isColor = (v) => Number.isInteger(v) && v >= 0 && v <= 0x3f;

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

const shown = (v) => (typeof v === 'string' ? JSON.stringify(v) : String(v));

function checkUniform(uniform, label) {
  if (!isObject(uniform)) fail(`${label}: team colors must be an object with cap, jersey and hair.`);
  for (const key of Object.keys(uniform)) {
    if (!UNIFORM_SLOTS.includes(key)) fail(`${label}: team colors have an unknown field ${JSON.stringify(key)}.`);
  }
  for (const slot of UNIFORM_SLOTS) {
    if (!Object.hasOwn(uniform, slot)) fail(`${label}: the ${slot} color is missing.`);
    if (!isColor(uniform[slot])) {
      fail(`${label}: the ${slot} color must be a whole NES color number from 0 to 63, not ${shown(uniform[slot])}.`);
    }
  }
}

const copyUniform = (uniform) => ({ cap: uniform.cap, jersey: uniform.jersey, hair: uniform.hair });

const uniformOf = ([cap, jersey, hair]) => ({ cap, jersey, hair });

const colorsChanged = (baseline, teams) =>
  teams.some((team, t) => UNIFORM_SLOTS.some((slot) => team.uniform[slot] !== baseline[t].uniform[slot]));

const layoutMasks = new WeakMap();
const variantMasks = new WeakMap();

/** Per-byte mask of the roster bits a layout may write. Built from pinned offsets only. */
function layoutMask(profile) {
  let mask = layoutMasks.get(profile);
  if (mask) return mask;
  mask = new Uint8Array(romSize(profile));
  for (let t = 0; t < profile.teamCount; t++) {
    for (let p = 0; p < ACTIVE_PLAYERS; p++) {
      const rec = profile.record(t, p);
      mask.fill(0xff, rec, rec + NAME_LEN);
      ATTR_BITS.forEach((bits, a) => { mask[rec + NAME_LEN + a] = bits; });
    }
    mask.fill(0xff, profile.rating(t), profile.rating(t) + RATING_COUNT);
    for (const f of profile.text) if (f.editable) mask.fill(0xff, f.at(t), f.at(t) + f.width(t));
  }
  layoutMasks.set(profile, mask);
  return mask;
}

/** The layout's roster bits plus, where the variant allows, the low six bits of each color byte. */
function writableMask(variant) {
  let mask = variantMasks.get(variant);
  if (mask) return mask;
  mask = layoutMask(variant.layout).slice();
  if (variant.writableColors) {
    for (let t = 0; t < variant.layout.teamCount; t++) mask.fill(0x3f, variant.uniform(t), variant.uniform(t) + 3);
  }
  variantMasks.set(variant, mask);
  return mask;
}

async function sha256(bytes) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) fail('This browser can’t check ROM files on this page. Open Roster Lab over HTTPS or from localhost.');
  const digest = new Uint8Array(await subtle.digest('SHA-256', bytes));
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('');
}

function checkHeader(bytes) {
  if (bytes.length < HEADER || bytes[0] !== 0x4e || bytes[1] !== 0x45 || bytes[2] !== 0x53 || bytes[3] !== 0x1a) {
    fail('This file isn’t an NES ROM.');
  }
  if (bytes[7] & 0x0c) fail('NES 2.0 and nonstandard headers aren’t supported. Use the plain iNES file.');
  if (bytes[6] & 0x04) fail('ROMs with a trainer aren’t supported.');
  const mapper = (bytes[7] & 0xf0) | (bytes[6] >> 4);
  if (mapper !== 1) fail(`This ROM uses mapper ${mapper}; Little League Baseball uses MMC1 (mapper 1).`);
}

const UNSUPPORTED = 'Roster Lab opens the original 16-team US ROM and the 32-team Preview 8 ROM. This file is neither.';

/** The one variant of `registry` whose pinned bits `bytes` matches, or a reason a person can act on. */
async function admit(bytes, registry) {
  checkHeader(bytes);
  const candidates = registry.filter((v) => bytes[4] === v.layout.prgBanks && bytes[5] === v.layout.chrBanks);
  if (!candidates.length) fail(UNSUPPORTED);
  const { layout } = candidates[0];
  const size = romSize(layout);
  if (bytes.length !== size) {
    fail(`The file is ${bytes.length.toLocaleString('en-US')} bytes, but its header describes ` +
      `${size.toLocaleString('en-US')}. It may be truncated or carry extra data.`);
  }
  const matches = [];
  for (const variant of candidates) {
    const mask = writableMask(variant);
    if (await sha256(bytes.map((b, i) => b & ~mask[i])) === variant.maskedSha256) matches.push(variant);
  }
  if (matches.length !== 1) {
    fail(`This isn’t the ${layout.name} ROM, or it has changes outside the roster fields Roster Lab edits.`);
  }
  return matches[0];
}

/**
 * Admit `bytes` as one of the production ROM variants.
 * @returns {Promise<{profile, variant: string, teams, sha256: string, exact: boolean}>}
 */
export async function openRom(bytes) {
  return readRom(bytes, VARIANTS);
}

/** Admit `bytes` as exactly one variant of `registry`, or throw a reason a person can act on. */
export async function readRom(bytes, registry) {
  const variant = await admit(bytes, registry);
  const profile = variant.layout;
  const teams = readTeams(bytes, variant);
  checkValues(profile, teams);
  const sha = await sha256(bytes);
  return { profile, variant: variant.id, teams, sha256: sha, exact: sha === variant.originalSha256 };
}

function readTeams(bytes, variant) {
  const profile = variant.layout;
  return Array.from({ length: profile.teamCount }, (_, t) => {
    const team = { id: t };
    for (const f of profile.text) team[f.key] = readText(bytes, f.at(t), f.width(t), f.centered);
    team.ratings = Array.from(bytes.subarray(profile.rating(t), profile.rating(t) + RATING_COUNT));
    team.uniform = uniformOf(bytes.subarray(variant.uniform(t), variant.uniform(t) + 3));
    team.players = Array.from({ length: profile.storedCount(t) }, (_, p) => {
      const rec = profile.record(t, p);
      return {
        name: readText(bytes, rec, NAME_LEN),
        attrs: Array.from(bytes.subarray(rec + NAME_LEN, rec + RECORD)),
      };
    });
    return team;
  });
}

function skillAllowed(profile, t, p, value) {
  return (Number.isInteger(value) && value >= 0 && value <= 4) ||
    profile.sourceSkills.some((s) => s.team === t && s.slot === p && s.value === value);
}

/** Shape and value checks that need no baseline. */
function checkValues(profile, teams) {
  if (!Array.isArray(teams) || teams.length !== profile.teamCount) fail(`Expected ${profile.teamCount} teams.`);
  teams.forEach((team, t) => {
    if (team.id !== t) fail(`${where(t)} is out of order.`);
    for (const f of profile.text) {
      if (!isText(team[f.key], f.width(t), f.centered)) {
        fail(`${where(t, team)}: ${f.json.replace('_', ' ')} must be up to ${f.width(t)} letters, digits or spaces.`);
      }
    }
    if (!Array.isArray(team.ratings) || team.ratings.length !== RATING_COUNT ||
        !team.ratings.every((v) => Number.isInteger(v) && v >= 1 && v <= 4)) {
      fail(`${where(t, team)}: team ratings must be four whole numbers from 1 to 4.`);
    }
    checkUniform(team.uniform, where(t, team));
    const stored = profile.storedCount(t);
    if (!Array.isArray(team.players) || team.players.length !== stored) {
      fail(`${where(t, team)}: expected ${stored} players.`);
    }
    team.players.forEach((player, p) => {
      if (!isText(player.name, NAME_LEN)) fail(`${where(t, team, p)}: names are up to 6 letters, digits or spaces.`);
      if (!Array.isArray(player.attrs) || player.attrs.length !== ATTR_COUNT || !player.attrs.every(isByte)) {
        fail(`${where(t, team, p)}: attrs must be ten whole numbers from 0 to 255.`);
      }
      if (p < ACTIVE_PLAYERS && !skillAllowed(profile, t, p, player.attrs[5])) {
        fail(`${where(t, team, p)}: skill ${player.attrs[5]} is out of range (0-4, shown as 1-5).`);
      }
    });
  });
}

/** Everything the profile does not let a person edit must equal the baseline. */
function checkReadOnly(profile, baseline, teams) {
  teams.forEach((team, t) => {
    const was = baseline[t];
    for (const f of profile.text) {
      if (!f.editable && team[f.key] !== was[f.key]) {
        fail(`${where(t, was)}: the team ${f.json} is built into this ROM's menus and bracket, so it can't change here.`);
      }
    }
    team.players.forEach((player, p) => {
      const before = was.players[p];
      if (p >= ACTIVE_PLAYERS) {
        if (player.name !== before.name || !sameTeams(player.attrs, before.attrs)) {
          fail(`${where(t, was, p)}: stored players the game doesn't load can't be changed.`);
        }
        return;
      }
      if (player.attrs[5] > 4 && player.attrs[5] !== before.attrs[5]) {
        fail(`${where(t, was, p)}: the original skill exception can only be kept unchanged. Choose a skill from 1 to 5.`);
      }
      ATTR_BITS.forEach((bits, a) => {
        if ((player.attrs[a] & ~bits) !== (before.attrs[a] & ~bits)) {
          fail(`${where(t, was, p)}: attrs[${a}] differs from the ROM, but only name, skill, batting, pitching and speed can change.`);
        }
      });
    });
  });
}

/**
 * True when exporting `teams` from a ROM of `variant` (an id) needs the
 * own-colors upgrade: the ROM's records are shared and a color differs from
 * the baseline it opened with.
 */
export function needsColorUpgrade(variant, baseline, teams) {
  return VARIANTS.find((v) => v.id === variant)?.writableColors === false && colorsChanged(baseline, teams);
}

const UPGRADE_REFUSED = 'Roster Lab couldn’t add own team colors to this ROM';

/**
 * Turn `out`, an admitted copy of `legacy`, into the own-colors variant: the
 * three routine constants plus every team's record seeded from the copy's own
 * shared records. Each guard below restates something the legacy digest
 * already pins, so a broken registry fails here instead of writing a bad ROM.
 */
async function addOwnColors(out, legacy, registry) {
  const target = registry.find((v) => v.id === legacy.upgrade) ?? fail(`${UPGRADE_REFUSED}.`);
  const { routine, before, after, padding, pointer } = OWN_COLORS;
  const source = out.slice();
  if (!before.every((b, i) => source[routine + i] === b)) fail(`${UPGRADE_REFUSED}: its palette routine isn’t as built.`);
  if (source[pointer] !== 0xc0 || source[pointer + 1] !== 0xfa) fail(`${UPGRADE_REFUSED}: its color pointer isn’t as built.`);
  if (!source.subarray(padding[0], padding[1]).every((b) => b === 0xff)) fail(`${UPGRADE_REFUSED}: its spare space is in use.`);
  const seed = Array.from({ length: target.layout.teamCount }, (_, t) => source.subarray(legacy.uniform(t), legacy.uniform(t) + 3));
  if (!seed.every((record) => record.every(isColor))) fail(`${UPGRADE_REFUSED}: its color records aren’t NES colors.`);

  out.set(after, routine);
  seed.forEach((record, t) => out.set(record, target.uniform(t)));

  const ledger = new Set(after.flatMap((b, i) => (b === before[i] ? [] : [routine + i])));
  for (let t = 0; t < target.layout.teamCount; t++) for (let s = 0; s < 3; s++) ledger.add(target.uniform(t) + s);
  let changed = 0;
  for (let i = 0; i < out.length; i++) {
    if (out[i] === source[i]) continue;
    if (!ledger.has(i)) fail(`${UPGRADE_REFUSED}: the upgrade touched an unexpected byte.`);
    changed += 1;
  }
  if (changed !== ledger.size) fail(`${UPGRADE_REFUSED}: the upgrade is incomplete.`);
  if (await admit(out, registry) !== target) fail(`${UPGRADE_REFUSED}: the upgraded copy isn’t a known ROM.`);
  return { target, ledger };
}

/**
 * Copy `source` and write only the fields where `teams` differs from `baseline`,
 * the roster `source` opened as. A legacy Preview 8 source whose final colors
 * differ from the baseline is upgraded to own colors first; nothing else ever
 * changes a source's variant. The copy must reopen as the expected variant and
 * as the same roster, with every changed bit writable. `registry` is the
 * production VARIANTS; tests pass copies whose digests describe synthetic images.
 */
export async function writeRom(source, profile, baseline, teams, registry = VARIANTS) {
  checkValues(profile, teams);
  checkReadOnly(profile, baseline, teams);
  const opened = await admit(source, registry);
  if (opened.layout !== profile) fail(`The open ROM is the ${opened.layout.name} layout, not ${profile.name}.`);
  if (!sameTeams(readTeams(source, opened), baseline)) fail('The roster baseline doesn’t describe the open ROM.');
  const out = source.slice();
  let variant = opened;
  let ledger = null;
  if (!opened.writableColors && colorsChanged(baseline, teams)) ({ target: variant, ledger } = await addOwnColors(out, opened, registry));

  teams.forEach((team, t) => {
    const was = baseline[t];
    for (const f of profile.text) {
      if (f.editable && team[f.key] !== was[f.key]) writeText(out, f.at(t), f.width(t), team[f.key]);
    }
    team.ratings.forEach((v, r) => {
      if (v !== was.ratings[r]) out[profile.rating(t) + r] = v;
    });
    UNIFORM_SLOTS.forEach((slot, s) => {
      if (team.uniform[slot] !== was.uniform[slot]) out[variant.uniform(t) + s] = team.uniform[slot];
    });
    for (let p = 0; p < ACTIVE_PLAYERS; p++) {
      const player = team.players[p];
      const before = was.players[p];
      const rec = profile.record(t, p);
      if (player.name !== before.name) writeText(out, rec, NAME_LEN, player.name);
      ATTR_BITS.forEach((bits, a) => {
        const at = rec + NAME_LEN + a;
        if (bits && player.attrs[a] !== before.attrs[a]) out[at] = (out[at] & ~bits) | (player.attrs[a] & bits);
      });
    }
  });

  const reopened = await readRom(out, registry);
  if (reopened.variant !== variant.id) fail('The exported ROM did not read back as the expected ROM variant.');
  if (!sameTeams(reopened.teams, teams)) fail('The exported ROM did not read back as the edited roster.');
  const mask = writableMask(opened);
  for (let i = 0; i < out.length; i++) {
    if ((out[i] ^ source[i]) & ~mask[i] & 0xff && !ledger?.has(i)) fail('The exported ROM changed bytes Roster Lab doesn’t edit.');
  }
  return out;
}

function readTextField(value, width, label, centered) {
  if (typeof value !== 'string' || value.length > width || !TEXT.test(value)) {
    fail(`${label} must be up to ${width} capital letters, digits or spaces.`);
  }
  return canonical(value, centered);
}

const isOldPadding = (p) =>
  isObject(p) && p.name === '' && Array.isArray(p.attrs) && p.attrs.length === ATTR_COUNT && p.attrs.every((v) => v === 0);

/**
 * Read a roster document's shape. Accepts version 3 with team colors, version
 * 2 and version 1 from earlier editors, and unversioned `{rom, teams}` files
 * (the bundled previews and tools/roster.py extracts). Fields a file omits
 * stay undefined so `fitRoster` can fill them: text from the baseline, colors
 * from the current draft. Team colors are read only from version 3 or from a
 * roster.py `uniform`; the old two-color `colors` object is never read.
 * @returns {{profile, teams: object[], notices: string[]}}
 */
export function readRosterFile(doc) {
  if (!isObject(doc)) fail('This file isn’t a Roster Lab roster.');
  let profile;
  const current = doc.format === FORMAT && doc.version === 3;
  const unversioned = doc.version === undefined && doc.format === undefined && typeof doc.rom === 'string';
  const legacy = doc.version === 1 || unversioned;
  if (doc.format === FORMAT && (doc.version === 2 || current)) {
    profile = PROFILES.find((p) => p.id === doc.profile) ?? fail(`Unknown roster layout ${JSON.stringify(doc.profile)}.`);
  } else if (legacy) {
    profile = PROFILES.find((p) => p.teamCount === doc.teams?.length) ?? fail('Older roster files must have 16 or 32 teams.');
  } else {
    fail('This roster file version isn’t supported.');
  }
  if (!Array.isArray(doc.teams) || doc.teams.length !== profile.teamCount) fail(`Expected ${profile.teamCount} teams.`);
  const colorsAllowed = current || unversioned;
  if (!colorsAllowed && (Object.hasOwn(doc, 'palette') || doc.teams.some((raw) => isObject(raw) && Object.hasOwn(raw, 'uniform')))) {
    fail('Team colors need roster version 3.');
  }
  if ((current || Object.hasOwn(doc, 'palette')) && doc.palette !== PALETTE) {
    fail(doc.palette === undefined
      ? `Version 3 rosters must name their color palette, "${PALETTE}".`
      : `This file's team colors use the palette ${shown(doc.palette)}, but Roster Lab reads "${PALETTE}".`);
  }

  let dropped = 0;
  let oldColors = false;
  const teams = doc.teams.map((raw, t) => {
    if (!isObject(raw)) fail(`${where(t)} is not an object.`);
    if (raw.id !== t) fail(`${where(t)} has id ${JSON.stringify(raw.id)}; teams must be listed in order from id 0.`);
    const team = { id: t };
    for (const f of profile.text) {
      const value = legacy && f.key === 'shortName' && raw[f.json] === '' ? undefined : raw[f.json];
      team[f.key] = value === undefined ? undefined : readTextField(value, f.width(t), `${where(t)} ${f.json.replace('_', ' ')}`, f.centered);
    }
    if (!Array.isArray(raw.ratings)) fail(`${where(t, team)}: ratings are missing.`);
    team.ratings = [...raw.ratings];
    if (current || (colorsAllowed && raw.uniform !== undefined)) {
      checkUniform(raw.uniform, where(t, team));
      team.uniform = copyUniform(raw.uniform);
    }
    if (raw.colors !== undefined) oldColors = true;
    if (!Array.isArray(raw.players)) fail(`${where(t, team)}: players are missing.`);
    let players = raw.players;
    const stored = profile.storedCount(t);
    if (legacy && profile === PREVIEW8 && stored === ACTIVE_PLAYERS && players.length === 20) {
      if (!players.slice(stored).every(isOldPadding)) {
        fail(`${where(t, team)} has 20 players, but Preview 8 stores 15 for this team. Players 16-20 aren't ` +
          'the blank placeholders an older editor added, so the file can’t be converted. Move them into players 1-15 or delete them.');
      }
      players = players.slice(0, stored);
      dropped += 20 - stored;
    }
    if (players.length !== stored) fail(`${where(t, team)}: expected ${stored} players, found ${players.length}.`);
    team.players = players.map((rawPlayer, p) => {
      if (!isObject(rawPlayer)) fail(`${where(t, team, p)} is not an object.`);
      if (!Array.isArray(rawPlayer.attrs)) fail(`${where(t, team, p)}: attrs are missing.`);
      return { name: readTextField(rawPlayer.name, NAME_LEN, `${where(t, team, p)} name`), attrs: [...rawPlayer.attrs] };
    });
    return team;
  });
  const notices = [];
  if (dropped) notices.push(`Removed ${dropped} blank placeholder players that an older editor added to the original 16 teams.`);
  if (oldColors) notices.push('Ignored the old two-color fields; they don’t match the game’s cap, jersey and hair records.');
  return { profile, teams, notices };
}

/**
 * Fit a read document onto the roster it will edit. Missing text keeps the
 * baseline's value, and missing team colors keep the colors of `draft`, the
 * roster being edited, so a colorless file never undoes color edits.
 * Read-only fields and records must match the baseline.
 */
export function fitRoster({ profile, teams }, baseline, draft = baseline) {
  if (baseline.length !== profile.teamCount || draft.length !== profile.teamCount) {
    fail(`This roster is for the ${profile.name} layout, not the open one.`);
  }
  const fitted = teams.map((team, t) => {
    const out = { id: t };
    for (const f of profile.text) out[f.key] = team[f.key] ?? baseline[t][f.key];
    out.ratings = team.ratings;
    out.uniform = copyUniform(team.uniform ?? draft[t].uniform);
    out.players = team.players;
    return out;
  });
  checkValues(profile, fitted);
  checkReadOnly(profile, baseline, fitted);
  return fitted;
}

/**
 * Build a preview roster from a bundled roster file and, for Preview 8, its
 * team metadata. Teams wear the original ROMs' colors: record t, or t & 15 on
 * Preview 8, as the unedited release shows them.
 */
export function previewRoster(profile, doc, meta) {
  const read = readRosterFile(doc);
  if (read.profile !== profile || read.notices.length) fail(`The bundled ${profile.name} roster has the wrong shape.`);
  const teams = read.teams.map((team, t) => {
    const known = meta?.teams?.[t];
    if (meta && known?.id !== t) fail(`Bundled team metadata is out of order at team ${t + 1}.`);
    const out = { id: t };
    for (const f of profile.text) {
      if (team[f.key] !== undefined && known?.[f.json] !== undefined && team[f.key] !== known[f.json]) {
        fail(`Bundled ${where(t)} ${f.json} disagrees with the team metadata.`);
      }
      out[f.key] = team[f.key] ?? known?.[f.json];
    }
    out.ratings = team.ratings;
    out.uniform = team.uniform ? copyUniform(team.uniform) : uniformOf(NATIVE_UNIFORMS[t & 15]);
    out.players = team.players;
    return out;
  });
  checkValues(profile, teams);
  return teams;
}

/** Version 3 roster document: every stored record, all ten attrs bytes and every team's colors. */
export function rosterJson(profile, teams, source) {
  return {
    format: FORMAT,
    version: 3,
    profile: profile.id,
    palette: PALETTE,
    ...(source && { source }),
    teams: teams.map((team) => {
      const out = { id: team.id };
      for (const f of profile.text) out[f.json] = team[f.key];
      out.ratings = [...team.ratings];
      out.uniform = copyUniform(team.uniform);
      out.players = team.players.map(({ name, attrs }) => ({ name, attrs: [...attrs] }));
      return out;
    }),
  };
}
