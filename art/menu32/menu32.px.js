// Menu art for the 32-team selector and bracket. Every color is an exact NES color from the
// FCEUX table the project emulator uses; tools/menu32_convert.py rejects anything else.
// Geometry is mirrored in art/menu32/layout.json, which the converter checks against these PNGs.
pal({
  k: "#183C5D",  // $0C slate navy: backdrop, and the blue/black of every flag
  W: "#FFFFFF",  // $30 white
  y: "#F3BE3C",  // $28 gold
  r: "#DB2800",  // $16 baseball red
  g: "#00AA00",  // $1A green
  c: "#FFE7A2",  // $38 cream nameplate
  l: "#BEBEBE",  // $10 gray connector
})

// ---- Condensed 4x5 code letters. Narrow forms keep every code inside a 14 px plate window.
const GLYPH = {
  A: [".##.", "#..#", "####", "#..#", "#..#"], A3: [".#.", "#.#", "###", "#.#", "#.#"],
  B: ["###.", "#..#", "###.", "#..#", "###."], C: [".###", "#...", "#...", "#...", ".###"],
  D: ["###.", "#..#", "#..#", "#..#", "###."], D3: ["##.", "#.#", "#.#", "#.#", "##."],
  E: ["####", "#...", "###.", "#...", "####"], E3: ["###", "#..", "##.", "#..", "###"],
  F: ["####", "#...", "###.", "#...", "#..."], G: [".###", "#...", "#.##", "#..#", ".###"],
  H: ["#..#", "#..#", "####", "#..#", "#..#"], I: ["###", ".#.", ".#.", ".#.", "###"],
  J: ["..##", "...#", "...#", "#..#", ".##."], K: ["#..#", "#.#.", "##..", "#.#.", "#..#"],
  L: ["#...", "#...", "#...", "#...", "####"], M: ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
  N: ["#..#", "##.#", "#.##", "#..#", "#..#"], O: [".##.", "#..#", "#..#", "#..#", ".##."],
  P: ["###.", "#..#", "###.", "#...", "#..."], R: ["###.", "#..#", "###.", "#.#.", "#..#"],
  S: [".###", "#...", ".##.", "...#", "###."], T: ["###", ".#.", ".#.", ".#.", ".#."],
  U: ["#..#", "#..#", "#..#", "#..#", ".##."], U3: ["#.#", "#.#", "#.#", "#.#", "###"],
  V: ["#...#", "#...#", ".#.#.", ".#.#.", "..#.."], W: ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
  X: ["#..#", "#..#", ".##.", "#..#", "#..#"], Y: ["#.#", "#.#", ".#.", ".#.", ".#."],
  Z: ["####", "...#", ".##.", "#...", "####"],
}
// Team order is the ROM's team id order (data/teams32.json).
const CODES = ["JPN", "ARI", "PEN", "TPE", "KOR", "NY", "CAL", "TEX", "HAW", "ESP", "PUR", "MEX",
  "CAN", "ITA", "ILL", "FLA", "AUS", "CUB", "DOM", "VEN", "PAN", "NED", "GER", "RSA", "BRA",
  "COL", "NIC", "PHI", "HKG", "GUM", "NZL", "CZE"]
const SPELL = { HAW: ["H", "A3", "W"], MEX: ["M", "E3", "X"], DOM: ["D3", "O", "M"],
  GUM: ["G", "U3", "M"], VEN: ["V", "E3", "N"] }
const letters = (code) => SPELL[code] || [...code]
const codeWidth = (code) => letters(code).reduce((w, ch, i) => w + GLYPH[ch][0].length + (i ? 1 : 0), 0)

