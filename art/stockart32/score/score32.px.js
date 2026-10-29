// Scoreboard between half-innings and after the final out: the sunny ballpark board with the stock
// characters. 256x240, exact NES colors, navy $0C backdrop, four palettes (layout.json):
//   P0 sky $21, cream $38, gold $28   sky, clouds, sign, light towers, the board, every runtime glyph
//   P1 sky $21, cream $38, green $1A  lawn
//   P2 red $16, cream $38, skin $36   brick, the red-shirted stock crowd, the batter
//   P3 blue $12, cream $38, brown $17 the blue pads and the glove kid
// The stock writer (bank 4 $B40E/$B482/$B5C6) draws every number over navy board cells after this
// background is drawn, so the scene leaves those cells navy. The glyphs it writes are the sprites
// "big", "narrow", "head" and "sep" below.
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

// Board rows. top/foot hold the gold frame; head the inning numbers and R H E; line[i] the two rows
// of side i's line score; rule the line under them; label the stat names; stats[i] side i's stats.
const ROW = { top: 7, head: 8, line: [9, 11], rule: 13, label: 14, stats: [15, 17], foot: 19 }
// The writer's columns: inning cells from x 64, R H E from x 192, 16 px each; stat separators.
const LINE_X = 64, INNINGS = 7, RHE_X = 192
const SEP_COLS = [12, 15, 18, 21, 24, 27]

// ---------- runtime glyphs ----------
// Cream with a gold shadow on navy. Values 0-9 are one big 16x16 glyph; 10 and up are a narrow tens
// tile then a narrow ones tile from the same set, so a digit sits in the same place in either half.
// Big digits sit at x 4 and narrow ones at x 2 of their tiles: both are centred on x 8.5 of a cell,
// under a two-digit inning number (x 2-12) or a one-digit one (x 8-12).
const BIG = {
  0: ["..cccccc..", ".cccccccc.", "ccc....ccc", "cc......cc", "cc......cc", "cc......cc", "cc......cc",
      "cc......cc", "cc......cc", "cc......cc", "cc......cc", "ccc....ccc", ".cccccccc.", "..cccccc.."],
  1: ["...ccc....", "..cccc....", ".ccccc....", "....cc....", "....cc....", "....cc....", "....cc....",
      "....cc....", "....cc....", "....cc....", "....cc....", "....cc....", ".cccccccc.", ".cccccccc."],
  2: ["..cccccc..", ".cccccccc.", "ccc....ccc", "cc......cc", "........cc", ".......ccc", ".....cccc.",
      "...cccc...", "..ccc.....", ".ccc......", "ccc.......", "cc........", "cccccccccc", "cccccccccc"],
  3: [".ccccccc..", "ccccccccc.", "cc.....ccc", "........cc", "........cc", ".......ccc", "...cccccc.",
      "...cccccc.", ".......ccc", "........cc", "........cc", "cc.....ccc", "ccccccccc.", ".ccccccc.."],
  4: ["......ccc.", ".....cccc.", "....ccccc.", "...ccc.cc.", "..ccc..cc.", ".ccc...cc.", "ccc....cc.",
      "cc.....cc.", "cccccccccc", "cccccccccc", ".......cc.", ".......cc.", ".......cc.", ".......cc."],
  5: ["cccccccccc", "cccccccccc", "cc........", "cc........", "cc........", "cccccccc..", "ccccccccc.",
      ".......ccc", "........cc", "........cc", "........cc", "cc.....ccc", "ccccccccc.", ".ccccccc.."],
  6: ["...ccccc..", ".ccccccc..", ".ccc......", "ccc.......", "cc........", "cc.ccccc..", "ccccccccc.",
      "ccc....ccc", "cc......cc", "cc......cc", "cc......cc", "ccc....ccc", ".cccccccc.", "..cccccc.."],
  7: ["cccccccccc", "cccccccccc", "cc.....ccc", ".......cc.", "......ccc.", "......cc..", ".....ccc..",
      ".....cc...", "....ccc...", "....cc....", "....cc....", "....cc....", "....cc....", "....cc...."],
  8: ["..cccccc..", ".cccccccc.", "ccc....ccc", "cc......cc", "ccc....ccc", ".cccccccc.", ".cccccccc.",
      "ccc....ccc", "cc......cc", "cc......cc", "cc......cc", "ccc....ccc", ".cccccccc.", "..cccccc.."],
  9: ["..cccccc..", ".cccccccc.", "ccc....ccc", "cc......cc", "cc......cc", "cc......cc", "ccc....ccc",
      ".ccccccccc", "..ccccc.cc", "........cc", ".......ccc", "......ccc.", "..cccccc..", "..ccccc..."],
  X: ["..........", "..........", "cc......cc", "ccc....ccc", ".ccc..ccc.", "..cccccc..", "...cccc...",
      "...cccc...", "..cccccc..", ".ccc..ccc.", "ccc....ccc", "cc......cc", "..........", ".........."],
}
const NARROW = {
  0: [".cccc.", "cccccc", "cc..cc", "cc..cc", "cc..cc", "cc..cc", "cc..cc", "cc..cc", "cc..cc", "cc..cc",
      "cc..cc", "cc..cc", "cccccc", ".cccc."],
  1: ["..cc..", ".ccc..", "cccc..", "..cc..", "..cc..", "..cc..", "..cc..", "..cc..", "..cc..", "..cc..",
      "..cc..", "..cc..", "cccccc", "cccccc"],
  2: [".cccc.", "cccccc", "cc..cc", "....cc", "....cc", "...ccc", "..ccc.", ".ccc..", "ccc...", "cc....",
      "cc....", "cc....", "cccccc", "cccccc"],
  3: ["ccccc.", "cccccc", "....cc", "....cc", "....cc", "...ccc", ".cccc.", ".cccc.", "...ccc", "....cc",
      "....cc", "....cc", "cccccc", "ccccc."],
  4: ["...cc.", "..ccc.", ".cccc.", "cc.cc.", "cc.cc.", "cc.cc.", "cc.cc.", "cccccc", "cccccc", "...cc.",
      "...cc.", "...cc.", "...cc.", "...cc."],
  5: ["cccccc", "cccccc", "cc....", "cc....", "cc....", "ccccc.", "cccccc", "....cc", "....cc", "....cc",
      "....cc", "cc..cc", "cccccc", ".cccc."],
  6: [".cccc.", "ccccc.", "cc....", "cc....", "cc....", "ccccc.", "cccccc", "cc..cc", "cc..cc", "cc..cc",
      "cc..cc", "cc..cc", "cccccc", ".cccc."],
  7: ["cccccc", "cccccc", "....cc", "....cc", "...cc.", "...cc.", "..cc..", "..cc..", "..cc..", ".cc...",
      ".cc...", ".cc...", ".cc...", ".cc..."],
  8: [".cccc.", "cccccc", "cc..cc", "cc..cc", "cc..cc", "cccccc", ".cccc.", "cccccc", "cc..cc", "cc..cc",
      "cc..cc", "cc..cc", "cccccc", ".cccc."],
  9: [".cccc.", "cccccc", "cc..cc", "cc..cc", "cc..cc", "cc..cc", "cccccc", ".ccccc", "....cc", "....cc",
      "....cc", "....cc", ".ccccc", ".cccc."],
  X: ["......", "......", "cc..cc", "cc..cc", ".cccc.", ".cccc.", "..cc..", "..cc..", ".cccc.", ".cccc.",
      "cc..cc", "cc..cc", "......", "......"],
}
const GLYPH_ORDER = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, "X"]

