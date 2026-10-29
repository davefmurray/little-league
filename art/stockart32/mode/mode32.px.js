// Mode menu: the sunny ballpark gate with the stock characters. 256x240, exact NES colors, navy $0C
// backdrop. Every 16x16 cell keeps to one of four palettes (layout.json); the menu text sits in P0,
// whose cream (value 2, as in every palette) is the stock font's ink. P2 and P3 both hold the stock
// skin $36, so a face split between a red- and a blue-shirted crowd metatile keeps one color:
//   P0 sky $21, cream $38, gold $28   sky, clouds, sign, scoreboard, flags, light towers
//   P1 sky $21, cream $38, green $1A  lawn
//   P2 red $16, cream $38, skin $36   brick, bunting, red-shirted stock crowd, cheerleader, pair
//   P3 blue $12, cream $38, skin $36  blue-shirted stock crowd (the stock crowd alternates shirts)
// Navy is free in every cell: outlines, hair, mortar, the board. CHR $06 holds 256 patterns, 24 of them
// the stock font at its ASCII ids, so the art has 232.
pal({
  k: "#183C5D",  // $0C navy backdrop
  s: "#3CBEFF",  // $21 sky
  c: "#FFE7A2",  // $38 cream
  y: "#F3BE3C",  // $28 gold
  g: "#00AA00",  // $1A green
  r: "#DB2800",  // $16 red
  t: "#FFBEB2",  // $36 stock skin
  b: "#2038EF",  // $12 blue
})

// ---------- sky ----------
function cloud(c, x, y, puffs) {
  for (const [dx, dy, r] of puffs) c.circ(x + dx, y + dy, r, "c")
  const x0 = Math.min(...puffs.map(([dx, , r]) => dx - r)), x1 = Math.max(...puffs.map(([dx, , r]) => dx + r))
  const base = Math.max(...puffs.map(([, dy]) => dy))
  c.rect(x + x0 + 2, y + base, x1 - x0 - 3, 3, "c")
}
function lightTower(c, x, y) {
  c.rect(x, y, 20, 14, "k")
  for (let j = 0; j < 2; j++) for (let i = 0; i < 4; i++) c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "c")
  c.rect(x + 8, y + 14, 4, 60, "k")
  c.hline(x - 1, y + 14, 22, "k")
}
function pennant(c, x, y, ink) {
  c.vline(x, y, 44 - y, "k")
  c.px(x, y - 1, "y")
  c.grid(x + 1, y, `
  kkk.......
  iiikkk....
  iiiiiikkk.
  iiiikkk...
  ikkk......`.replace(/i/g, ink))
}

