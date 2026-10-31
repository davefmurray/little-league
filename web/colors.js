/**
 * FCEUX's default palette, the table the project's art tools use
 * (tools/menu32_convert.py FCEUX_6BIT, each channel (v << 2) | (v >> 4)).
 * Real consoles and TVs differ, so these are approximate.
 */
export const NES_RGB = Object.freeze([
  '#757575', '#24188e', '#0000aa', '#45009e', '#8e0075', '#aa0010', '#a60000', '#7d0800',
  '#412c00', '#004500', '#005100', '#003c14', '#183c5d', '#000000', '#000000', '#000000',
  '#bebebe', '#0071ef', '#2038ef', '#8200f3', '#be00be', '#e70059', '#db2800', '#cb4d0c',
  '#8a7100', '#009600', '#00aa00', '#009238', '#00828a', '#000000', '#000000', '#000000',
  '#ffffff', '#3cbeff', '#5d96ff', '#cf8aff', '#f779ff', '#ff75b6', '#ff7561', '#ff9a38',
  '#f3be3c', '#82d310', '#4ddf49', '#59fb9a', '#00ebdb', '#797979', '#000000', '#000000',
  '#ffffff', '#aae7ff', '#c7d7ff', '#d7cbff', '#ffc7ff', '#ffc7db', '#ffbeb2', '#ffdbaa',
  '#ffe7a2', '#e3ffa2', '#aaf3be', '#b2ffcf', '#9efff3', '#c7c7c7', '#000000', '#000000',
]);

const SAME_BLACK = 'black, same as $0F';

const NAMES = Object.freeze([
  'gray', 'indigo', 'dark blue', 'dark violet', 'plum', 'crimson', 'dark red', 'maroon',
  'dark olive', 'dark green', 'forest green', 'dark sea green', 'navy teal', 'below black', SAME_BLACK, 'black',
  'light gray', 'azure', 'royal blue', 'violet', 'magenta', 'raspberry', 'red', 'burnt orange',
  'olive', 'green', 'bright green', 'sea green', 'teal', SAME_BLACK, SAME_BLACK, SAME_BLACK,
  'white', 'sky blue', 'cornflower', 'lavender', 'orchid', 'pink', 'salmon', 'orange',
  'gold', 'lime', 'light green', 'mint', 'aqua', 'gray, varies by TV', SAME_BLACK, SAME_BLACK,
  'white, same as $20', 'pale sky blue', 'pale blue', 'pale lavender', 'pale orchid', 'pale pink', 'peach', 'tan',
  'cream', 'pale lime', 'pale green', 'pale mint', 'pale aqua', 'light gray, varies by TV', SAME_BLACK, SAME_BLACK,
]);

/** The basic picker: hues $x0-$xC of the four brightness rows, then the usual black $0F. */
export const BASIC_COLORS = Object.freeze([
  ...Array.from({ length: 4 * 13 }, (_, i) => 16 * Math.floor(i / 13) + (i % 13)),
  0x0f,
]);

export const BELOW_BLACK = 0x0d;
export const BELOW_BLACK_NOTE = 'Below-black $0D can cause display issues on some original hardware; $0F is the usual black.';

export const hexCode = (code) => `$${code.toString(16).toUpperCase().padStart(2, '0')}`;
export const colorName = (code) => NAMES[code];

export const describeColor = (code) => `${hexCode(code)} (${code}) ${colorName(code)}`;

/**
 * Read an exact code typed as decimal ("27") or hex ("$1B"). Anything else,
 * including "27x", "1.5", "-1" and values past 63, is refused, never trimmed
 * into range.
 * @returns {{value: number} | {error: string}}
 */
export function parseColorCode(text) {
  const typed = String(text).trim();
  const hex = /^\$([0-9a-f]{1,2})$/i.exec(typed);
  if (!hex && !/^\d{1,2}$/.test(typed)) return { error: 'Type a code from 0 to 63, or $00 to $3F.' };
  const value = hex ? parseInt(hex[1], 16) : Number(typed);
  if (value > 0x3f) return { error: `${typed} is past the last NES color code, 63 ($3F).` };
  return { value };
}