// The gold label face: inning numbers, R H E. One-digit innings sit flush left in their right tile;
// the 1 sits right of centre in its own tile, so a tens 1 hugs its ones digit ("15 16 17 18") and a
// lone 1 lands within 2 px of where 2-9 sit.
const FACE = {
  0: [".yyy.", "yy.yy", "yy.yy", "yy.yy", "yy.yy", "yy.yy", ".yyy."],
  1: [".yy.", "yyy.", ".yy.", ".yy.", ".yy.", ".yy.", "yyyy"],
  2: [".yyy.", "yy.yy", "...yy", "..yy.", ".yy..", "yy...", "yyyyy"],
  3: ["yyyy.", "...yy", "...yy", ".yyy.", "...yy", "...yy", "yyyy."],
  4: ["...yy", "..yyy", ".y.yy", "y..yy", "yyyyy", "...yy", "...yy"],
  5: ["yyyyy", "yy...", "yyyy.", "...yy", "...yy", "yy.yy", ".yyy."],
  6: [".yyy.", "yy...", "yyyy.", "yy.yy", "yy.yy", "yy.yy", ".yyy."],
  7: ["yyyyy", "...yy", "...yy", "..yy.", "..yy.", ".yy..", ".yy.."],
  8: [".yyy.", "yy.yy", "yy.yy", ".yyy.", "yy.yy", "yy.yy", ".yyy."],
  9: [".yyy.", "yy.yy", "yy.yy", ".yyyy", "...yy", "...yy", ".yyy."],
  R: ["yyyy.", "yy.yy", "yy.yy", "yyyy.", "yy.y.", "yy.yy", "yy.yy"],
  H: ["yy.yy", "yy.yy", "yy.yy", "yyyyy", "yy.yy", "yy.yy", "yy.yy"],
  E: ["yyyyy", "yy...", "yy...", "yyyy.", "yy...", "yy...", "yyyyy"],
}
const FACE_X = { 1: 2 }

