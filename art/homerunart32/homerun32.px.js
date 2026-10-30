// HOME RUN cutscene: two 256x240 frames. The stock state 3 alternates them every 8 frames by switching
// CHR1 between $04 (scene homerun_a) and $15 (scene homerun_b). Exact NES colors on the navy $0C backdrop.
// Both frames share one nametable, one attribute table and one palette record, so every 16x16 cell keeps
// one palette of art/homerunart32/layout.json in both frames; only pixels inside a cell change between
// frames. Sky, marquee and lawn use the sky/cream/gold and sky/cream/green palettes; the stands, the
// concourse and the cast use red/cream/skin.
pal({
  k: "#183C5D",  // $0C navy backdrop
  s: "#3CBEFF",  // $21 sky
  c: "#FFE7A2",  // $38 cream
  y: "#F3BE3C",  // $28 gold
  g: "#00AA00",  // $1A green
  r: "#DB2800",  // $16 red
  t: "#FFBEB2",  // $36 stock skin
})

sprite("_cheer_a", { png: "parts/cheer.png" })
sprite("_cheer_b", { png: "parts/cheer-b.png" })
sprite("_pair", { png: "parts/pair.png" })
sprite("_batter", { png: "parts/batter.png" })
sprite("_crowd", { png: "parts/crowd-red.png" })

function cloud(c, x, y, puffs) {
  for (const [dx, dy, r] of puffs) c.circ(x + dx, y + dy, r, "c")
  const x0 = Math.min(...puffs.map(([dx, , r]) => dx - r)), x1 = Math.max(...puffs.map(([dx, , r]) => dx + r))
  const base = Math.max(...puffs.map(([, dy]) => dy))
  c.rect(x + x0 + 2, y + base, x1 - x0 - 3, 3, "c")
}
function lightTower(c, x, y, phase) {
  c.rect(x, y, 20, 14, "k")
  for (let j = 0; j < 2; j++) for (let i = 0; i < 4; i++)
    c.rect(x + 2 + i * 4, y + 2 + j * 5, 3, 4, (i + j + phase) % 2 ? "y" : "c")
  c.rect(x + 8, y + 14, 4, 50, "k")
  c.hline(x - 1, y + 14, 22, "k")
}
function pennant(c, x, y, ink, phase) {
  c.vline(x, y, 16, "k")
  c.px(x, y - 1, "y")
  const rows = phase ? ["kkkk......", "iiiikkkk..", "iiiiiiiikk", "iiiikkkk..", "kkkk......"]
    : ["kkk.......", "iiikkk....", "iiiiiikkk.", "iiiikkk...", "ikkk......"]
  for (let j = 0; j < 5; j++) for (let i = 0; i < 10; i++) {
    if (rows[j][i] === "k") c.px(x + 1 + i, y + j, "k")
    if (rows[j][i] === "i") c.px(x + 1 + i, y + j, ink)
  }
}

