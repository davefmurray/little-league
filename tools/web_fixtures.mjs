// Synthetic ROM images for the web editor tests. No ROM bytes: every image is a
// deterministic filler pattern with roster data (made up, or the bundled preview
// JSON) written at the measured file offsets of the two supported ROMs. Offsets
// and the writable mask are written out independently of web/rom.js so the
// tests cross-check it.
import { createHash } from 'node:crypto';
import { PREVIEW8, STOCK16 } from '../web/rom.js';

export const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const pad2 = (n) => String(n).padStart(2, '0');

const ACTIVE = 15;
export const lowRecord = (t, p) => 0x10430 + 0x120 * t + 16 * p;
export const p8Record = (t, p) => (t < 16 ? lowRecord(t, p) : 0x21710 + 0x170 * (t - 16) + 16 * p);
const p8Stored = (t) => (t < 16 ? 15 : 20);
export const p8Rating = (t) => 0xfc90 + 4 * t;
export const p8Name = (t) => (t < 16 ? 0x5190 + 16 * t : 0x7cd0 + 16 * (t - 16));
export const p8Code = (t) => 0x2f010 + 4 * t;
const p8Region = (t) => 0x2aa10 + 8 * t;
export const stockRating = (t) => 0xf234 + 4 * t;
export const stockName = (t) => 0x5190 + 16 * t;
export const STOCK_SHORT_WIDTHS = [10, 11, 13, 14, 10, 11, 12, 10, 10, 10, 12, 10, 10, 10, 11, 10];
const shortEntry = (t) => 0x52b0 + STOCK_SHORT_WIDTHS.slice(0, t).reduce((sum, w) => sum + w + 2, 0);
export const stockShortText = (t) => shortEntry(t) + 1;
export const stockShortPointer = (t) => 0x5290 + 2 * t;

export const LAYOUTS = {
  preview8: { size: 393232, prg: 16, teams: 32, record: p8Record, stored: p8Stored, rating: p8Rating },
  stock16: { size: 262160, prg: 8, teams: 16, record: lowRecord, stored: () => 15, rating: stockRating },
};

function ascii(bytes, off, width, text) {
  for (let i = 0; i < width; i++) bytes[off + i] = i < text.length ? text.charCodeAt(i) : 0x20;
}

const fixtureName = (t, p) => (p % 2 ? `P${p}T${t}` : `T${pad2(t)}P${pad2(p)}`);
const REGIONS = ['ASIA', 'AMERICA', 'EUROPE'];

/** A made-up roster with the real one's quirks: 15/20 records and one stored skill of 7. */
function syntheticTeams(kind) {
  const layout = LAYOUTS[kind];
  return Array.from({ length: layout.teams }, (_, t) => ({
    id: t,
    name: kind === 'preview8' ? `TEAM ${t}` : `CLUB ${t}`,
    code: `T${pad2(t)}`,
    region: REGIONS[t % 3],
    shortName: `CLUB${t}`,
    ratings: [0, 1, 2, 3].map((r) => ((t + r) % 4) + 1),
    players: Array.from({ length: layout.stored(t) }, (_, p) => ({
      name: fixtureName(t, p),
      attrs: [
        (t + p) % 3 | (p % 4 === 1 ? 0x80 : 0), 0xff, (p < 3 ? 0x80 : 0) | (p * 4), (t * 16 + p) & 0xff,
        0x90 | ((t + 2 * p) & 0x0f), t === 4 && p === 2 ? 7 : (t + p) % 5, p < 3 ? 8 * (p + 1) : 0, 0, p % 3, 0,
      ],
    })),
  }));
}

/** Write `teams` at the measured offsets of a deterministic filler image. */
function image(kind, teams) {
  const layout = LAYOUTS[kind];
  const bytes = new Uint8Array(layout.size);
  for (let i = 16; i < bytes.length; i++) bytes[i] = (i * 31 + 7) & 0xff;
  bytes.set([0x4e, 0x45, 0x53, 0x1a, layout.prg, 16, 0x10, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  teams.forEach((team, t) => {
    team.players.forEach((player, p) => {
      ascii(bytes, layout.record(t, p), 6, player.name);
      bytes.set(player.attrs, layout.record(t, p) + 6);
    });
    bytes.set(team.ratings, layout.rating(t));
    if (kind === 'preview8') {
      ascii(bytes, p8Name(t), 14, team.name);
      bytes.set([0xff, 0xff], p8Name(t) + 14);
      ascii(bytes, p8Code(t), 4, team.code);
      ascii(bytes, p8Region(t), 8, team.region.padStart(team.region.length + ((8 - team.region.length) >> 1)));
    } else {
      ascii(bytes, stockName(t), 14, team.name);
      bytes.set([0xff, 0xff], stockName(t) + 14);
      const entry = shortEntry(t);
      const cpu = entry - 0x4010 + 0x8000;
      bytes.set([cpu & 0xff, cpu >> 8], stockShortPointer(t));
      bytes[entry] = 4;
      ascii(bytes, entry + 1, STOCK_SHORT_WIDTHS[t], team.shortName);
      bytes[entry + 1 + STOCK_SHORT_WIDTHS[t]] = 0xff;
    }
  });
  if (kind === 'preview8') {
    for (let t = 0; t < 16; t++) for (let r = 0; r < 4; r++) bytes[stockRating(t) + r] = ((t + r + 1) % 4) + 1;
  }
  return bytes;
}

/** The bits the editor contract allows to change, per byte. */
export function writableMask(kind) {
  const layout = LAYOUTS[kind];
  const mask = new Uint8Array(layout.size);
  for (let t = 0; t < layout.teams; t++) {
    for (let p = 0; p < ACTIVE; p++) {
      const rec = layout.record(t, p);
      mask.fill(0xff, rec, rec + 6);
      mask[rec + 9] = 0xff;
      mask[rec + 10] = 0x0f;
      mask[rec + 11] = 0xff;
    }
    mask.fill(0xff, layout.rating(t), layout.rating(t) + 4);
    if (kind === 'stock16') {
      mask.fill(0xff, stockName(t), stockName(t) + 14);
      mask.fill(0xff, stockShortText(t), stockShortText(t) + STOCK_SHORT_WIDTHS[t]);
    }
  }
  return mask;
}

export const maskedDigest = (bytes, mask) => sha256(bytes.map((b, i) => b & ~mask[i]));

/** A synthetic image plus a test-only profile whose digests describe it. */
export function fixture(kind, teams = syntheticTeams(kind)) {
  const bytes = image(kind, teams);
  const production = kind === 'preview8' ? PREVIEW8 : STOCK16;
  return {
    bytes,
    profile: { ...production, maskedSha256: maskedDigest(bytes, writableMask(kind)), originalSha256: sha256(bytes) },
  };
}