// cream glyph rows, gold shadow one pixel right and down ("drop") or one pixel down ("below")
function inked(c, x0, y0, rows, shadow) {
  const [sx, sy] = shadow === "drop" ? [1, 1] : [0, 1]
  const on = (x, y) => y >= 0 && y < rows.length && x >= 0 && x < rows[y].length && rows[y][x] === "c"
  for (let y = 0; y <= rows.length; y++) for (let x = 0; x <= rows[0].length; x++) {
    if (on(x, y)) c.px(x0 + x, y0 + y, "c")
    else if (on(x - sx, y - sy)) c.px(x0 + x, y0 + y, "y")
  }
}
sprite("big", { w: 176, h: 16 }, (c) => {
  c.rect(0, 0, 176, 16, "k")
  GLYPH_ORDER.forEach((g, i) => inked(c, 16 * i + 4, 1, BIG[g], "drop"))
})
sprite("narrow", { w: 88, h: 16 }, (c) => {
  c.rect(0, 0, 88, 16, "k")
  GLYPH_ORDER.forEach((g, i) => inked(c, 8 * i + 2, 1, NARROW[g], "below"))
})
// inning digits 0-9, then the blank the writer puts before 1-9 and after 18
sprite("head", { w: 88, h: 8 }, (c) => {
  c.rect(0, 0, 88, 8, "k")
  for (let d = 0; d < 10; d++) c.grid(8 * d + (FACE_X[d] || 0), 0, FACE[d].join("\n"))
})
// the stat separator the writer puts between stat columns: a gold rule on navy
sprite("sep", { w: 8, h: 8 }, (c) => { c.rect(0, 0, 8, 8, "k"); c.vline(4, 0, 8, "y") })

// ---------- sky ----------
function cloud(c, x, y, puffs) {
  for (const [dx, dy, r] of puffs) c.circ(x + dx, y + dy, r, "c")
  const x0 = Math.min(...puffs.map(([dx, , r]) => dx - r)), x1 = Math.max(...puffs.map(([dx, , r]) => dx + r))
  const base = Math.max(...puffs.map(([, dy]) => dy))
  c.rect(x + x0 + 2, y + base, x1 - x0 - 3, 3, "c")
}
function lightTower(c, x, y, mast) {
  c.rect(x, y, 20, 14, "k")
  for (let j = 0; j < 2; j++) for (let i = 0; i < 4; i++) c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "c")
  c.rect(x + 8, y + 14, 4, mast, "k")
  c.hline(x - 1, y + 14, 22, "k")
}

// ---------- the mode menu's sign, unchanged: navy outline, gold band, bulbs, ball on crossed bats ----------
function marquee(c) {
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
  c.grid(124, 24, `
  ...y...
  ...y...
  yyyyyyy
  .yyyyy.
  ..yyy..
  .yy.yy.
  .y...y.`)
}

// ---------- the board ----------
function face(c, x, y, ch) {
  c.grid(x, y, FACE[ch].join("\n"))
}
function board(c) {
  const y0 = 8 * ROW.top, y1 = 8 * ROW.foot + 7
  c.rect(8, y0, 240, y1 - y0 + 1, "k")
  c.rect(9, y0 + 1, 238, 3, "y"); c.rect(9, y1 - 3, 238, 3, "y")
  c.rect(9, y0 + 1, 3, y1 - y0 - 1, "y"); c.rect(244, y0 + 1, 3, y1 - y0 - 1, "y")
  for (let x = 16; x < 244; x += 8) { c.px(x, y0 + 2, "c"); c.px(x, y1 - 2, "c") }
  for (let y = y0 + 8; y < y1 - 3; y += 8) { c.px(10, y, "c"); c.px(245, y, "c") }
  // R H E over the middle of their cells, in the inning numbers' face, with a rule between cells
  "RHE".split("").forEach((ch, k) => face(c, RHE_X + 16 * k + 6, 8 * ROW.head, ch))
  for (const k of [1, 2]) c.vline(RHE_X + 16 * k, 8 * ROW.head, 8, "y")
  // the rule under the line score breaks between cells, so each value stands on its own dash
  const ruleY = 8 * ROW.rule + 2
  const cells = [...Array(INNINGS).keys()].map((k) => LINE_X + 16 * k).concat([0, 1, 2].map((k) => RHE_X + 16 * k))
  c.hline(12, ruleY, 232, "y")
  for (const x of cells) { c.px(x, ruleY, "k"); c.px(x + 15, ruleY, "k") }
  // posts between names, innings and R H E, ending at the line score's last row
  const lineTop = 8 * ROW.head, lineBottom = 8 * ROW.line[1] + 15
  c.vline(60, lineTop, lineBottom - lineTop + 1, "y")
  c.vline(183, lineTop, lineBottom - lineTop + 1, "y")
  const statTop = 8 * ROW.label, statBottom = 8 * ROW.stats[1] + 15
  c.vline(68, statTop, statBottom - statTop + 1, "y")
  // the label row continues the separators the writer draws between stat columns
  for (const col of SEP_COLS) c.vline(8 * col + 4, statTop, 8, "y")
}
function posts(c) {
  // two gold posts from the sign down to the board; the right outline starts on the tile row below
  // the sign, so the sign's bottom tiles stay one pattern
  const h = 8 * ROW.top - 46
  for (const x of [84, 164]) { c.rect(x, 46, 4, h, "y"); c.vline(x - 1, 46, h, "k"); c.vline(x + 4, 48, h - 2, "k") }
}

