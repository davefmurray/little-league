// Scoreboard between half-innings and after the final out: the sunny ballpark board.
// 256x240, exact NES colors, navy $0C backdrop. The four palettes are the mode menu's
// (art/modeart32/layout.json), so the two screens share every color:
//   P0 sky $21, cream $38, gold $28   sky, clouds, sign, light towers, the board, every runtime glyph
//   P1 sky $21, cream $38, green $1A  lawn
//   P2 red $16, cream $38, tan $27    brick, red caps and shirts, tan skin
//   P3 blue $12, cream $38, brown $17 blue caps and shirts, brown skin
// The stock writer (bank 4 $B40E/$B482/$B5C6) draws every number over navy board cells after this
// background is drawn. The scene leaves those
// cells navy. The glyphs it writes are the sprites "big", "narrow", "head" and "sep" below.
pal({
  k: "#183C5D",  // $0C navy backdrop
  s: "#3CBEFF",  // $21 sky
  c: "#FFE7A2",  // $38 cream
  y: "#F3BE3C",  // $28 gold
  g: "#00AA00",  // $1A green
  r: "#DB2800",  // $16 red
  t: "#FF9A38",  // $27 tan skin
  b: "#2038EF",  // $12 blue
  d: "#CB4D0C",  // $17 brown skin
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

// ---------- the crowd and the wall ----------
const FAN_A = ["..rrrr..", ".rrrrrr.", "..tktk..", "..tttt..", ".cccccc.", "cccccccc", "cccccccc"]
const FAN_B = ["..kkkk..", ".kttttk.", "..tktk..", "..tttt..", ".rrrrrr.", "rrrrrrrr", "rrrrrrrr"]
const BLUE = { r: "b", t: "d" }
function stands(c, y0, tiers) {
  // one tier per tile row, a fan every 8 px, every other tier offset by 4 px
  c.rect(0, y0, 256, 8 * tiers, "k")
  for (let k = 0; k < tiers; k++) {
    const y = y0 + 8 * k + 1
    for (let x = (k & 1 ? 4 : 0) - 8; x < 256; x += 8) {
      const fan = k & 1 ? FAN_B : FAN_A
      for (let j = 0; j < fan.length; j++) for (let i = 0; i < 8; i++) {
        const ch = fan[j][i], X = x + i
        if (ch !== "." && X >= 0 && X < 256) c.px(X, y + j, ch)
      }
    }
  }
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
function blueCells(c, cells) {
  // every 16x16 cell listed as blue takes P3: red to blue, tan to brown
  for (const [cx, cy] of cells) for (let y = 16 * cy; y < 16 * cy + 16; y++) for (let x = 16 * cx; x < 16 * cx + 16; x++) {
    const k = c.key(x, y)
    if (BLUE[k]) c.px(x, y, BLUE[k])
  }
}

// ---------- people (the mode menu's figures) ----------
function at(rows, dx, dy) {
  const out = {}
  for (const [y, runs] of Object.entries(rows)) out[+y + dy] = runs.map(([x, s]) => [x + dx, s])
  return out
}
const KIDHEAD = {
  0: [[5, "kkkk"]], 1: [[3, "kkrrrrkk"]], 2: [[2, "krrrrcrrrk"]], 3: [[1, "krrrrrcrrrrk"]],
  4: [[1, "krrrrrcccrrk"]], 5: [[1, "krrrrrrrrrrk"]], 6: [[0, "kkkkkkkkkkkkkk"]],
  7: [[1, "kttttttttttk"]], 8: [[1, "kttkttttkttk"]], 9: [[1, "kttkttttkttk"]], 10: [[1, "kttttttttttk"]],
  11: [[1, "ktttkkkktttk"]], 12: [[2, "ktttkktttk"]], 13: [[3, "kttttttk"]], 14: [[4, "kkkkkk"]],
}
function fig(layers, stretch = []) {
  const shift = (y) => stretch.reduce((s, [r, n]) => s + (y > r ? n : 0), 0)
  return (c) => {
    for (const layer of layers) {
      const out = {}
      for (const [k, runs] of Object.entries(layer)) {
        const y = +k, to = y + shift(y)
        out[to] = runs
        for (const [r, n] of stretch) if (y === r) for (let i = 1; i <= n; i++) out[to + i] = runs
      }
      c.runs(out)
    }
  }
}
const GLANCE = { ...KIDHEAD, 8: [[1, "ktkttttktttk"]], 9: [[1, "ktkttttktttk"]], 11: [[1, "kttkttttkttk"]],
                 12: [[2, "kttkkkkttk"]] }
const KIDLEGS = {
  23: [[4, "kccccccccccck"]], 24: [[4, "kcrcccccccrck"]], 25: [[4, "kcrcccccccrck"]], 26: [[4, "kcrccckcccrck"]],
  27: [[4, "kcrcck.kccrck"]], 28: [[4, "kcrck...kcrck"]], 29: [[4, "kccck...kccck"]], 30: [[4, "krrrk...krrrk"]],
  31: [[4, "krrrk...krrrk"]], 32: [[4, "krcrk...krcrk"]], 33: [[4, "krrrk...krrrk"]],
  34: [[3, "kkkkkk..kkkkkk"]], 35: [[2, "kkkkkkk..kkkkkkk"]],
}
sprite("kid_red", { w: 21, h: 36 }, fig([{
  1: [[1, "kk"]], 2: [[0, "ktk"]], 3: [[0, "kttk"]], 4: [[0, "kttk"]], 5: [[0, "kttk"]], 6: [[1, "ktk"]],
  7: [[1, "ktk"]], 8: [[1, "kttk"]], 9: [[2, "ktk"]], 10: [[2, "ktk"]], 11: [[2, "krrk"]], 12: [[2, "krrk"]],
  13: [[2, "krrk"]], 14: [[3, "krrk"]] }, at(KIDHEAD, 4, 0), KIDLEGS, {
  15: [[3, "kkrrrrkkkrrrrkk"]], 16: [[3, "krrrrrrcrrrrrrrk"]], 17: [[3, "krrrrrrcrrrrrrrrk"]],
  18: [[3, "krrrrrrcrrrrkrrrk"]], 19: [[3, "krrrrrrcrrrrkkkkk"]], 20: [[3, "krrrrrrcrrrkttttk"]],
  21: [[3, "krrrrrrcrrkttttttk"]], 22: [[3, "kkkkkkkkkkkttkkttk"]], 23: [[14, "ktttttk"]],
  24: [[15, "ktttk"]], 25: [[16, "kkk"]] }]))
sprite("kid_blue", { w: 23, h: 36, swap: BLUE }, fig([{
  0: [[19, "kk"]], 1: [[18, "kcck"]], 2: [[18, "kcck"]], 3: [[17, "kcck"]], 4: [[17, "kcck"]], 5: [[17, "kck"]],
  6: [[17, "kck"]], 7: [[17, "kck"]], 8: [[17, "kck"]], 9: [[17, "kck"]], 10: [[17, "kck"]], 11: [[17, "kck"]] },
  at(GLANCE, 4, 0), KIDLEGS, {
  12: [[16, "kttk"]], 13: [[16, "kttk"]], 14: [[15, "kkkkk"]],
  15: [[3, "kkrrrrkkkrrrrkrrk"]], 16: [[3, "krrrrrrcrrrrrrrk"]], 17: [[3, "krrrrrrcrrrrrrrk"]],
  18: [[3, "krkrrrrcrrrrrrrk"]], 19: [[3, "krkrrrrcrrrrrrrk"]], 20: [[3, "ktkrrrrcrrrrrrrk"]],
  21: [[3, "ktkrrrrcrrrrrrrk"]], 22: [[3, "ktkkkkkkkkkkkkkk"]] }]))
sprite("dad", { w: 16, h: 51 }, fig([{
  0: [[0, ".kk..........kk."]], 1: [[0, "kttk........kttk"]], 2: [[0, "kttk........kttk"]],
  3: [[0, "ktk...kkkk...ktk"]], 4: [[0, "ktk.kkrrrrkk.ktk"]], 5: [[0, "ktkkrrrcrrrrkktk"]],
  6: [[0, "krkkrrrccrrrkkrk"]], 7: [[0, "krkkkkkkkkkkkkrk"]], 8: [[0, "krkkttttttttkkrk"]],
  9: [[0, "krkktkttttktkkrk"]], 10: [[0, "krkkttttttttkkrk"]], 11: [[0, "krrkttkkkkttkrrk"]],
  12: [[0, ".krrkttkkttkrrk."]], 13: [[0, ".krrrkkkkkkrrrk."]], 14: [[0, ".krrrrrrrrrrrrk."]],
  15: [[0, "kcccckkkkkkcccck"]], 16: [[0, "kccckkkkkkkkccck"]], 17: [[0, "kttkkkkkkkkkkttk"]],
  18: [[0, "kttkkttttttkkttk"]], 19: [[0, "ktkkttttttttkktk"]], 20: [[0, "ktktkkttttkktktk"]],
  21: [[0, "ktkttttttttttktk"]], 22: [[0, "kkkkttttttttkkkk"]], 23: [[0, "kkkkttkkkkttkkkk"]],
  24: [[0, "....kttttttk...."]], 25: [[0, ".kkkkkkkkkkkkkk."]], 26: [[0, ".kccccrrrrcccck."]],
  27: [[0, "kccccccrrcccccck"]], 28: [[0, "kccccccrrcccccck"]], 29: [[0, "kcckcccccccckcck"]],
  30: [[0, "kttkcccccccckttk"]], 31: [[0, "kttkcccccccckttk"]], 32: [[0, "kttkcccccccckttk"]],
  33: [[0, "kttkcccccccckttk"]], 34: [[0, "kttkkkkkkkkkkttk"]], 35: [[0, ".kk.kkkkkkkk.kk."]],
  36: [[0, "...kkkkkkkkkk..."]], 37: [[0, "...kkkkkkkkkk..."]], 38: [[0, "...kkkkkkkkkk..."]],
  39: [[0, "...kkkkkkkkkk..."]], 40: [[0, "....kttk..kttk.."]], 41: [[0, "....kttk..kttk.."]],
  42: [[0, "....kttk..kttk.."]], 43: [[0, "....kttk..kttk.."]], 44: [[0, "....kcck..kcck.."]],
  45: [[0, "...kkkkk.kkkkk.."]], 46: [[0, "..kkkkkk.kkkkkk."]],
}], [[31, 2], [42, 2]]))
sprite("mom", { w: 16, h: 37 }, fig([{
  0: [[0, ".....kkkkkk....."]], 1: [[0, "....kcccccck...."]], 2: [[0, "...kcccccccck..."]],
  3: [[0, "...krrrrrrrrk..."]], 4: [[0, ".kkkcccccccckkk."]], 5: [[0, "kcccccccccccccck"]],
  6: [[0, ".kkkkkkkkkkkkkk."]], 7: [[0, "..kkttttttttkk.."]], 8: [[0, "..kktkttttktkk.."]],
  9: [[0, "..kktkttttktkk.."]], 10: [[0, "..kkttttttttkk.."]], 11: [[0, "..kktkttttktkk.."]],
  12: [[0, "..kkktkkkktkkk.."]], 13: [[0, "..kkkkttttkkkk.."]], 14: [[0, "..kkk.kkkk.kkk.."]],
  15: [[0, "...k..kttk..k..."]], 16: [[0, "...kcccccccck..."]], 17: [[0, "..kcccccccccck.."]],
  18: [[0, ".kckcccccccckck."]], 19: [[0, ".ktkcccccccckck."]], 20: [[0, ".ktkcccccccckttk"]],
  21: [[0, ".ktkrrrrrrrrktk."]], 22: [[0, ".ktkcccccccckrrk"]], 23: [[0, ".kkkcccccccckrrk"]],
  24: [[0, "..kcccccccccckkk"]], 25: [[0, "..kcccccccccck.."]], 26: [[0, ".kccccccccccccck"]],
  27: [[0, "kcccccccccccccck"]], 28: [[0, "kkkkkkkkkkkkkkkk"]], 29: [[0, ".....ktk..ktk..."]],
  30: [[0, ".....ktk..ktk..."]], 31: [[0, ".....ktk..ktk..."]], 32: [[0, ".....ktk..ktk..."]],
  33: [[0, ".....kkk..kkk..."]], 34: [[0, "....kkkk..kkkk.."]],
}], [[25, 1], [31, 1]]))
sprite("fan10", { w: 15, h: 40, swap: BLUE }, fig([{
  0: [[5, "kkkkkk"]], 1: [[4, "krrrrrrk"]], 2: [[3, "krrrrrrrrk"]], 3: [[3, "krrrrrrrrk"]],
  4: [[3, "kkkkkkkkkk"]], 5: [[3, "kkkkkkkkkk"]], 6: [[2, "ktkkkkkkkktk"]], 7: [[2, "ktkkkkkkkktk"]],
  8: [[3, "kkkkkkkkkk"]], 9: [[4, "kkttttkk"]],
  10: [[2, "kkrrrrrrrrkk"]], 11: [[1, "krrrrrrrrrrrrk"]], 12: [[0, "krrrcrrcccrrrrk"]],
  13: [[0, "krrccrrcrcrrrrk"]], 14: [[0, "krrrcrrcrcrrrrk"]], 15: [[0, "ktrrcrrcrcrrrtk"]],
  16: [[0, "ktrrcrrcccrrrtk"]], 17: [[0, "kkrrrrrrrrrrrkk"]], 18: [[0, "ktkrrrrrrrrrktk"]],
  19: [[0, "ktkrrrrrrrrrktk"]], 20: [[1, "kkkkkkkkkkkkk"]], 21: [[2, "kccccccccck"]],
  22: [[2, "kccccccccck"]], 23: [[2, "kccccccccck"]], 24: [[2, "kcccckcccck"]], 25: [[2, "kcccckcccck"]],
  26: [[2, "kcccckcccck"]], 27: [[2, "kcccckcccck"]], 28: [[2, "kccck.kccck"]], 29: [[2, "krrrk.krrrk"]],
  30: [[2, "krrrk.krrrk"]], 31: [[2, "krrrk.krrrk"]], 32: [[2, "kkkkk.kkkkk"]], 33: [[1, "kkkkkk.kkkkkk"]],
}], [[19, 2], [26, 4]]))
// popcorn cart with the vendor: striped canopy, glass case of popcorn, red body, wheel (40x63)
const POPCORN = ["cctcccck", "ccccctcc", "tcckcccc", "cccccccc", "ckcccctc", "ccctcccc", "cccccckc", "ctcccccc"]
sprite("cart", { w: 40, h: 63 }, (c) => {
  c.rect(0, 0, 40, 40, "k")
  for (let y = 1; y < 7; y++) for (let x = 0; x < 40; x++) c.px(x, y, (x >> 2) & 1 ? "c" : "r")
  for (let x = 0; x < 40; x += 4) c.grid(x, 7, (x >> 2) & 1 ? "cccc\n.cc." : "rrrr\n.rr.")
  c.runs(at({ ...KIDHEAD, 1: [[3, "kkcccckk"]], 2: [[2, "kcccccccck"]], 3: [[1, "kcccccccccck"]],
              4: [[1, "kcccccccccck"]], 5: [[1, "krrrrrrrrrrk"]], 11: [[1, "kttkkkkkkttk"]], 12: [[2, "ktkkttkktk"]] }, 16, 9))
  c.runs({ 24: [[15, "kcrcrcrcrcrck"]], 25: [[13, "kttkrcrcrcrckttk"]], 26: [[12, "kttkkkkkkkkkkttk"]] })
  for (let y = 27; y < 40; y++) for (let x = 0; x < 40; x++) c.px(x, y, POPCORN[(y - 27) & 7][x & 7])
  c.hline(0, 27, 40, "k")
  c.rect(0, 40, 40, 16, "r"); c.hline(0, 40, 40, "k"); c.hline(0, 55, 40, "k")
  c.rect(0, 44, 40, 3, "c"); c.hline(0, 47, 40, "k")
  c.circ(9, 55, 7, "k"); c.circ(9, 55, 5, "c"); c.circ(9, 55, 3, "k"); c.px(9, 55, "c")
  for (const [dx, dy] of [[0, -4], [0, 4], [-4, 0], [4, 0]]) c.px(9 + dx, 55 + dy, "k")
  c.rect(33, 55, 3, 8, "k")
})

// ---------- the scene ----------
scene("score", { w: 256, h: 240, bg: "s" }, (c) => {
  const CLOUD = [[7, 6, 4], [14, 3, 5], [22, 5, 4], [27, 7, 3]]
  // both corner groups sit on the same 8 px phase, so the right one reuses the left one's tiles
  for (const x0 of [8, 208]) { cloud(c, x0, 13, CLOUD); lightTower(c, x0 + 22, 4, 8 * ROW.top - 18) }
  marquee(c)
  posts(c)
  board(c)
  stands(c, 160, 5)
  c.rect(0, 200, 256, 3, "c"); c.hline(0, 203, 256, "k")
  bricks(c, 0, 204, 160, 20)
  lawn(c, 224)
  c.stamp("dad", 16, 172)
  c.stamp("mom", 34, 186)
  c.stamp("kid_red", 66, 188)
  c.stamp("cart", 104, 160)
  // blue cells: alternate fans in the top tier row, the visitors' side below
  const blue = [[2, 10], [4, 10], [9, 10], [11, 10], [13, 10], [15, 10], [0, 11], [15, 11]]
  for (let cx = 10; cx < 16; cx++) for (let cy = 11; cy < 14; cy++) if (!(cx === 15 && cy === 11)) blue.push([cx, cy])
  blueCells(c, blue)
  pads(c, 160, 204, 96, 20)
  c.stamp("kid_blue", 160, 188)
  // the blue kid's soles stop one pixel short on the pad, so both feet are one tile pattern
  c.px(162, 223, "b"); c.px(177, 223, "b")
  c.stamp("fan10", 194, 184)
  for (const [x0, x1, y] of [[67, 84, 224], [161, 178, 224]])
    for (let x = x0; x <= x1; x++) if ((x & 1) === 0) c.px(x, y, "k")
})
