// Power Analysis card: the selected baseball-marker card. 256x240, exact NES colors, navy $0C backdrop.
// tools/analysisart32_convert.py renders this with the pinned pxl and converts it for build_analysisart32.py.
// Rows 0-7 use only CHR $18 patterns (sky $E0, blank $20, rail $E9): the stock name writer prints the
// team name on rows 2-5 in its own fonts. Row 8 is the split strip ($E0, identical in both banks).
// Rows 9-29 use CHR $06: the stockart32 mode art at its tile phases, plus a few new patterns.
//   P0 sky $21, cream $38, gold $28   board, sky, light towers, ball sockets
//   P1 sky $21, cream $38, green $1A  lawn
//   P2 red $16, cream $38, skin $36   brick, red-shirted stock crowd, cheerleader, pair, counter
//   P3 cream $38, gold $28, sky $21   title band (CHR $18 font ink is value 1)
// Labels, digits and the hint text are not drawn here: layout.json places them as font glyph ids.
// layout.json owns the socket geometry and placements.json the part stamps; the converter refuses a
// render whose sockets or visible part pixels differ from them.
pal({
  k: "#183C5D",  // $0C navy backdrop
  s: "#3CBEFF",  // $21 sky
  c: "#FFE7A2",  // $38 cream
  y: "#F3BE3C",  // $28 gold
  g: "#00AA00",  // $1A green
  r: "#DB2800",  // $16 red
  t: "#FFBEB2",  // $36 stock skin
})

// ---------- shared with the mode menu (same code, same phases) ----------
function lightTower(c, x, y) {
  c.rect(x, y, 20, 14, "k")
  for (let j = 0; j < 2; j++) for (let i = 0; i < 4; i++) c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, "c")
  c.rect(x + 8, y + 14, 4, 60, "k")
  c.hline(x - 1, y + 14, 22, "k")
}
function bricks(c, x0, y0, w, h) {
  c.rect(x0, y0, w, h, "r")
  for (let y = y0; y < y0 + h; y++) {
    if (y % 4 === 3) { c.hline(x0, y, w, "k"); continue }
    const off = y % 8 < 4 ? 7 : 3
    for (let x = x0; x < x0 + w; x++) if (x % 8 === off) c.px(x, y, "k")
  }
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
function gateWall(c, x0, y0, w, h) {
  c.rect(x0, y0, w, h, "c")
  c.hline(x0, y0, w, "k")
}
function counter(c, x0, y0, w) {
  c.rect(x0, y0, w, 24, "c")
  c.hline(x0, y0, w, "k"); c.hline(x0, y0 + 3, w, "k")
  c.vline(x0, y0, 24, "k"); c.vline(x0 + w - 1, y0, 24, "k")
  for (let x = x0 + 8; x < x0 + w - 4; x += 16) c.vline(x, y0 + 4, 20, "k")
}
sprite("_cheer", { png: "parts/cheer.png" })
sprite("_pair", { png: "parts/pair.png" })
sprite("_crowd_l", { png: "parts/crowd-red.png", area: [0, 0, 32, 32] })
sprite("_crowd_r", { png: "parts/crowd-red.png", area: [48, 0, 32, 32] })

// ---------- title band: only CHR $18 patterns ----------
function rail(c, y) {
  // CHR $18 $E9 under P3: navy 2, cream 1, gold 2, cream 1, navy 2
  c.hline(0, y + 2, 256, "c"); c.rect(0, y + 3, 256, 2, "y"); c.hline(0, y + 5, 256, "c")
}
function titleBand(c) {
  c.rect(0, 0, 256, 80, "s")          // rows 0-9: sky ($E0 under P3), split strip included
  c.rect(0, 8, 256, 48, "k")          // rows 1-6 navy banner
  rail(c, 8); rail(c, 48)
}

// ---------- the card ----------
function statCard(c) {
  // the mode board's frame shifted down 32 px, so its bottom band, ledge and side dots keep the mode
  // tiles; the top border sits in row 9, which shares its attribute row with the split strip (P3)
  const x0 = 32, y0 = 76, w = 192, h = 79   // y 76..154
  c.rect(x0, y0, w, h, "k")
  c.rect(x0 + 1, y0 + 1, w - 2, 3, "y"); c.rect(x0 + 1, y0 + h - 4, w - 2, 3, "y")
  c.rect(x0 + 1, y0 + 1, 3, h - 2, "y"); c.rect(x0 + w - 4, y0 + 1, 3, h - 2, "y")
  for (const [x, y] of [[x0, y0], [x0 + w - 1, y0], [x0, y0 + h - 1], [x0 + w - 1, y0 + h - 1]]) c.px(x, y, "s")
  for (let x = 40; x < 220; x += 8) { c.px(x, y0 + 2, "c"); c.px(x, y0 + h - 3, "c") }
  for (let y = y0 + 8; y < y0 + h - 3; y += 8) { c.px(34, y, "c"); c.px(221, y, "c") }
}
function socket(c, x, y) {
  // an empty ball slot: the outline of the CHR $1B ball sprite, which covers it when the rating reaches it
  c.grid(x, y, `
  ..yyyy..
  .y....y.
  y......y
  y......y
  y......y
  y......y
  .y....y.
  ..yyyy..`)
}
function bButton(c, x, y) {
  // the picker draws its A button as a disc; here a cream disc with a navy B
  c.grid(x, y, `
  ..cccc..
  .cccccc.
  cckkkccc
  cckcckcc
  cckkkccc
  cckcckcc
  .ckkkcc.
  ..cccc..`)
}

scene("card", { w: 256, h: 240, bg: "s" }, (c) => {
  // lower half: bleachers run down both sides to the concourse, the pair behind the ticket counter and
  // the cheerleader beside it, the B plaque on the open ground at right
  bricks(c, 0, 160, 256, 40)
  gateWall(c, 32, 160, 192, 40)
  c.rect(0, 200, 256, 24, "c"); c.hline(0, 200, 256, "k")
  lawn(c)
  c.stamp("_pair", 56, 156)
  counter(c, 48, 200, 80)
  c.stamp("_cheer", 132, 160)
  // upper half
  c.rect(0, 0, 256, 160, "s")
  titleBand(c)
  lightTower(c, 6, 80); lightTower(c, 230, 80)
  c.rect(0, 96, 32, 104, "k"); c.stamp("_crowd_l", 0, 96); c.stamp("_crowd_l", 0, 128); c.stamp("_crowd_l", 0, 160)
  c.hline(0, 96, 32, "c")
  c.rect(224, 96, 32, 104, "k"); c.stamp("_crowd_r", 224, 96); c.stamp("_crowd_r", 224, 128); c.stamp("_crowd_r", 224, 160)
  c.hline(224, 96, 32, "c")
  c.rect(32, 155, 192, 4, "c"); c.hline(32, 159, 192, "k")
  statCard(c)
  // sockets: rows 11, 13, 15, 17 (layout.json stats) by columns 16, 18, 20, 22 (layout.json sockets)
  for (const row of [11, 13, 15, 17]) for (const col of [16, 18, 20, 22]) socket(c, col * 8, row * 8)
  c.rect(192, 205, 56, 11, "k"); c.rect(192, 216, 56, 3, "k")
  bButton(c, 25 * 8, 26 * 8)
})