function bricks(c, x0, y0, w, h) {
  c.rect(x0, y0, w, h, "r")
  for (let y = y0; y < y0 + h; y++) {
    if (y % 4 === 3) { c.hline(x0, y, w, "k"); continue }
    const off = y % 8 < 4 ? 7 : 3
    for (let x = x0; x < x0 + w; x++) if (x % 8 === off) c.px(x, y, "k")
  }
}
function lawn(c, y0) {
  c.rect(0, y0, 256, 240 - y0, "g")
  c.hline(0, y0, 256, "k")
  for (let x = 0; x < 256; x += 16) c.grid(x, y0 + 1, `
  gggggggggggggggg
  ggggkkgggggggggg
  gggkggkggggkkggg
  ggggggggggkggkgg`)
}
function pads(c, x0, y0, w, h) {
  // the visitors' padded wall: blue panels, navy seams every 16 px, a cream stripe
  c.rect(x0, y0, w, h, "b")
  for (let x = x0; x < x0 + w; x += 16) c.vline(x, y0, h, "k")
  c.hline(x0, y0 + 6, w, "c")
}

// ---------- stock characters ----------
// Cut from the ROM by tools/stockart32_convert.py as art/stockart32/characters.json describes, never
// redrawn: the intro's glove kid (panel 0) and batter (panel 1), CHR $14 sprites composed by bank 5
// $AEE6, and the stands crowd, CHR $10 metatiles in their observed order. Each PNG holds exact NES
// colors and is generated beside a staged copy of this file, never committed.
sprite("_glove", { png: "parts/glove.png" })
sprite("_batter", { png: "parts/batter.png" })
sprite("_crowd", { png: "parts/crowd-red.png" })

function stands(c, y0) {
  // two metatile rows of the stock crowd on the attribute grid, the observed 80x32 block repeated
  for (let x = 0; x < 256; x += 80) c.stamp("_crowd", x, y0)
  c.rect(0, y0 + 32, 256, 8, "k")
}
function opening(c, x0, y0, w, h, back) {
  // a dugout or the players' tunnel through the stands, framed, on the 16-pixel attribute grid so the
  // crowd's P2 cells and a figure's own cells never share a cell. A lit cream wall keeps the batter's
  // dark hair (drawn with the backdrop, as in the intro) readable; the tunnel stays navy
  c.rect(x0, y0, w, h, back === "k" ? "c" : "k")
  c.rect(x0 + 2, y0 + 2, w - 4, h - 2, back)
}

// ---------- the scene ----------
scene("score", { w: 256, h: 240, bg: "s" }, (c) => {
  const CLOUD = [[7, 6, 4], [14, 3, 5], [22, 5, 4], [27, 7, 3]]
  // both corner groups sit on the same 8 px phase, so the right one reuses the left one's tiles
  for (const x0 of [8, 208]) { cloud(c, x0, 13, CLOUD); lightTower(c, x0 + 22, 4, 8 * ROW.top - 18) }
  marquee(c)
  posts(c)
  board(c)
  stands(c, 160)
  opening(c, 16, 160, 64, 40, "c")
  opening(c, 192, 160, 48, 40, "k")
  c.rect(0, 200, 256, 3, "c"); c.hline(0, 203, 256, "k")
  bricks(c, 0, 204, 160, 20)
  pads(c, 160, 204, 96, 20)
  lawn(c, 224)
  // P2 cells: the batter over the cream dugout and the brick; P3 cells: the glove kid over the tunnel and pads
  c.stamp("_batter", 20, 160)
  c.stamp("_glove", 196, 160)
})