// ---------- sign and scoreboard ----------
function marquee(c) {
  // flat-topped sign with an arched crest over the middle; navy outline, gold band, bulbs
  const cx = 127.5, cy = 22, R = 14
  const outer = (x, y) => (x >= 64 && x <= 191 && y >= 16 && y <= 45 && !((x === 64 || x === 191) && y === 16))
    || Math.hypot(x - cx, y - cy) <= R
  const inner = (x, y) => (x >= 69 && x <= 186 && y >= 21) || (Math.hypot(x - cx, y - cy) <= R - 4 && y >= 11)
  for (let y = 6; y <= 45; y++) for (let x = 63; x <= 192; x++) {
    if (!outer(x, y)) continue
    const edge = !outer(x - 1, y) || !outer(x + 1, y) || !outer(x, y - 1)
    c.px(x, y, inner(x, y) || edge ? "k" : "y")
  }
  for (let x = 72; x < 186; x += 8) if (Math.abs(x + 0.5 - cx) > R - 1) c.rect(x, 18, 2, 2, "c")
  for (const a of [20, 50, 90, 130, 160]) {
    const t = a * Math.PI / 180
    c.rect(Math.round(cx + (R - 2) * Math.cos(t) - 0.5), Math.round(cy - (R - 2) * Math.sin(t) - 0.5), 2, 2, "c")
  }
  // emblem: a ball resting on two crossed bats
  c.line(118, 22, 125, 15, "y"); c.line(119, 22, 126, 15, "y"); c.px(117, 22, "y")
  c.line(137, 22, 130, 15, "y"); c.line(136, 22, 129, 15, "y"); c.px(138, 22, "y")
  c.grid(123, 12, `
  ...kkkk...
  .kkcccckk.
  .kcyccyck.
  kcyccccyck
  kcyccccyck
  kcyccccyck
  kcyccccyck
  .kcyccyck.
  .kkcccckk.
  ...kkkk...`)
  // a gold star between LITTLE and LEAGUE (the gap is art, not reserved text)
  c.grid(124, 24, `
  ...y...
  ...y...
  yyyyyyy
  .yyyyy.
  ..yyy..
  .yy.yy.
  .y...y.`)
}
function board(c) {
  c.rect(32, 44, 192, 79, "k")
  c.rect(33, 45, 190, 3, "y"); c.rect(33, 119, 190, 3, "y")
  c.rect(33, 45, 3, 76, "y"); c.rect(220, 45, 3, 76, "y")
  for (const y of [71, 95]) c.hline(36, y, 184, "y")
  for (const [x, y] of [[32, 44], [223, 44], [32, 122], [223, 122]]) c.px(x, y, "s")
  for (let x = 40; x < 220; x += 8) { c.px(x, 46, "c"); c.px(x, 120, "c") }
  for (let y = 52; y < 120; y += 8) { c.px(34, y, "c"); c.px(221, y, "c") }
}


// ---------- facade ----------
function bricks(c, x0, y0, w, h) {
  c.rect(x0, y0, w, h, "r")
  for (let y = y0; y < y0 + h; y++) {
    if (y % 4 === 3) { c.hline(x0, y, w, "k"); continue }
    const off = y % 8 < 4 ? 7 : 3
    for (let x = x0; x < x0 + w; x++) if (x % 8 === off) c.px(x, y, "k")
  }
}
function arch(c, x0, area) {
  // opening x0..x0+47, crown 134, springline 158; the stock crowd and a string of pennants inside
  const cx = x0 + 23.5, cy = 158
  for (let y = 128; y < 192; y++) for (let x = x0 - 4; x < x0 + 52; x++) {
    const d = Math.hypot(x - cx, Math.max(0, cy - y))
    if (d < 24) c.px(x, y, "k")
    else if (d < 27.5) c.px(x, y, d < 25 ? "k" : "c")
  }
  c.rect(cx - 2, 130, 4, 5, "c"); c.hline(cx - 2, 135, 4, "k")
  c.hline(x0 + 4, 140, 40, "c")
  for (let i = 0; i < 5; i++) c.grid(x0 + 5 + i * 8, 141, i & 1 ? "ccc\n.c." : "rrr\n.r.")
  c.stamp(area, x0, 160)
}
function bunting(c, x) {
  // half rosette under the board: red and cream pleats, navy middle with a cream star
  for (let y = 128; y < 145; y++) for (let i = 0; i < 32; i++) {
    const dx = i - 15.5, dy = y - 127.5, d = Math.hypot(dx, dy)
    if (d >= 16.5) continue
    const a = Math.atan2(dy, dx), pleat = Math.floor(a / (Math.PI / 8)) & 1
    c.px(x + i, y, d >= 15.5 ? "k" : d < 6 ? "k" : d < 7 ? "c" : pleat ? "c" : "r")
  }
  c.grid(x + 13, 128, "..c..\nccccc\n.ccc.\n.c.c.")
}
function lawn(c) {
  c.rect(0, 224, 256, 16, "g")
  c.hline(0, 224, 256, "k")
  for (let x = 0; x < 256; x += 16) c.grid(x, 225, `
  gggggggggggggggg
  ggggkkgggggggggg
  gggkggkggggkkggg
  ggggggggggkggkgg`)
}

