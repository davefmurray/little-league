// Export team-color cases through the web editor's own adapter, so the Python
// checks in tools/test_colors32.py and tools/test_roster.py run on what Roster
// Lab actually writes, never on a hand-patched copy.
//
//   node tools/web_colors_export.mjs [--synthetic] SOURCE.nes OUTPUT.nes CASE
//   node tools/web_colors_export.mjs --fixture preview8|stock16 OUTPUT.nes
//
// CASE:
//   venezuela        Preview 8 team 20 to cap $16, jersey $30, hair $38
//   seeded           venezuela, reopened, then set back: an upgraded copy where
//                    every team still wears its old shared record
//   distinct         every team gets its own cap, jersey and hair
//   import:FILE      fit a roster file onto the ROM as Import JSON does, then export
//
// --synthetic admits SOURCE with a test-only registry made from its own bytes,
// for synthetic CI images. --fixture writes the synthetic image the web tests
// use. Outputs are created exclusively: an existing file, including SOURCE,
// is never overwritten.
import { readFileSync, writeFileSync } from 'node:fs';
import { VARIANTS, fitRoster, readRom, readRosterFile, writeRom } from '../web/rom.js';
import { fixture, testVariants } from './web_fixtures.mjs';

const args = process.argv.slice(2);
const usage = () => {
  console.error('usage: node tools/web_colors_export.mjs [--synthetic] SOURCE.nes OUTPUT.nes CASE\n' +
    '       node tools/web_colors_export.mjs --fixture preview8|stock16 OUTPUT.nes');
  process.exit(2);
};

if (args[0] === '--fixture') {
  const [, kind, output] = args;
  if (!['preview8', 'stock16'].includes(kind) || !output) usage();
  writeFileSync(output, fixture(kind).bytes, { flag: 'wx' });
  console.log(`wrote synthetic ${kind} image ${output}`);
  process.exit(0);
}

const synthetic = args[0] === '--synthetic';
const [source, output, kase] = synthetic ? args.slice(1) : args;
if (!source || !output || !kase) usage();

const bytes = new Uint8Array(readFileSync(source));
const registry = synthetic ? testVariants(bytes[4] === 16 ? 'preview8' : 'stock16', bytes) : VARIANTS;
const rom = await readRom(bytes, registry);
const recolor = (teams, t, uniform) => {
  const out = structuredClone(teams);
  out[t].uniform = uniform;
  return out;
};

let out;
if (kase === 'venezuela' || kase === 'seeded') {
  out = await writeRom(bytes, rom.profile, rom.teams, recolor(rom.teams, 19, { cap: 0x16, jersey: 0x30, hair: 0x38 }), registry);
  if (kase === 'seeded') {
    const up = await readRom(out, registry);
    out = await writeRom(out, up.profile, up.teams, recolor(up.teams, 19, rom.teams[19].uniform), registry);
  }
} else if (kase === 'distinct') {
  const teams = structuredClone(rom.teams);
  teams.forEach((team, t) => { team.uniform = { cap: (2 * t + 1) & 0x3f, jersey: (2 * t) & 0x3f, hair: (t + 0x20) & 0x3f }; });
  out = await writeRom(bytes, rom.profile, rom.teams, teams, registry);
} else if (kase.startsWith('import:')) {
  const read = readRosterFile(JSON.parse(readFileSync(kase.slice('import:'.length), 'utf8')));
  out = await writeRom(bytes, rom.profile, rom.teams, fitRoster(read, rom.teams), registry);
} else {
  usage();
}

const back = await readRom(out, registry);
writeFileSync(output, out, { flag: 'wx' });
console.log(`exported ${output} (${kase}): ${out.reduce((n, b, i) => n + (b !== bytes[i]), 0)} bytes differ from ${source}; variant ${back.variant}`);