// A nameplate: a 16x7 rounded plate (index 1) with the code cut out of it, then one empty row.
function nameplate(c, key) {
  c.rect(1, 0, 14, 7, key)
  c.vline(0, 1, 5, key)
  c.vline(15, 1, 5, key)
}
function cutCode(c, code) {
  let x = Math.floor((16 - codeWidth(code)) / 2)
  for (const ch of letters(code)) {
    const g = GLYPH[ch]
    for (let yy = 0; yy < g.length; yy++)
      for (let xx = 0; xx < g[yy].length; xx++)
        if (g[yy][xx] === "#") c.px(x + xx, 1 + yy, "_")
    x += g[0].length + 1
  }
}
CODES.forEach((code, i) => {
  sprite(`chip_${i}`, { w: 16, h: 8 }, (c) => { nameplate(c, "c"); cutCode(c, code) })
})
// An undecided slot: a dotted outline of the same plate.
sprite("chip_empty", { w: 16, h: 8 }, (c) => {
  for (let x = 2; x < 14; x += 2) { c.px(x, 0, "l"); c.px(x + 1, 6, "l") }
  c.px(0, 2, "l"); c.px(0, 4, "l"); c.px(15, 2, "l"); c.px(15, 4, "l")
  c.px(1, 0, "l"); c.px(14, 6, "l")
})