const GLYPHS = {
  H: ["XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXXXXXXXXX",
      "XXXXXXXXXX", "XXXXXXXXXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX"],
  O: [".XXXXXXXX.", "XXXXXXXXXX", "XXXXXXXXXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXXXXXXXXX",
      "XXXXXXXXXX", ".XXXXXXXX."],
  M: ["XX......XX", "XXX....XXX", "XXXX..XXXX", "XXXXXXXXXX", "XXXXXXXXXX", "XXX.XX.XXX", "XXX.XX.XXX",
      "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX"],
  E: ["XXXXXXXXXX", "XXXXXXXXXX", "XXXXXXXXXX", "XXX.......", "XXX.......", "XXX.......", "XXXXXXXX..",
      "XXXXXXXX..", "XXXXXXXX..", "XXX.......", "XXX.......", "XXX.......", "XXX.......", "XXXXXXXXXX",
      "XXXXXXXXXX", "XXXXXXXXXX"],
  R: ["XXXXXXXXX.", "XXXXXXXXXX", "XXXXXXXXXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXXXXXXXXX",
      "XXXXXXXXXX", "XXXXXXXXX.", "XXX..XXX..", "XXX...XXX.", "XXX...XXX.", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX"],
  U: ["XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXXXXXXXXX",
      "XXXXXXXXXX", ".XXXXXXXX."],
  N: ["XXX....XXX", "XXXX...XXX", "XXXXX..XXX", "XXXXX..XXX", "XXXXXX.XXX", "XXX.XX.XXX", "XXX.XXXXXX",
      "XXX..XXXXX", "XXX..XXXXX", "XXX...XXXX", "XXX....XXX", "XXX....XXX", "XXX....XXX", "XXX....XXX",
      "XXX....XXX", "XXX....XXX"],
}
function glyph(c, ch, x, y, face, shade) {
  const g = GLYPHS[ch]
  const on = (i, j) => j >= 0 && j < 16 && i >= 0 && i < 10 && g[j][i] === "X"
  for (let j = 0; j < 17; j++) for (let i = 0; i < 11; i++)
    if (!on(i, j) && on(i - 1, j - 1)) c.rect(x + 2 * i, y + 2 * j, 2, 2, shade)
  for (let j = 0; j < 16; j++) for (let i = 0; i < 10; i++)
    if (on(i, j)) c.rect(x + 2 * i, y + 2 * j, 2, 2, face)
}
function star(c, x, y, ink) {
  c.grid(x, y, `
  ...i...
  ...i...
  iiiiiii
  .iiiii.
  ..iii..
  .ii.ii.
  .i...i.`.replace(/i/g, ink))
}
function marquee(c, phase) {
  const x0 = 24, y0 = 16, w = 208, h = 80
  c.rect(x0, y0, w, h, "k")
  c.rect(x0 + 1, y0 + 1, w - 2, 2, "y"); c.rect(x0 + 1, y0 + h - 3, w - 2, 2, "y")
  c.rect(x0 + 1, y0 + 1, 2, h - 2, "y"); c.rect(x0 + w - 3, y0 + 1, 2, h - 2, "y")
  for (const [x, y] of [[x0, y0], [x0 + w - 1, y0], [x0, y0 + h - 1], [x0 + w - 1, y0 + h - 1]]) c.px(x, y, "s")
  for (let x = x0 + 6, k = 0; x < x0 + w - 6; x += 8, k++) {
    const lit = (k + phase) % 2 === 0
    for (const y of [y0 + 6, y0 + h - 9]) {
      c.rect(x, y, 3, 3, lit ? "c" : "y")
      c.px(x, y, "k"); c.px(x + 2, y, "k"); c.px(x, y + 2, "k"); c.px(x + 2, y + 2, "k")
    }
  }
  const face = phase ? "y" : "c", shade = phase ? "c" : "y"
  const word1 = ["H", "O", "M", "E"], word2 = ["R", "U", "N"]
  word1.forEach((ch, i) => glyph(c, ch, 40 + 24 * i, 40, face, shade))
  word2.forEach((ch, i) => glyph(c, ch, 152 + 24 * i, 40, face, shade))
  star(c, 30, 52, phase ? "c" : "y"); star(c, 219, 52, phase ? "c" : "y")
}

function stands(c, phase) {
  const dy = phase ? -2 : 0
  for (const x of [0, 80, 160, 240]) { c.stamp("_crowd", x, 104 + dy); c.stamp("_crowd", x, 136 + dy) }
  c.rect(0, 96, 256, 8, "c"); c.hline(0, 103, 256, "k")
  c.rect(0, 152, 256, 4, "c"); c.hline(0, 156, 256, "k")
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
function counter(c, x0, y0, w) {
  c.rect(x0, y0, w, 24, "c")
  c.hline(x0, y0, w, "k"); c.hline(x0, y0 + 3, w, "k")
  c.vline(x0, y0, 24, "k"); c.vline(x0 + w - 1, y0, 24, "k")
  for (let x = x0 + 8; x < x0 + w - 4; x += 16) c.vline(x, y0 + 4, 20, "k")
}

function draw(c, phase) {
  c.rect(0, 0, 256, 96, "s")
  const CLOUD = [[7, 6, 4], [14, 3, 5], [22, 5, 4], [27, 7, 3]]
  cloud(c, 96, 1, CLOUD); cloud(c, 150, 2, CLOUD)
  lightTower(c, 2, 24, phase); lightTower(c, 234, 24, phase)
  pennant(c, 14, 8, "c", phase); pennant(c, 238, 8, "c", 1 - phase)
  marquee(c, phase)
  stands(c, phase)
  c.rect(0, 157, 256, 67, "c")
  c.hline(0, 208, 256, "k")
  c.stamp("_pair", 20, 150)
  counter(c, 12, 200, 80)
  c.stamp(phase ? "_cheer_b" : "_cheer_a", 104, 156)
  c.stamp("_batter", 176, 152)
  lawn(c)
}

scene("homerun_a", { w: 256, h: 240, bg: "s" }, (c) => draw(c, 0))
scene("homerun_b", { w: 256, h: 240, bg: "s" }, (c) => draw(c, 1))