/**
 * Where the game draws the batter at the plate in the batting view: 26 8x8
 * sprites from CHR 4K bank 8, as [x, y, tile, attributes] inside a 49x58 box,
 * in OAM order (earlier sprites draw on top). Numeric pose data only; every
 * pixel comes from the opened ROM. Measured on the repo's CPU/PPU model in an
 * Exhibition game, the same frame as the reviewed role map.
 */
export const BATTER = Object.freeze({
  width: 49,
  height: 58,
  chrBank: 8,
  /** The field's 16-byte sprite palette record (palette set $85), fixed bank. */
  paletteRecord: 0xf9d0,
  sprites: Object.freeze([
    [36, -3, 0x97, 0x40], [28, -3, 0x98, 0x40], [36, 5, 0x99, 0x40], [28, 5, 0x9a, 0x40],
    [40, 15, 0xaf, 0x40], [32, 15, 0xb0, 0x40], [40, 23, 0xb1, 0x40], [32, 23, 0xb2, 0x40],
    [39, 34, 0x9f, 0x40], [37, 42, 0xa0, 0x40], [38, 50, 0xa1, 0x40], [30, 50, 0xa2, 0x40],
    [41, 27, 0xa5, 0x43], [33, 27, 0xa6, 0x43], [41, 35, 0xa7, 0x43], [33, 35, 0xa8, 0x43],
    [36, 43, 0xa9, 0x43], [16, 16, 0xb3, 0x43], [8, 15, 0xb4, 0x43], [0, 15, 0xb5, 0x43],
    [37, 8, 0xaa, 0x42], [29, 8, 0xb6, 0x42], [21, 8, 0xb7, 0x42], [23, 16, 0xb8, 0x42],
    [12, 15, 0xfd, 0x03], [12, 41, 0xff, 0x03],
  ].map((sprite) => Object.freeze(sprite))),
});

/**
 * Decode the batter from an admitted ROM. Each pixel holds its sprite palette
 * entry, 4 * palette + color (0 is clear), and `palette` is the ROM's field
 * sprite palette record.
 * @returns {{width: number, height: number, pixels: Uint8Array, palette: number[]}}
 */
export function batterPicture(rom) {
  const { width, height, chrBank, paletteRecord, sprites } = BATTER;
  const prgBanks = rom[4];
  const chr = 16 + prgBanks * 0x4000 + chrBank * 0x1000;
  const record = 16 + (prgBanks - 1) * 0x4000 + paletteRecord - 0xc000;
  const pixels = new Uint8Array(width * height);
  for (let i = sprites.length - 1; i >= 0; i--) {
    const [x, y, tile, attr] = sprites[i];
    for (let r = 0; r < 8; r++) {
      const row = chr + 16 * tile + (attr & 0x80 ? 7 - r : r);
      for (let c = 0; c < 8; c++) {
        const bit = attr & 0x40 ? c : 7 - c;
        const color = ((rom[row] >> bit) & 1) | (((rom[row + 8] >> bit) & 1) << 1);
        const px = x + c;
        const py = y + r;
        if (color && px >= 0 && px < width && py >= 0 && py < height) pixels[py * width + px] = 4 * (attr & 3) + color;
      }
    }
  }
  return { width, height, pixels, palette: Array.from(rom.subarray(record, record + 16)) };
}

/**
 * The NES code a batter pixel shows for a team: the field routine puts the
 * batting team's jersey and cap in sprite palette 0 entries 2 and 3, and its
 * hair in sprite palette 2 entry 3. Outline, skin and bat colors come from the
 * ROM's record.
 */
export function batterColor(entry, palette, uniform) {
  if (entry === 2) return uniform.jersey;
  if (entry === 3) return uniform.cap;
  if (entry === 11) return uniform.hair;
  return palette[entry];
}