// ---- 16x8 flags. Slate (k) stands in for every blue and black; each flag fits one palette:
// [gold white red], [green white red] (MEX ITA RSA) or [green white gold] (BRA).
function tri(c, key, apex) {            // hoist triangle, full height at x=0, point at x=apex
  for (let y = 0; y < 8; y++) {
    const d = Math.abs(y - 3.5) - 0.5
    const w = Math.round(apex * (1 - d / 3.5))
    if (w > 0) c.hline(0, y, w, key)
  }
}
function jack(c) {                        // a 7x3 Union Jack canton
  c.rect(0, 0, 7, 3, "k")
  c.px(0, 0, "W"); c.px(2, 0, "W"); c.px(4, 0, "W"); c.px(6, 0, "W")
  c.px(0, 2, "W"); c.px(2, 2, "W"); c.px(4, 2, "W"); c.px(6, 2, "W")
  c.hline(0, 1, 7, "r"); c.vline(3, 0, 3, "r")
}
const FLAG = []
FLAG[0] = (c) => {                        // Japan
  c.rect(0, 0, 16, 8, "W")
  c.hline(7, 2, 2, "r"); c.hline(6, 3, 4, "r"); c.hline(6, 4, 4, "r"); c.hline(7, 5, 2, "r")
}
FLAG[1] = (c) => {                        // Arizona: rays over blue, copper star
  c.rect(0, 0, 16, 8, "k")
  for (let y = 0; y < 4; y++) for (let x = 0; x < 16; x++) {
    const a = Math.atan2(4 - y, x - 7.5)
    c.px(x, y, Math.floor(a / (Math.PI / 13)) % 2 ? "r" : "y")
  }
  c.hline(7, 2, 2, "W"); c.hline(6, 3, 4, "W"); c.hline(7, 4, 2, "W"); c.px(6, 5, "W"); c.px(9, 5, "W")
}
FLAG[2] = (c) => {                        // Pennsylvania: arms between two horses
  c.rect(0, 0, 16, 8, "k")
  c.hline(6, 1, 4, "y"); c.rect(5, 2, 6, 3, "y"); c.hline(6, 3, 4, "r"); c.hline(6, 5, 4, "y")
  c.vline(3, 2, 3, "W"); c.vline(12, 2, 3, "W"); c.px(4, 2, "W"); c.px(11, 2, "W")
  c.hline(3, 6, 10, "y")
}
FLAG[3] = (c) => {                        // Chinese Taipei: plum blossom
  c.rect(0, 0, 16, 8, "W")
  c.hline(7, 1, 2, "k"); c.hline(5, 2, 6, "k"); c.hline(5, 3, 6, "k"); c.hline(5, 4, 6, "k")
  c.hline(6, 5, 1, "k"); c.hline(9, 5, 1, "k")
  c.hline(7, 2, 2, "r"); c.hline(6, 3, 4, "r"); c.hline(7, 4, 2, "W")
  for (const x of [4, 6, 8, 10]) c.px(x + 1, 7, "k")
}
FLAG[4] = (c) => {                        // Korea: taegeuk and four trigrams
  c.rect(0, 0, 16, 8, "W")
  c.hline(7, 2, 2, "r"); c.hline(6, 3, 4, "r"); c.hline(6, 4, 4, "k"); c.hline(7, 5, 2, "k")
  c.px(9, 3, "k"); c.px(6, 4, "r")
  for (const [x, y] of [[1, 1], [3, 1], [2, 2], [12, 1], [14, 1], [13, 2], [2, 5], [1, 6], [3, 6], [13, 5], [12, 6], [14, 6]])
    c.px(x, y, "k")
}
FLAG[5] = (c) => {                        // New York: arms with two supporters
  c.rect(0, 0, 16, 8, "k")
  c.hline(7, 1, 2, "y"); c.rect(6, 2, 4, 3, "y"); c.hline(7, 3, 2, "W"); c.hline(7, 5, 2, "y")
  c.vline(4, 2, 4, "W"); c.vline(11, 2, 4, "W"); c.px(3, 3, "W"); c.px(12, 3, "W")
  c.hline(4, 6, 8, "y")
}
FLAG[6] = (c) => {                        // California: star, golden bear, red bar
  c.rect(0, 0, 16, 8, "W")
  c.px(1, 0, "r"); c.hline(0, 1, 3, "r"); c.px(1, 2, "r")
  c.hline(6, 2, 6, "y"); c.hline(4, 3, 9, "y"); c.hline(3, 4, 9, "y"); c.px(3, 3, "y")
  c.px(5, 5, "y"); c.px(7, 5, "y"); c.px(9, 5, "y"); c.px(11, 5, "y")
  c.rect(0, 6, 16, 2, "r")
}
FLAG[7] = (c) => {                        // Texas
  c.rect(0, 0, 16, 4, "W"); c.rect(0, 4, 16, 4, "r"); c.rect(0, 0, 5, 8, "k")
  c.px(2, 2, "W"); c.hline(0, 3, 5, "W"); c.hline(1, 4, 3, "W"); c.px(1, 5, "W"); c.px(3, 5, "W")
}
FLAG[8] = (c) => {                        // Hawaii: eight stripes and the Union Jack
  const S = ["W", "r", "k", "W", "r", "k", "W", "r"]
  for (let y = 0; y < 8; y++) c.hline(0, y, 16, S[y])
  jack(c)
}
FLAG[9] = (c) => {                        // Spain
  c.rect(0, 0, 16, 8, "y"); c.rect(0, 0, 16, 2, "r"); c.rect(0, 6, 16, 2, "r")
  c.rect(3, 3, 2, 2, "r"); c.px(3, 2, "r")
}
FLAG[10] = (c) => {                       // Puerto Rico
  const S = ["r", "r", "W", "r", "r", "W", "r", "r"]
  for (let y = 0; y < 8; y++) c.hline(0, y, 16, S[y])
  tri(c, "k", 7)
  c.px(2, 3, "W"); c.hline(1, 4, 3, "W")
}
FLAG[11] = (c) => {                       // Mexico: eagle on a cactus
  c.rect(0, 0, 5, 8, "g"); c.rect(5, 0, 6, 8, "W"); c.rect(11, 0, 5, 8, "r")
  c.hline(7, 2, 2, "r"); c.hline(6, 3, 4, "r"); c.hline(7, 4, 2, "g"); c.hline(6, 5, 4, "g")
}
FLAG[12] = (c) => {                       // Canada
  c.rect(0, 0, 4, 8, "r"); c.rect(4, 0, 8, 8, "W"); c.rect(12, 0, 4, 8, "r")
  c.hline(7, 1, 2, "r"); c.px(5, 2, "r"); c.hline(7, 2, 2, "r"); c.px(10, 2, "r")
  c.hline(5, 3, 6, "r"); c.hline(6, 4, 4, "r"); c.hline(7, 5, 2, "r"); c.px(7, 6, "r")
}
FLAG[13] = (c) => {                       // Italy
  c.rect(0, 0, 5, 8, "g"); c.rect(5, 0, 6, 8, "W"); c.rect(11, 0, 5, 8, "r")
}
FLAG[14] = (c) => {                       // Illinois: eagle seal over the name
  c.rect(0, 0, 16, 8, "W")
  c.hline(6, 1, 4, "k"); c.vline(5, 2, 3, "k"); c.vline(10, 2, 3, "k"); c.hline(6, 5, 4, "k")
  c.rect(6, 2, 4, 3, "y"); c.px(8, 3, "k")
  c.hline(3, 7, 10, "k")
}
FLAG[15] = (c) => {                       // Florida: saltire and seal
  c.rect(0, 0, 16, 8, "W")
  for (let y = 0; y < 8; y++) {
    const x = y < 4 ? 2 * y : 2 * (7 - y)
    c.hline(x, y, 2, "r"); c.hline(14 - x, y, 2, "r")
  }
  c.hline(7, 2, 2, "y"); c.hline(6, 3, 4, "y"); c.hline(6, 4, 4, "y"); c.hline(7, 5, 2, "y")
  c.px(7, 3, "k"); c.px(8, 4, "k")
}
FLAG[16] = (c) => {                       // Australia
  c.rect(0, 0, 16, 8, "k"); jack(c)
  c.px(3, 5, "W"); c.hline(2, 6, 3, "W"); c.px(3, 7, "W")
  for (const [x, y] of [[12, 1], [10, 3], [14, 3], [12, 6], [13, 4]]) c.px(x, y, "W")
}
FLAG[17] = (c) => {                       // Cuba
  const S = ["k", "k", "W", "k", "k", "W", "k", "k"]
  for (let y = 0; y < 8; y++) c.hline(0, y, 16, S[y])
  tri(c, "r", 7)
  c.px(2, 3, "W"); c.hline(1, 4, 3, "W")
}
FLAG[18] = (c) => {                       // Dominican Republic
  c.rect(0, 0, 16, 8, "W")
  c.rect(0, 0, 7, 3, "k"); c.rect(9, 0, 7, 3, "r"); c.rect(0, 5, 7, 3, "r"); c.rect(9, 5, 7, 3, "k")
  c.rect(7, 3, 2, 2, "y")
}
FLAG[19] = (c) => {                       // Venezuela: arc of stars
  c.rect(0, 0, 16, 3, "y"); c.rect(0, 3, 16, 3, "k"); c.rect(0, 6, 16, 2, "r")
  for (const [x, y] of [[3, 5], [4, 4], [6, 3], [9, 3], [11, 4], [12, 5]]) c.px(x, y, "W")
}
FLAG[20] = (c) => {                       // Panama
  c.rect(0, 0, 8, 4, "W"); c.rect(8, 0, 8, 4, "r"); c.rect(0, 4, 8, 4, "k"); c.rect(8, 4, 8, 4, "W")
  c.px(4, 1, "k"); c.hline(3, 2, 3, "k")
  c.px(11, 5, "r"); c.hline(10, 6, 3, "r")
}
FLAG[21] = (c) => {                       // Netherlands
  c.rect(0, 0, 16, 3, "r"); c.rect(0, 3, 16, 2, "W"); c.rect(0, 5, 16, 3, "k")
}
FLAG[22] = (c) => {                       // Germany
  c.rect(0, 0, 16, 3, "k"); c.rect(0, 3, 16, 2, "r"); c.rect(0, 5, 16, 3, "y")
}
FLAG[23] = (c) => {                       // South Africa
  c.rect(0, 0, 16, 3, "r"); c.rect(0, 5, 16, 3, "k")
  c.rect(0, 2, 16, 4, "W")
  c.rect(0, 3, 16, 2, "g")
  for (let y = 0; y < 8; y++) {
    const d = y < 4 ? 3 - y : y - 4
    c.hline(0, y, d + 3, "W"); c.hline(0, y, d + 2, "g"); c.hline(0, y, d, "k")
  }
  c.hline(0, 3, 3, "k"); c.hline(0, 4, 3, "k")
}
FLAG[24] = (c) => {                       // Brazil
  c.rect(0, 0, 16, 8, "g")
  c.hline(7, 1, 2, "y"); c.hline(5, 2, 6, "y"); c.hline(3, 3, 10, "y"); c.hline(3, 4, 10, "y")
  c.hline(5, 5, 6, "y"); c.hline(7, 6, 2, "y")
  c.hline(7, 2, 2, "k"); c.hline(6, 3, 4, "k"); c.hline(6, 4, 4, "W"); c.hline(7, 5, 2, "k")
}
FLAG[25] = (c) => {                       // Colombia
  c.rect(0, 0, 16, 4, "y"); c.rect(0, 4, 16, 2, "k"); c.rect(0, 6, 16, 2, "r")
}
FLAG[26] = (c) => {                       // Nicaragua
  c.rect(0, 0, 16, 3, "k"); c.rect(0, 3, 16, 2, "W"); c.rect(0, 5, 16, 3, "k")
  c.hline(7, 3, 2, "y"); c.hline(6, 4, 4, "y")
}
FLAG[27] = (c) => {                       // Philippines
  c.rect(0, 0, 16, 4, "k"); c.rect(0, 4, 16, 4, "r")
  tri(c, "W", 7)
  c.rect(1, 3, 2, 2, "y"); c.px(0, 0, "y"); c.px(0, 7, "y"); c.px(5, 3, "y")
}
FLAG[28] = (c) => {                       // Hong Kong: bauhinia
  c.rect(0, 0, 16, 8, "r")
  c.hline(7, 1, 2, "W"); c.hline(5, 2, 2, "W"); c.px(8, 2, "W"); c.hline(10, 2, 2, "W")
  c.hline(5, 3, 2, "W"); c.hline(9, 3, 2, "W"); c.px(8, 4, "W")
  c.hline(5, 5, 2, "W"); c.px(7, 5, "W"); c.hline(9, 5, 2, "W"); c.hline(7, 6, 2, "W")
}
FLAG[29] = (c) => {                       // Guam: red border and seal
  c.rect(0, 0, 16, 8, "r"); c.rect(1, 1, 14, 6, "k")
  c.hline(6, 2, 4, "y"); c.vline(5, 3, 2, "y"); c.vline(10, 3, 2, "y"); c.hline(6, 5, 4, "y")
  c.rect(6, 3, 4, 2, "W"); c.px(7, 3, "k"); c.px(7, 4, "k")
}
FLAG[30] = (c) => {                       // New Zealand
  c.rect(0, 0, 16, 8, "k"); jack(c)
  for (const [x, y] of [[12, 1], [10, 3], [14, 3], [12, 6]]) {
    c.px(x, y, "r"); c.px(x - 1, y, "W"); c.px(x + 1, y, "W")
  }
}
FLAG[31] = (c) => {                       // Czech Republic
  c.rect(0, 0, 16, 4, "W"); c.rect(0, 4, 16, 4, "r"); tri(c, "k", 7)
}
FLAG.forEach((draw, i) => sprite(`flag_${i}`, { w: 16, h: 8 }, draw))

