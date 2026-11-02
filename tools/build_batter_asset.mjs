import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { batterPicture } from '../web/colors.js';

export const SOURCE_SHA256 = 'a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b';
const COMMAND = 'node tools/build_batter_asset.mjs build/homerunart32.nes > web/assets/game/batter.json';

/** The asset text for `rom`: one string per pixel row, each pixel a palette entry in hex, '.' when clear. */
export function batterAssetText(rom) {
  const sha256 = createHash('sha256').update(rom).digest('hex');
  if (sha256 !== SOURCE_SHA256) throw new Error(`Expected the Preview 8 ROM (SHA-256 ${SOURCE_SHA256}), got ${sha256}.`);
  const { width, height, pixels, palette } = batterPicture(rom);
  const rows = Array.from({ length: height }, (_, y) =>
    Array.from(pixels.subarray(y * width, (y + 1) * width), (entry) => (entry ? entry.toString(16) : '.')).join(''));
  const source = { rom: 'little-league-32-team.nes (Preview 8)', sha256, decoder: 'batterPicture() in web/colors.js', command: COMMAND };
  return [
    '{',
    '  "format": "roster-lab-batter",',
    '  "version": 1,',
    `  "source": ${JSON.stringify(source)},`,
    `  "width": ${width},`,
    `  "height": ${height},`,
    `  "palette": ${JSON.stringify(palette)},`,
    '  "rows": [',
    rows.map((row) => `    "${row}"`).join(',\n'),
    '  ]',
    '}',
    '',
  ].join('\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [path] = process.argv.slice(2);
  if (!path) {
    console.error(`usage: ${COMMAND}`);
    process.exit(2);
  }
  process.stdout.write(batterAssetText(new Uint8Array(readFileSync(path))));
}
