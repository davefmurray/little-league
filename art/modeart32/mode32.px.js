// Mode menu: the sunny ballpark gate. 256x240, exact NES colors, navy $0C backdrop.
// Every 16x16 cell keeps to one of four palettes (layout.json). Cream is value 2 in all of them, the
// stock font's ink, so any palette can sit under text; value 1 and 3 line up too, so tiles dedupe:
//   P0 sky $21, cream $38, gold $28   sky, clouds, sign, scoreboard, flags, light towers
//   P1 sky $21, cream $38, green $1A  lawn
//   P2 red $16, cream $38, tan $27    brick, awning, bunting, cart, red-side people and fans
//   P3 blue $12, cream $38, brown $17 blue-side people and fans
// Navy is free in every cell: outlines, hair, mortar, the board. CHR $06 holds 256 patterns, 24 of them
// the stock font at its ASCII ids, so the art has 232: repeat tiles before cutting people.
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

// ---------- side scenery ----------
function stands(c, x0) {
  // bleachers beside the board: seven tiers of fans, one tile row per tier, a fan every 8 px, so the
  // whole crowd is two tiles; standsBlue recolors every other 16-px band to P3 for a mixed crowd
  c.rect(x0, 64, 32, 59, "k")
  c.hline(x0, 64, 32, "c")
  for (let k = 0; k < 7; k++) {
    const y = 65 + 8 * k
    for (let x = x0 + (k & 1 ? 4 : 0) - 8; x < x0 + 32; x += 8) {
      const fan = k & 1 ? FAN_B : FAN_A
      for (let j = 0; j < fan.length; j++) for (let i = 0; i < 8; i++) {
        const ch = fan[j][i], X = x + i
        if (ch !== "." && X >= x0 && X < x0 + 32) c.px(X, y + j, ch)
      }
    }
  }
  c.rect(x0, 120, 32, 3, "c")
}
const FAN_A = ["..rrrr..", ".rrrrrr.", "..tktk..", "..tttt..", ".cccccc.", "cccccccc", "cccccccc"]
const FAN_B = ["..kkkk..", ".kttttk.", "..tktk..", "..tttt..", ".rrrrrr.", "rrrrrrrr", "rrrrrrrr"]
function standsBlue(c, x0) {
  stands(c, x0)
  for (let y = 64; y < 123; y++) for (let x = x0; x < x0 + 32; x++) {
    const cellBlue = (y >> 4) & 1
    if (!cellBlue) continue
    const k = c.key(x, y)
    if (k === "r") c.px(x, y, "b"); else if (k === "t") c.px(x, y, "d")
  }
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
function pilaster(c, x) {
  // cream stone column between an arch and the middle, with a capital under the ledge
  c.rect(x, 128, 16, 64, "c")
  c.vline(x, 128, 64, "k"); c.vline(x + 15, 128, 64, "k")
  c.rect(x, 128, 16, 3, "c"); c.hline(x, 131, 16, "k")
  for (let y = 139; y < 192; y += 8) { c.hline(x + 1, y, 14, "k"); c.px(x + ((y >> 3) & 1 ? 5 : 10), y - 4, "k") }
}
function crowd(c, x0, x1, y0, rows) {
  // little heads under an arch: cap, face, shoulders; navy between them
  for (let j = 0; j < rows.length; j++) {
    const y = y0 + j * 7
    for (let x = x0 + (j & 1 ? 4 : 0); x + 4 < x1; x += 8) {
      const [cap, shirt] = rows[j][((x - x0) >> 3) % rows[j].length]
      c.hline(x + 1, y, 3, cap); c.rect(x, y + 1, 5, 3, "t"); c.px(x + 1, y + 2, "k"); c.px(x + 3, y + 2, "k")
      c.rect(x - 1, y + 4, 7, 3, shirt)
    }
  }
}
function arch(c, x0, crowdRows) {
  // opening x0..x0+47, crown 134, springline 158; crowd and a string of pennants inside
  const cx = x0 + 23.5, cy = 158
  for (let y = 128; y < 192; y++) for (let x = x0 - 4; x < x0 + 52; x++) {
    const d = Math.hypot(x - cx, Math.max(0, cy - y))
    if (d < 24) c.px(x, y, "k")
    else if (d < 27.5) c.px(x, y, d < 25 ? "k" : "c")
  }
  c.rect(cx - 2, 130, 4, 5, "c"); c.hline(cx - 2, 135, 4, "k")
  c.hline(x0 + 4, 140, 40, "c")
  for (let i = 0; i < 5; i++) c.grid(x0 + 5 + i * 8, 141, i & 1 ? "ccc\n.c." : "rrr\n.r.")
  crowd(c, x0 + 2, x0 + 46, 146, crowdRows)
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
function awning(c) {
  c.rect(96, 146, 64, 2, "k")
  for (let y = 148; y < 157; y++) for (let x = 96; x < 160; x++) c.px(x, y, (x >> 2) & 1 ? "c" : "r")
  for (let x = 96; x < 160; x += 4) c.grid(x, 157, (x >> 2) & 1 ? "cccc\n.cc." : "rrrr\n.rr.")
}
function ticketWindow(c) {
  c.rect(96, 160, 64, 32, "c")
  c.rect(104, 162, 48, 22, "k")
  c.rect(100, 183, 56, 4, "c"); c.hline(100, 187, 56, "k"); c.hline(100, 182, 56, "k")
  c.vline(96, 160, 32, "k"); c.vline(159, 160, 32, "k")
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

// ---------- people ----------
// Drawn in P2 keys (r red, c cream, t tan); BLUE swaps a figure to P3 (b blue, d brown).
const BLUE = { r: "b", t: "d" }
function at(rows, dx, dy) {
  const out = {}
  for (const [y, runs] of Object.entries(rows)) out[+y + dy] = runs.map(([x, s]) => [x + dx, s])
  return out
}
// kid head, front, cap with an L (14x15)
const KIDHEAD = {
  0: [[5, "kkkk"]], 1: [[3, "kkrrrrkk"]], 2: [[2, "krrrrcrrrk"]], 3: [[1, "krrrrrcrrrrk"]],
  4: [[1, "krrrrrcccrrk"]], 5: [[1, "krrrrrrrrrrk"]], 6: [[0, "kkkkkkkkkkkkkk"]],
  7: [[1, "kttttttttttk"]], 8: [[1, "kttkttttkttk"]], 9: [[1, "kttkttttkttk"]], 10: [[1, "kttttttttttk"]],
  11: [[1, "ktttkkkktttk"]], 12: [[2, "ktttkktttk"]], 13: [[3, "kttttttk"]], 14: [[4, "kkkkkk"]],
}
// repeat rows to lengthen a figure: stretch [[row, extra], ...] across all of its run layers
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
// both kids share the legs, so their lowest tiles dedupe (same x phase on screen)
const KIDLEGS = {
  23: [[4, "kccccccccccck"]], 24: [[4, "kcrcccccccrck"]], 25: [[4, "kcrcccccccrck"]], 26: [[4, "kcrccckcccrck"]],
  27: [[4, "kcrcck.kccrck"]], 28: [[4, "kcrck...kcrck"]], 29: [[4, "kccck...kccck"]], 30: [[4, "krrrk...krrrk"]],
  31: [[4, "krrrk...krrrk"]], 32: [[4, "krcrk...krcrk"]], 33: [[4, "krrrk...krrrk"]],
  34: [[3, "kkkkkk..kkkkkk"]], 35: [[2, "kkkkkkk..kkkkkkk"]],
}
// red-team kid, front, waving, glove on the other hand (21x36)
sprite("kid_red", { w: 21, h: 36 }, fig([{
  1: [[1, "kk"]], 2: [[0, "ktk"]], 3: [[0, "kttk"]], 4: [[0, "kttk"]], 5: [[0, "kttk"]], 6: [[1, "ktk"]],
  7: [[1, "ktk"]], 8: [[1, "kttk"]], 9: [[2, "ktk"]], 10: [[2, "ktk"]], 11: [[2, "krrk"]], 12: [[2, "krrk"]],
  13: [[2, "krrk"]], 14: [[3, "krrk"]] }, at(KIDHEAD, 4, 0), KIDLEGS, {
  15: [[3, "kkrrrrkkkrrrrkk"]], 16: [[3, "krrrrrrcrrrrrrrk"]], 17: [[3, "krrrrrrcrrrrrrrrk"]],
  18: [[3, "krrrrrrcrrrrkrrrk"]], 19: [[3, "krrrrrrcrrrrkkkkk"]], 20: [[3, "krrrrrrcrrrkttttk"]],
  21: [[3, "krrrrrrcrrkttttttk"]], 22: [[3, "kkkkkkkkkkkttkkttk"]], 23: [[14, "ktttttk"]],
  24: [[15, "ktttk"]], 25: [[16, "kkk"]] }]))
// blue-team kid, front, bat on the shoulder, glancing (23x36)
sprite("kid_blue", { w: 23, h: 36, swap: BLUE }, fig([{
  0: [[19, "kk"]], 1: [[18, "kcck"]], 2: [[18, "kcck"]], 3: [[17, "kcck"]], 4: [[17, "kcck"]], 5: [[17, "kck"]],
  6: [[17, "kck"]], 7: [[17, "kck"]], 8: [[17, "kck"]], 9: [[17, "kck"]], 10: [[17, "kck"]], 11: [[17, "kck"]] },
  at(GLANCE, 4, 0), KIDLEGS, {
  12: [[16, "kttk"]], 13: [[16, "kttk"]], 14: [[15, "kkkkk"]],
  15: [[3, "kkrrrrkkkrrrrkrrk"]], 16: [[3, "krrrrrrcrrrrrrrk"]], 17: [[3, "krrrrrrcrrrrrrrk"]],
  18: [[3, "krkrrrrcrrrrrrrk"]], 19: [[3, "krkrrrrcrrrrrrrk"]], 20: [[3, "ktkrrrrcrrrrrrrk"]],
  21: [[3, "ktkrrrrcrrrrrrrk"]], 22: [[3, "ktkkkkkkkkkkkkkk"]] }]))

// adult face under navy hair (12x11)
const MANHEAD = {
  0: [[3, "kkkkkk"]], 1: [[2, "kkkkkkkk"]], 2: [[1, "kkkkkkkkkk"]], 3: [[1, "kkttttttkk"]],
  4: [[0, "kkttttttttkk"]], 5: [[0, "ktkkttttkktk"]], 6: [[0, "kttttttttttk"]], 7: [[1, "kttttttttk"]],
  8: [[1, "kttkkkkttk"]], 9: [[2, "kttttttk"]], 10: [[3, "kkkkkk"]],
}

// dad with a cheering toddler on his shoulders (16x51)
sprite("dad", { w: 16, h: 51 }, fig([{
  0: [[0, ".kk..........kk."]],
  1: [[0, "kttk........kttk"]],
  2: [[0, "kttk........kttk"]],
  3: [[0, "ktk...kkkk...ktk"]],
  4: [[0, "ktk.kkrrrrkk.ktk"]],
  5: [[0, "ktkkrrrcrrrrkktk"]],
  6: [[0, "krkkrrrccrrrkkrk"]],
  7: [[0, "krkkkkkkkkkkkkrk"]],
  8: [[0, "krkkttttttttkkrk"]],
  9: [[0, "krkktkttttktkkrk"]],
  10: [[0, "krkkttttttttkkrk"]],
  11: [[0, "krrkttkkkkttkrrk"]],
  12: [[0, ".krrkttkkttkrrk."]],
  13: [[0, ".krrrkkkkkkrrrk."]],
  14: [[0, ".krrrrrrrrrrrrk."]],
  15: [[0, "kcccckkkkkkcccck"]],
  16: [[0, "kccckkkkkkkkccck"]],
  17: [[0, "kttkkkkkkkkkkttk"]],
  18: [[0, "kttkkttttttkkttk"]],
  19: [[0, "ktkkttttttttkktk"]],
  20: [[0, "ktktkkttttkktktk"]],
  21: [[0, "ktkttttttttttktk"]],
  22: [[0, "kkkkttttttttkkkk"]],
  23: [[0, "kkkkttkkkkttkkkk"]],
  24: [[0, "....kttttttk...."]],
  25: [[0, ".kkkkkkkkkkkkkk."]],
  26: [[0, ".kccccrrrrcccck."]],
  27: [[0, "kccccccrrcccccck"]],
  28: [[0, "kccccccrrcccccck"]],
  29: [[0, "kcckcccccccckcck"]],
  30: [[0, "kttkcccccccckttk"]],
  31: [[0, "kttkcccccccckttk"]],
  32: [[0, "kttkcccccccckttk"]],
  33: [[0, "kttkcccccccckttk"]],
  34: [[0, "kttkkkkkkkkkkttk"]],
  35: [[0, ".kk.kkkkkkkk.kk."]],
  36: [[0, "...kkkkkkkkkk..."]],
  37: [[0, "...kkkkkkkkkk..."]],
  38: [[0, "...kkkkkkkkkk..."]],
  39: [[0, "...kkkkkkkkkk..."]],
  40: [[0, "....kttk..kttk.."]],
  41: [[0, "....kttk..kttk.."]],
  42: [[0, "....kttk..kttk.."]],
  43: [[0, "....kttk..kttk.."]],
  44: [[0, "....kcck..kcck.."]],
  45: [[0, "...kkkkk.kkkkk.."]],
  46: [[0, "..kkkkkk.kkkkkk."]],
}], [[31, 2], [42, 2]]))

// mom in a sun hat, cream dress, red belt and bag (16x37)
sprite("mom", { w: 16, h: 37 }, fig([{
  0: [[0, ".....kkkkkk....."]],
  1: [[0, "....kcccccck...."]],
  2: [[0, "...kcccccccck..."]],
  3: [[0, "...krrrrrrrrk..."]],
  4: [[0, ".kkkcccccccckkk."]],
  5: [[0, "kcccccccccccccck"]],
  6: [[0, ".kkkkkkkkkkkkkk."]],
  7: [[0, "..kkttttttttkk.."]],
  8: [[0, "..kktkttttktkk.."]],
  9: [[0, "..kktkttttktkk.."]],
  10: [[0, "..kkttttttttkk.."]],
  11: [[0, "..kktkttttktkk.."]],
  12: [[0, "..kkktkkkktkkk.."]],
  13: [[0, "..kkkkttttkkkk.."]],
  14: [[0, "..kkk.kkkk.kkk.."]],
  15: [[0, "...k..kttk..k..."]],
  16: [[0, "...kcccccccck..."]],
  17: [[0, "..kcccccccccck.."]],
  18: [[0, ".kckcccccccckck."]],
  19: [[0, ".ktkcccccccckck."]],
  20: [[0, ".ktkcccccccckttk"]],
  21: [[0, ".ktkrrrrrrrrktk."]],
  22: [[0, ".ktkcccccccckrrk"]],
  23: [[0, ".kkkcccccccckrrk"]],
  24: [[0, "..kcccccccccckkk"]],
  25: [[0, "..kcccccccccck.."]],
  26: [[0, ".kccccccccccccck"]],
  27: [[0, "kcccccccccccccck"]],
  28: [[0, "kkkkkkkkkkkkkkkk"]],
  29: [[0, ".....ktk..ktk..."]],
  30: [[0, ".....ktk..ktk..."]],
  31: [[0, ".....ktk..ktk..."]],
  32: [[0, ".....ktk..ktk..."]],
  33: [[0, ".....kkk..kkk..."]],
  34: [[0, "....kkkk..kkkk.."]],
}], [[25, 1], [31, 1]]))

// ticket buyer, three quarters from behind, reaching to the window; the arm stays above y 176 so the
// P3 line kid's cells stay blue (22x43)
sprite("buyer", { w: 22, h: 43 }, fig([{
  0: [[4, "kkkkkk"]], 1: [[3, "krrrrrrk"]], 2: [[2, "krrrrrrrrk"]], 3: [[2, "krrrrrrrrrkkk"]],
  4: [[2, "kkkkkkkkkkkkk"]], 5: [[2, "kkkkkkkkttk"]], 6: [[2, "kkkkkkkkttk"]], 7: [[2, "kkkkkkkttttk"]],
  8: [[2, "kkkkkkkttttk"]], 9: [[3, "kkkkkkttttk"]], 10: [[4, "kkkkktttk"]], 11: [[5, "kkkkkk"]],
  12: [[2, "kkcccccccckk"]], 13: [[1, "kccccccccccckkkk"]], 14: [[0, "kcccccccccccccccckkkk"]],
  15: [[0, "kcccccccccccckkkkkttk"]], 16: [[0, "kccccccccccck...kccck"]], 17: [[0, "kcckcccccccck....kkk"]],
  18: [[0, "kcckccccccccck"]], 19: [[0, "kcckccccccccck"]], 20: [[0, "kcckccccccccck"]],
  21: [[0, "kttkccccccccck"]], 22: [[0, "kttkccccccccck"]], 23: [[1, "kkkccccccccck"]],
  24: [[2, "kkkkkkkkkkk"]], 25: [[2, "kkkkkkkkkkk"]], 26: [[2, "kkkkkkkkkkk"]], 27: [[2, "kkkkk.kkkkk"]],
  28: [[2, "kkkkk.kkkkk"]], 29: [[2, "kkkkk.kkkkk"]], 30: [[2, "kkkkk.kkkkk"]],
  31: [[1, "kkkkkk.kkkkkk"]], 32: [[1, "kkkkkk.kkkkkkk"]],
}], [[20, 2], [29, 8]]))

// small kid in line, from behind (P3, 14x26)
sprite("linekid", { w: 14, h: 25, swap: BLUE }, fig([{
  0: [[4, "kkkk"]], 1: [[2, "kkrrrrkk"]], 2: [[1, "krrrrrrrrk"]], 3: [[1, "krrrrrrrrk"]],
  4: [[1, "kkkkkkkkkk"]], 5: [[1, "kkkkkkkkkkk"]], 6: [[0, "ktkkkkkkkktk"]], 7: [[0, "ktkkkkkkkktk"]],
  8: [[1, "kkkkkkkkkk"]], 9: [[2, "kkttttkk"]], 10: [[1, "kkcccccckk"]], 11: [[0, "kcccccccccck"]],
  12: [[0, "kcccccccccck"]], 13: [[0, "kccccccccccck"]], 14: [[0, "ktcccccccctk"]], 15: [[0, "ktcccccccctk"]],
  16: [[0, "kkcccccccckk"]], 17: [[1, "krrrrrrrrk"]], 18: [[1, "krrrrrrrrk"]], 19: [[1, "krrrrkrrrk"]],
  20: [[2, "kttk.kttk"]], 21: [[2, "kttk.kttk"]], 22: [[2, "kttk.kttk"]], 23: [[2, "kcck.kcck"]],
  24: [[1, "kkkkk.kkkkk"]],
}]))

// woman in line, three quarters toward the window, ponytail (16x46)
sprite("woman", { w: 16, h: 46 }, fig([{
  0: [[4, "kkkkkk"]], 1: [[3, "kkkkkkkk"]], 2: [[2, "kkkkkkkkkk"]], 3: [[1, "kkkkkkkkttk"]],
  4: [[0, "kkkkkkkttttk"]], 5: [[0, "kk.kkkttkttkk"]], 6: [[0, "kkrkkkttkttk"]], 7: [[1, "kkkkkttttttk"]],
  8: [[3, "kkkttkkttk"]], 9: [[4, "kkktttttk"]], 10: [[5, "kkkkkk"]], 11: [[6, "kttk"]],
  12: [[4, "krrrrrrk"]], 13: [[3, "krrrrrrrrk"]], 14: [[3, "krrrrrrrrk"]], 15: [[3, "krrrrrrrrrk"]],
  16: [[4, "krrrrrrrk"]], 17: [[4, "krrrrrtrk"]], 18: [[4, "krrrrtttk"]], 19: [[5, "krrrkttk"]],
  20: [[5, "krrrrkk"]], 21: [[6, "krrrrk"]], 22: [[5, "kkkkkkk"]], 23: [[5, "kkkkkkk"]],
  24: [[4, "kkkkkkkk"]], 25: [[4, "kkkkkkkk"]], 26: [[4, "kkkkkkkkk"]], 27: [[4, "kkkkkkkkk"]],
  28: [[4, "kkkkkkkkkk"]], 29: [[4, "kkkkkkkkkk"]], 30: [[4, "kkkkkkkkkk"]], 31: [[5, "ktk..ktk"]],
  32: [[5, "ktk..ktk"]], 33: [[5, "ktk..ktk"]], 34: [[5, "ktk..ktk"]], 35: [[5, "ktk..ktk"]],
  36: [[5, "ktk..ktk"]], 37: [[5, "krrk.krrk"]], 38: [[5, "kkkkkkkkkk"]],
}], [[20, 3], [27, 3], [33, 1]]))

// ticket seller in the window: cap, smile, bow tie, a ticket held up (16x18)
sprite("seller", { w: 16, h: 18 }, fig([at(KIDHEAD, 1, 0), {
  15: [[1, "kccccckrkcccck"]], 16: [[0, "kcccccrrrcccccck"]], 17: [[0, "kcccccckcccccck"]] }, {
  11: [[11, "kkkk"]], 12: [[11, "kcck"]], 13: [[11, "kcck"]], 14: [[10, "kttttk"]], 15: [[10, "kttttk"]],
  16: [[11, "kkkk"]] }]))

// girl with a box of popcorn held in front, ponytail (16x34)
sprite("girl", { w: 16, h: 34 }, fig([{
  5: [[13, "kk"]], 6: [[13, "kkk"]], 7: [[14, "kkk"]], 8: [[14, "kk"]], 9: [[14, "kk"]], 10: [[14, "k"]] },
  at({ ...KIDHEAD, 8: [[1, "kttkttttkttk"]], 9: [[1, "kttkttttkttk"]], 11: [[1, "kttkttttkttk"]],
       12: [[2, "kttkkkkttk"]] }, 0, 0), {
  7: [[1, "k"], [12, "k"]], 8: [[0, "kk"]], 9: [[0, "kk"]], 10: [[0, "k"]],
  15: [[2, "kkcccccckk"]], 16: [[1, "kcccccccccck"]], 17: [[0, "kccccccccccck"]],
  18: [[0, "kctk.c.cc.ktck"]], 19: [[0, "kctkccccccktck"]], 20: [[0, "kttkkkkkkkkttk"]],
  21: [[0, "kkkkcrrccrrkkk"]], 22: [[1, "kk.kcrrccrrk"]], 23: [[3, "kcrrccrrk"]], 24: [[3, "kcrrccrrk"]],
  25: [[3, "kkkkkkkkk"]], 26: [[3, "krrrkrrrk"]], 27: [[3, "kttk.kttk"]], 28: [[3, "kttk.kttk"]],
  29: [[3, "kttk.kttk"]], 30: [[3, "kttk.kttk"]], 31: [[3, "kcck.kcck"]], 32: [[2, "kkkkk.kkkkk"]],
  33: [[2, "kkkkk.kkkkkk"]] }]))

// fan in a number 10 jersey walking into the arch, from behind (P3, 15x40)
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

// popcorn cart with the vendor inside: striped canopy, shaded back, glass case of popcorn, red body
// with a cream band, wheel. 40x64, stamped on the tile grid so stripes, popcorn and body repeat.
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
// one 8x8 tile of popcorn: cream puffs, tan kernels, navy gaps (repeats in the glass case)
const POPCORN = ["cctcccck", "ccccctcc", "tcckcccc", "cccccccc", "ckcccctc", "ccctcccc", "cccccckc", "ctcccccc"]

scene("mode", { w: 256, h: 240, bg: "s" }, (c) => {
  const CLOUD = [[7, 6, 4], [14, 3, 5], [22, 5, 4], [27, 7, 3]]
  cloud(c, 0, 13, CLOUD); cloud(c, 224, 13, CLOUD)
  lightTower(c, 6, 32); lightTower(c, 230, 32)
  pennant(c, 44, 25, "y"); pennant(c, 52, 17, "c"); pennant(c, 204, 25, "y"); pennant(c, 212, 17, "c")
  board(c)
  marquee(c)
  standsBlue(c, 0); standsBlue(c, 224)
  c.rect(0, 123, 256, 4, "c"); c.hline(0, 127, 256, "k")
  bricks(c, 0, 128, 256, 64)
  const RED = [["r", "c"], ["k", "r"]]
  arch(c, 16, [RED, RED]); arch(c, 192, [RED, RED])
  pilaster(c, 64); pilaster(c, 176)
  bunting(c, 80); bunting(c, 112); bunting(c, 144)
  awning(c)
  ticketWindow(c)
  c.rect(0, 192, 256, 8, "c"); c.hline(0, 192, 256, "k")
  for (let x = 4; x < 256; x += 16) c.vline(x, 193, 7, "k")
  c.rect(0, 200, 256, 24, "c"); c.hline(0, 200, 256, "k")
  lawn(c)
  // people, back to front; each 16x16 cell holds one palette, so neighbours of different
  // palettes stand in different cell columns (P2 dad, mom, red kid, buyer, seller, woman, girl, cart;
  // P3 blue kid, line kid, number 10)
  c.stamp("seller", 120, 166)
  c.stamp("fan10", 193, 160)
  c.stamp("cart", 216, 160)
  c.stamp("dad", 0, 152)
  c.stamp("mom", 16, 168)
  c.stamp("buyer", 80, 160)
  c.stamp("linekid", 98, 181)
  c.stamp("woman", 136, 160)
  c.stamp("girl", 160, 176)
  c.stamp("kid_blue", 34, 184)
  c.stamp("kid_red", 66, 184)
  // soft shadows under the front figures, inside tiles their feet already use
  for (const [x0, x1, y] of [[35, 52, 220], [67, 84, 220], [162, 174, 210]])
    for (let x = x0; x <= x1; x++) if ((x & 1) === 0) c.px(x, y, "k")
})