// ---- Sprites and small art.
sprite("cursor_corner", `
  yyyyyy..
  yWWWWy..
  yWyyyy..
  yWy.....
  yWy.....
  yyy.....
  ........
  ........`)
sprite("icon_pad", `
  ..WWW...
  ..WkW...
  WWWWWWW.
  WkWkWkW.
  WWWWWWW.
  ..WkW...
  ..WWW...
  ........`)
sprite("icon_a", `
  ..rrrr..
  .rrWWrr.
  rrWrrWrr
  rrWWWWrr
  rrWrrWrr
  .rrrrrr.
  ..rrrr..
  ........`)
sprite("ball", `
  ......WWWW......
  ....WWWWWWWW....
  ...WrrWWWWrrW...
  ..WWWrWWWWrWWW..
  .WWWrrWWWWrrWWW.
  .WWWrWWWWWWrWWW.
  WWWrrWWWWWWrrWWW
  WWWrWWWWWWWWrWWW
  WWWrWWWWWWWWrWWW
  WWWrrWWWWWWrrWWW
  .WWWrWWWWWWrWWW.
  .WWWrrWWWWrrWWW.
  ..WWWrWWWWrWWW..
  ...WrrWWWWrrW...
  ....WWWWWWWW....
  ......WWWW......`)
