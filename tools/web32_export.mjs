// Export a Preview 8 copy with every editable field changed, through the web
// editor's own adapter. tools/test_web32_runtime.py runs the CPU checks on it.
//
//   node tools/web32_export.mjs build/homerunart32.nes /tmp/edited.nes
import { readFileSync, writeFileSync } from 'node:fs';
import { ACTIVE_PLAYERS, PREVIEW8, openRom, writeRom } from '../web/rom.js';

const [source, output] = process.argv.slice(2);
if (!source || !output) {
  console.error('usage: node tools/web32_export.mjs SOURCE.nes OUTPUT.nes');
  process.exit(2);
}

const bytes = new Uint8Array(readFileSync(source));
const rom = await openRom(bytes);
if (rom.profile !== PREVIEW8 || !rom.exact) throw new Error(`${source} is not the original Preview 8 ROM`);

const teams = structuredClone(rom.teams);
teams.forEach((team, t) => {
  team.ratings = team.ratings.map((v) => (v % 4) + 1);
  team.players.slice(0, ACTIVE_PLAYERS).forEach((player, p) => {
    player.name = `E${String(t).padStart(2, '0')}P${String(p).padStart(2, '0')}`;
    player.attrs[3] ^= 0xff;
    player.attrs[4] = (player.attrs[4] & 0xf0) | ((player.attrs[4] & 0x0f) ^ 0x0f);
    player.attrs[5] = player.attrs[5] === 7 ? 0 : (player.attrs[5] + 1) % 5;
  });
});

const out = await writeRom(bytes, PREVIEW8, rom.teams, teams);
writeFileSync(output, out, { flag: 'wx' });
console.log(`exported ${output}: ${out.reduce((n, b, i) => n + (b !== bytes[i]), 0)} bytes differ from ${source}`);
