pal({
  k: "#183C5D",  // $0C slate navy backdrop
  W: "#FFFFFF",  // $30 white
  y: "#F3BE3C",  // $28 gold
  r: "#DB2800",  // $16 red
  g: "#00AA00",  // $1A green
})

const BIG = {
  A: [".####.", "#....#", "#....#", "######", "#....#", "#....#", "#....#"],
  B: ["#####.", "#....#", "#....#", "#####.", "#....#", "#....#", "#####."],
  E: ["######", "#.....", "#.....", "#####.", "#.....", "#.....", "######"],
  G: [".#####", "#.....", "#.....", "#..###", "#....#", "#....#", ".####."],
  I: ["######", "..##..", "..##..", "..##..", "..##..", "..##..", "######"],
  L: ["#.....", "#.....", "#.....", "#.....", "#.....", "#.....", "######"],
  S: [".#####", "#.....", "#.....", ".####.", ".....#", ".....#", "#####."],
  T: ["######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."],
  U: ["#....#", "#....#", "#....#", "#....#", "#....#", "#....#", ".####."],
}
for (const [ch, rows] of Object.entries(BIG)) {
  sprite(`big_${ch}`, { w: 16, h: 16 }, (c) => {
    for (let y = 0; y < 7; y++) for (let x = 0; x < 6; x++) if (rows[y][x] === "#")
      c.rect(2 + 2 * x + 1, 1 + 2 * y + 1, 2, 2, "r")
    for (let y = 0; y < 7; y++) for (let x = 0; x < 6; x++) if (rows[y][x] === "#")
      c.rect(2 + 2 * x, 1 + 2 * y, 2, 2, y < 3 ? "W" : "y")
  })
}

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

sprite("copyright", `
  ..WWWW..
  .W....W.
  W..WW..W
  W.W....W
  W.W....W
  W..WW..W
  .W....W.
  ..WWWW..`)

const FRAME_TOP = 9, FRAME_BOTTOM = 230
function screenFrame(c) {
  for (const inset of [0, 2]) {
    const x0 = 2 + inset, x1 = 253 - inset, y0 = FRAME_TOP + inset, y1 = FRAME_BOTTOM - inset
    c.hline(x0 + 2, y0, x1 - x0 - 3, "W"); c.hline(x0 + 2, y1, x1 - x0 - 3, "W")
    c.vline(x0, y0 + 2, y1 - y0 - 3, "W"); c.vline(x1, y0 + 2, y1 - y0 - 3, "W")
    c.px(x0 + 1, y0 + 1, "W"); c.px(x1 - 1, y0 + 1, "W"); c.px(x0 + 1, y1 - 1, "W"); c.px(x1 - 1, y1 - 1, "W")
  }
}
function goldRule(c, row, col0, col1) {
  const y = row * 8 + 2, x0 = col0 * 8 + 3, x1 = (col1 + 1) * 8 - 4
  c.hline(x0 + 2, y, x1 - x0 - 3, "y"); c.hline(x0 + 2, y + 2, x1 - x0 - 3, "y")
  for (const [x, d] of [[x0, 1], [x1, -1]]) {
    c.px(x + d, y, "y"); c.px(x, y + 1, "y"); c.px(x + 2 * d, y + 1, "y"); c.px(x + d, y + 2, "y")
  }
}
function word(c, text, x, y) {
  for (const [i, ch] of [...text].entries()) if (ch !== " ") c.stamp(`big_${ch}`, x + 16 * i, y)
}
function baseballWord(c, text, x, y) {
  for (const [i, ch] of [...text].entries()) {
    const rows = BIG[ch]
    for (const [dx, dy, shadow] of [[2, 2, true], [0, 0, false]])
      for (let yy = 0; yy < 7; yy++) for (let xx = 0; xx < 6; xx++)
        if (rows[yy][xx] === "#") c.rect(x + i * 22 + xx * 3 + dx, y + yy * 3 + dy,
          3, 3, shadow ? "r" : yy < 3 ? "W" : "y")
  }
}
function stadium(c) {
  for (let y = 0; y < 13; y++) {
    const half = 68 + Math.floor(y * 1.2)
    const yy = 96 + y
    for (let x = 128 - half; x < 128 + half; x++) {
      if (y === 0 || y === 12) c.px(x, yy, "W")
      else if (y % 3 === 0) c.px(x, yy, "y")
      else if (x % 5 === (y % 3)) c.px(x, yy, "W")
    }
  }
  for (let y = 0; y < 50; y++) {
    const half = 82 - Math.floor(y * 1.58)
    c.hline(128 - half, 110 + y, 2 * half + 1, "g")
    c.px(127 - half, 110 + y, "W"); c.px(129 + half, 110 + y, "W")
  }
  const cx = 128, cy = 140, hw = 25, hh = 17
  for (let y = -hh; y <= hh; y++) {
    const half = Math.floor(hw * (1 - Math.abs(y) / hh))
    c.hline(cx - half, cy + y, 2 * half + 1, "y")
    c.px(cx - half, cy + y, "W"); c.px(cx + half, cy + y, "W")
  }
  for (let y = -9; y <= 9; y++) {
    const half = Math.floor(14 * (1 - Math.abs(y) / 9))
    c.hline(cx - half, cy + y, 2 * half + 1, "g")
  }
  c.rect(126, 139, 5, 2, "y"); c.hline(127, 139, 3, "W")
  for (const [x, y] of [[127, 123], [103, 139], [151, 139], [127, 155]]) c.rect(x, y, 3, 3, "W")
  for (const x of [23, 225]) {
    c.vline(x + 3, 102, 39, "y"); c.vline(x + 4, 102, 39, "W")
    c.hline(x - 4, 141, 16, "y")
    c.rect(x - 5, 94, 18, 9, "y")
    for (let row = 0; row < 2; row++) for (let col = 0; col < 4; col++)
      c.rect(x - 4 + col * 4, 95 + row * 4, 3, 3, "W")
  }
}

scene("title", { w: 256, h: 240, bg: "k" }, (c) => {
  screenFrame(c)
  word(c, "LITTLE LEAGUE", 24, 24)
  baseballWord(c, "BASEBALL", 41, 46)
  goldRule(c, 10, 4, 27)
  stadium(c)
  c.stamp("ball", 40, 164)
  c.stamp("ball", 200, 164)
  c.stamp("copyright", 24, 200)
})