// Trophy: gold cup (y) with white shine (W) and a red ribbon (r); [red gold white] palette.
sprite("trophy", `
  ....yyyyyyyyyyyyyyyy....
  ..yyyWWyyyyyyyyyyyyyyy..
  .y..yWyyyyyyyyyyyyyy..y.
  y...yWyyyyyyyyyyyyyy...y
  y...yWyyyyyyyyyyyyyy...y
  y...yWyyyyyyyyyyyyyy...y
  .y..yWyyyyyyyyyyyyyy..y.
  ..yyyyWyyyyyyyyyyyyyyy..
  .....yyyyyyyyyyyyyy.....
  ......yyyyyyyyyyyy......
  .......yyyyyyyyyy.......
  .........yyyyyy.........
  ..........yyyy..........
  ..........yyyy..........
  ..........yWyy..........
  .........yyyyyy.........
  .......rrrrrrrrrr.......
  ......rrrrrrrrrrrr......
  ......ryyyyyyyyyyr......
  ......rrrrrrrrrrrr......
  .....yyyyyyyyyyyyyy.....
  .....yWWWWWWWWWWWWy.....
  .....yyyyyyyyyyyyyy.....
  ........................`)

// ---- Shared frame: a double white rule just inside the 224-line visible area.
const FRAME_TOP = 9, FRAME_BOTTOM = 230
function screenFrame(c) {
  for (const inset of [0, 2]) {
    const x0 = 2 + inset, x1 = 253 - inset, y0 = FRAME_TOP + inset, y1 = FRAME_BOTTOM - inset
    c.hline(x0 + 2, y0, x1 - x0 - 3, "W"); c.hline(x0 + 2, y1, x1 - x0 - 3, "W")
    c.vline(x0, y0 + 2, y1 - y0 - 3, "W"); c.vline(x1, y0 + 2, y1 - y0 - 3, "W")
    c.px(x0 + 1, y0 + 1, "W"); c.px(x1 - 1, y0 + 1, "W"); c.px(x0 + 1, y1 - 1, "W"); c.px(x1 - 1, y1 - 1, "W")
  }
}
// A double gold rule from tile col0 to col1 inclusive, closed by small diamonds.
function goldRule(c, row, col0, col1) {
  const y = row * 8 + 2, x0 = col0 * 8 + 3, x1 = (col1 + 1) * 8 - 4
  c.hline(x0 + 2, y, x1 - x0 - 3, "y"); c.hline(x0 + 2, y + 2, x1 - x0 - 3, "y")
  for (const [x, d] of [[x0, 1], [x1, -1]]) {
    c.px(x + d, y, "y"); c.px(x, y + 1, "y"); c.px(x + 2 * d, y + 1, "y"); c.px(x + d, y + 2, "y")
  }
}