// ---------- stock characters ----------
// Cut from the ROM by tools/stockart32_convert.py as art/stockart32/characters.json describes, never
// redrawn: the intro's cheerleader (panel 4) and pair (panel 6), CHR $14 sprites composed by bank 5
// $AEE6, and the stands crowd, CHR $10 metatiles in their observed order with the stock red/blue shirt
// alternation. Each PNG holds exact NES colors and is generated beside a staged copy of this file.
sprite("_cheer", { png: "parts/cheer.png" })
sprite("_pair", { png: "parts/pair.png" })
// 16-pixel areas of the 80x32 crowd block, so every metatile keeps its own attribute cell
sprite("_crowd_l", { png: "parts/crowd-mix.png", area: [0, 0, 32, 32] })
sprite("_crowd_r", { png: "parts/crowd-mix.png", area: [48, 0, 32, 32] })
sprite("_crowd_arch_l", { png: "parts/crowd-mix.png", area: [0, 0, 48, 32] })
sprite("_crowd_arch_r", { png: "parts/crowd-mix.png", area: [32, 0, 48, 32] })

function stands(c, x0, area) {
  // bleachers beside the board: the crowd block's two metatile rows, then both again, cut at the ledge
  c.rect(x0, 64, 32, 59, "k")
  c.stamp(area, x0, 64); c.stamp(area, x0, 96)
  c.hline(x0, 64, 32, "c")
  c.rect(x0, 120, 32, 3, "c")
}
function gateWall(c, x0, y0, w, h) {
  // lit cream wall between the arches: dark hair drawn with the backdrop stays readable against it
  c.rect(x0, y0, w, h, "c")
  c.hline(x0, y0, w, "k")
}
function counter(c, x0, y0, w) {
  // the ticket counter in front of the pair hides the panel edge that cuts their legs
  c.rect(x0, y0, w, 24, "c")
  c.hline(x0, y0, w, "k"); c.hline(x0, y0 + 3, w, "k")
  c.vline(x0, y0, 24, "k"); c.vline(x0 + w - 1, y0, 24, "k")
  for (let x = x0 + 8; x < x0 + w - 4; x += 16) c.vline(x, y0 + 4, 20, "k")
}

scene("mode", { w: 256, h: 240, bg: "s" }, (c) => {
  const CLOUD = [[7, 6, 4], [14, 3, 5], [22, 5, 4], [27, 7, 3]]
  cloud(c, 0, 13, CLOUD); cloud(c, 224, 13, CLOUD)
  lightTower(c, 6, 32); lightTower(c, 230, 32)
  pennant(c, 44, 25, "y"); pennant(c, 52, 17, "c"); pennant(c, 204, 25, "y"); pennant(c, 212, 17, "c")
  board(c)
  marquee(c)
  stands(c, 0, "_crowd_l"); stands(c, 224, "_crowd_r")
  c.rect(0, 123, 256, 4, "c"); c.hline(0, 127, 256, "k")
  bricks(c, 0, 128, 256, 64)
  arch(c, 16, "_crowd_arch_l"); arch(c, 192, "_crowd_arch_r")
  bunting(c, 80); bunting(c, 112); bunting(c, 144)
  gateWall(c, 64, 160, 128, 40)
  c.rect(0, 192, 64, 8, "c"); c.hline(0, 192, 64, "k"); c.rect(192, 192, 64, 8, "c"); c.hline(192, 192, 64, "k")
  for (const x of [4, 20, 36, 52, 196, 212, 228, 244]) c.vline(x, 193, 7, "k")
  c.rect(0, 200, 256, 24, "c"); c.hline(0, 200, 256, "k")
  lawn(c)
  // every figure cell is P2 over cream, brick or navy; no figure shares a cell with a blue shirt
  c.stamp("_pair", 120, 156)
  counter(c, 112, 200, 80)
  c.stamp("_cheer", 68, 160)
})