// ---- Selector. Card t sits at tile col 4*(t&7)+1; its flag on row 7+4*(t>>3), plate below.
const SEL = { flagRow: 7, rowPitch: 4, col0: 1, colPitch: 4 }
function cardFrame(c, col, row) {         // white frame around a 16x15 card (flag + plate)
  const x0 = col * 8 - 1, x1 = col * 8 + 16, y0 = row * 8 - 1, y1 = row * 8 + 16
  c.hline(x0 + 1, y0, 16, "W"); c.hline(x0 + 1, y1, 16, "W")
  c.vline(x0, y0 + 1, 16, "W"); c.vline(x1, y0 + 1, 16, "W")
}
function flagFrame(c, col, row) {         // white frame around a bare 16x8 flag
  const x0 = col * 8 - 1, x1 = col * 8 + 16, y0 = row * 8 - 1, y1 = row * 8 + 8
  c.hline(x0 + 1, y0, 16, "W"); c.hline(x0 + 1, y1, 16, "W")
  c.vline(x0, y0 + 1, 8, "W"); c.vline(x1, y0 + 1, 8, "W")
}
scene("selector", { w: 256, h: 240, bg: "k" }, (c) => {
  screenFrame(c)
  c.stamp("ball", 40, 20); c.stamp("ball", 200, 20)
  goldRule(c, 5, 2, 29)
  for (let t = 0; t < 32; t++) {
    const col = SEL.col0 + SEL.colPitch * (t & 7), row = SEL.flagRow + SEL.rowPitch * (t >> 3)
    cardFrame(c, col, row)
    c.stamp(`flag_${t}`, col * 8, row * 8)
    c.stamp(`chip_${t}`, col * 8, row * 8 + 8, { swap: { c: "y" } })
  }
  goldRule(c, 22, 2, 29)
  flagFrame(c, 2, 24)                    // info flag, drawn at run time
  c.stamp("icon_pad", 7 * 8, 26 * 8); c.stamp("icon_a", 17 * 8, 26 * 8)  // MOVE at 9, SELECT at 19
})

// ---- Bracket. Heap slot s maps to a tile cell by tools/menu32_convert.py's slot_cell().
const ROW0 = 4
function seg(c, x, y, w, h) { c.rect(x, y, w, h, "l") }
scene("bracket", { w: 256, h: 240, bg: "k" }, (c) => {
  screenFrame(c)
  for (const side of [0, 1]) {
    // gap columns between rounds, as (round, column) pairs on the left; mirrored on the right
    const X = (col, rel) => side ? 255 - (col * 8 + rel) : col * 8 + rel
    const H = (col, rel0, rel1, y) => { const a = X(col, rel0), b = X(col, rel1); seg(c, Math.min(a, b), y, Math.abs(b - a) + 1, 1) }
    const V = (col, rel, y0, y1) => seg(c, X(col, rel), y0, 1, y1 - y0 + 1)
    const cy = (row) => row * 8 + 3
    // R1 -> R2 (gap col 3): groups of four slots
    for (let g = 0; g < 4; g++) {
      const r = ROW0 + 4 * g
      H(3, 0, 3, cy(r)); V(3, 3, cy(r), cy(r + 1)); H(3, 0, 7, cy(r + 1))
      H(3, 0, 7, cy(r + 2)); V(3, 3, cy(r + 2), cy(r + 3)); H(3, 0, 3, cy(r + 3))
    }
    // R2 -> QF (gap col 6)
    for (let g = 0; g < 2; g++) {
      const r = ROW0 + 1 + 8 * g
      H(6, 0, 3, cy(r)); H(6, 0, 3, cy(r + 1)); V(6, 3, cy(r), cy(r + 2)); H(6, 3, 7, cy(r + 2))
      H(6, 0, 3, cy(r + 4)); H(6, 0, 3, cy(r + 5)); V(6, 3, cy(r + 3), cy(r + 5)); H(6, 3, 7, cy(r + 3))
    }
    // QF -> SF (gap col 9)
    {
      const r = ROW0 + 3
      H(9, 0, 3, cy(r)); H(9, 0, 3, cy(r + 1)); V(9, 3, cy(r), cy(r + 4)); H(9, 3, 7, cy(r + 4))
      H(9, 0, 3, cy(r + 8)); H(9, 0, 3, cy(r + 9)); V(9, 3, cy(r + 5), cy(r + 9)); H(9, 3, 7, cy(r + 5))
    }
    // SF -> final (gap col 12): both semifinal slots join and run into the finalist plate
    {
      const r = ROW0 + 7
      H(12, 0, 7, cy(r)); V(12, 3, cy(r), cy(r + 1)); H(12, 0, 3, cy(r + 1))
    }
  }
  // finalists [60] VS [61] on row ROW0+7; both rise and meet under the champion plate
  const fy = (ROW0 + 7) * 8, top = (ROW0 + 6) * 8 + 3
  seg(c, 111, top, 1, fy - top); seg(c, 144, top, 1, fy - top)
  seg(c, 111, top, 144 - 111 + 1, 1)
  seg(c, 15 * 8 + 7, (ROW0 + 6) * 8, 2, top - (ROW0 + 6) * 8)
  c.stamp("trophy", 116, 36)
  goldRule(c, 20, 2, 29)
})
