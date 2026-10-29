#!/usr/bin/env python3
"""Run the stock scoreboard scenes $0A and $0B on the CPU model from a planted game state.

tools/test_scoreart32.py drives every runtime check through this module. A machine is
tools/frontend32_test_machine.Boot (render_menu32.Machine with controller 2, an approximate
sprite-0 hit and the vblank-poll race), first set up the way render_menu32.stock_machine leaves a
game in progress: the sound engine running a song, gameplay CHR, a non-menu MMC1 mode, guards
clear and unrelated RAM. enter() plants an Entry and calls scene $0A as the dispatcher does: bank
4 mapped, $047B = $0A and the main loop's return address $CC13 on the stack, so scene $0B, its
exits and the frames after them run the real code. A planted championship series (heap, markers)
lets a final reach the bank-11 results gate. It is a CPU timing model with an approximate PPU;
pictures, hardware timing and real-core acceptance belong to the root emulator gates.
"""
from dataclasses import dataclass, field

from frontend32_test_machine import SCENE, Boot
import render_menu32 as R
from scoreart32_assets import LINE_BYTES, Board

HALVES, LINE, RUNS, STATS = 0x048A, 0x06F6, 0x048B, 0x0738
ENTRY, WRITER, DRAWN, MAIN_LOOP = 0xB39D, 0xB3D4, 0xB3F2, 0xCC13
WAIT_EXIT, WAIT_RETURN = 0xC266, 0xC26D     # $C260: past its BIT $2002 loop; its PLA
LABEL_SLOTS = (1, 13, 25, 37)               # $B5BA: first OAM slot of each team-name label
LABEL_SPRITES = 10                          # five characters, two 8x8 sprites each


@dataclass(frozen=True)
class Entry:
    """A scene $0A entry: the board and the state its exits read."""
    board: Board
    teams: tuple = (0x0D, 0x0F)       # $04EF/$04F0 team ids, side 0 on top
    over: int = 0                     # $04D0: 0 live, 1 final, 2 the called 18-inning tie
    quiet: int = 0                    # $07EE: 1 skips the jingle
    cpu: tuple = (0x80, 0x80)         # $04EB/$04EC: bit 7 marks a CPU side
    championship: int = 0            # $04E2: a final then leaves through the bracket
    attract: int = 0                  # $A7: the attract demo
    pokes: tuple = field(default=())  # (address, value) written after the plant


def board(halves, line=(), runs=(0, 0), stats=((0, 0),) * 7):
    return Board(halves, bytes(line) + bytes(LINE_BYTES - len(line)), tuple(runs), tuple(map(tuple, stats)))


SAMPLES = {
    "top of the 1st": Entry(board(1, [0], (0, 0), ((3, 0),) + ((0, 0),) * 6)),
    "mid 4th": Entry(board(7, [1, 0, 0, 2, 3, 0, 1], (5, 2),
                           ((14, 11), (6, 4), (1, 0), (3, 5), (2, 1), (0, 1), (1, 0))), teams=(0x02, 0x0D)),
    "final, X": Entry(board(12, [0, 1, 2, 0, 0, 0, 1, 1, 0, 0, 0, 0x80], (3, 2),
                            ((22, 19), (7, 5), (1, 1), (4, 6), (2, 3), (1, 0), (0, 1))), teams=(0x05, 0x1F), over=1),
    "walk-off": Entry(board(12, [0, 0, 1, 0, 0, 0, 0, 0, 2, 0, 0, 0x82], (3, 4),
                            ((21, 23), (5, 9), (0, 1), (6, 2), (1, 2), (0, 0), (2, 0))), teams=(0x10, 0x03), over=1),
    "ten-run rule": Entry(board(8, [0, 4, 0, 7, 0, 0, 0, 0x80], (0, 11),
                                ((12, 17), (2, 12), (0, 3), (5, 1), (0, 4), (0, 0), (0, 1))),
                          teams=(0x1E, 0x00), over=1),
    "two-digit": Entry(board(10, [12, 0, 0, 11, 3, 10, 0, 0, 1, 0], (16, 21),
                             ((31, 40), (18, 22), (4, 7), (10, 12), (9, 13), (2, 3), (1, 2))), teams=(0x0B, 0x16)),
    "9th": Entry(board(17, [0] * 16 + [1], (4, 3), ((30, 28), (7, 6), (1, 0), (8, 9), (3, 2), (0, 1), (1, 1))),
                 teams=(0x07, 0x18)),
    "15th": Entry(board(29, [0] * 28 + [2], (7, 5), ((55, 52), (13, 12), (2, 2), (15, 14), (6, 7), (2, 3), (3, 2))),
                  teams=(0x1F, 0x10)),
    "called tie": Entry(board(36, [0] * 36, (2, 2), ((66, 64), (10, 11), (1, 1), (20, 19), (8, 9), (1, 1), (2, 3))),
                        teams=(0x04, 0x1C), over=2),
}


def machine(rom, pads=(None, None), song=0x02, control=0x1F, chr_banks=(0x12, 0x16)):
    """Boot, set up as render_menu32.stock_machine leaves a game: `song` playing (the in-game $02 by default),
    gameplay CHR, guards clear, no NMI work pending and garbage elsewhere."""
    m = Boot(rom, pads)
    m.mpu.sp = 0xEF
    m.ram[0x04EA] = 0
    m.call(0xCF59)
    m.call(0xC249, a=song)
    m.ram[0x2D] = 0
    m.call(0xCF74)
    if m.ram[0x0401] != song:
        raise R.Halt(f"song ${song:02X} did not start")
    m.control = control
    m.chr = list(chr_banks)
    m.ram[0x23], m.ram[0x25] = chr_banks
    m.ram[0x2C] = m.ram[0x2D] = 0
    m.ram[0x04E4] = m.ram[0x04E6] = 0
    m.ram[0x047A] = m.ram[0x0190] = m.ram[0x01B5] = m.ram[0x32] = 0
    m.ram[0xAD], m.ram[0x20], m.ram[0x22] = 0x1E, 0x90, control
    m.ctrl, m.mask = 0x90, 0x1E
    for log in (m.apu, m.queue, m.ticks, m.tick_marks, m.log):
        log.clear()
    return m


def plant(m, entry):
    b, ram = entry.board, m.ram
    ram[0x04EF], ram[0x04F0] = entry.teams
    ram[HALVES] = b.halves
    ram[LINE:LINE + LINE_BYTES] = b.line
    ram[RUNS], ram[RUNS + 1] = b.runs
    for k, pair in enumerate(b.stats):
        ram[STATS + 2 * k], ram[STATS + 2 * k + 1] = pair
    ram[0x04D0], ram[0x07EE], ram[0xA7], ram[0x04E2] = entry.over, entry.quiet, entry.attract, entry.championship
    ram[0x04EB], ram[0x04EC] = entry.cpu
    ram[0x04ED] = b.halves & 1                  # the side at bat
    ram[0x04EE] = ram[0x04ED] ^ 1
    ram[0x0402], ram[0x04E9], ram[0x31] = 0xFF, 0, 0
    ram[0x8D:0x97] = bytes(10)                  # no button held or pressed before the board
    m.wram[0x1700:0x1740] = bytes(range(32)) + b"\xFF" * 32
    ram[0x07FC], ram[0x07EF], ram[0x07ED] = 0, 0x32, 1
    for address, value in entry.pokes:
        ram[address] = value


def enter(rom, entry, pads=(None, None), song=0x02, lead=0):
    """A machine about to run scene $0A for `entry`; `lead` shifts the vblank phase by that many cycles."""
    m = machine(rom, pads, song)
    plant(m, entry)
    m.map_bank(4)
    m.ram[SCENE] = 0x0A
    for byte in (MAIN_LOOP >> 8, MAIN_LOOP & 0xFF):
        m.ram[0x100 + m.mpu.sp] = byte
        m.mpu.sp = (m.mpu.sp - 1) & 0xFF
    m.mpu.pc = ENTRY
    m.next_vblank += lead
    return m


def outside_nmi(m, pc, bank=4):
    return m.mpu.pc == pc and m.prg == bank and not m.nmi_depth


def draw(rom, entry, **kwargs):
    """Run until the writer is done ($B3F2, before $2C is released): VRAM and the OAM buffer hold the board."""
    m = enter(rom, entry, **kwargs)
    m.run(lambda mm: outside_nmi(mm, DRAWN), limit=5_000_000)
    return m


def show(rom, entry, settle=1, **kwargs):
    """Run until scene $0B shows the board, then `settle` frames, so palette, CHR and OAM have landed."""
    m = enter(rom, entry, **kwargs)
    start = m.frame
    m.run(lambda mm: (mm.ram[SCENE] == 0x0B and R.shown(mm)) or mm.frame - start > 400, limit=60_000_000)
    if m.ram[SCENE] != 0x0B or not R.shown(m):
        raise AssertionError(f"the board never showed: scene ${m.ram[SCENE]:02X}, pc ${m.mpu.pc:04X}")
    m.frames(settle)
    return m


def oam_buffer(m):
    return bytes(m.ram[0x0200:0x0300])


def timeline(rom, entry, frames, pads=(None, None), song=0x02, lead=0):
    """Frame-stamped behavior from scene $0A entry: per frame the scene, PRG bank (none while scene $0A
    draws: stock maps bank 2 there), song and rendering; every scene write, sound request and APU write."""
    m = enter(rom, entry, pads, song, lead)
    sampled = []
    for _ in range(frames):
        m.frames(1)
        drawing = m.ram[SCENE] == 0x0A
        sampled.append((m.ram[SCENE], None if drawing else m.prg, m.ram[0x0401], bool(m.mask & 0x18)))
    scenes = [(frame, new) for frame, address, _, new, _, _ in m.log if address == SCENE]
    return {"frames": sampled, "scenes": scenes, "requests": list(m.queue), "apu": list(m.apu)}


COSTS = {0x10: 2, 0x18: 2, 0x20: 6, 0x24: 3, 0x29: 2, 0x38: 2, 0x4A: 2, 0x4C: 3, 0x60: 6, 0x65: 3, 0x68: 4,
         0x6C: 5, 0x85: 3, 0x88: 2, 0x8D: 4, 0x98: 2, 0x9D: 5, 0xA0: 2, 0xA2: 2, 0xA4: 3, 0xA5: 3, 0xA6: 3,
         0xA8: 2, 0xA9: 2, 0xAA: 2, 0xB1: 5, 0xB9: 4, 0xBD: 4, 0xC0: 2, 0xC6: 5, 0xC8: 2, 0xC9: 2, 0xCA: 2,
         0xD0: 2, 0xE0: 2, 0xE6: 5, 0xE8: 2, 0xEA: 2, 0xF0: 2}
BRANCHES = {0x10, 0xD0, 0xF0}


def crossed(a, b):
    return (a & 0xFF00) != (b & 0xFF00)


def interval(rom, entry, lead=0, quiet=False):
    """CPU cycles from the second $C260 vblank wait's return (its PLA) to the stock writer at $B3D4,
    NMI cycles excluded, and the waits taken before it. With `quiet`, NMIs are masked from that PLA on
    and `independent` adds the cost of every instruction from a hand-written table plus page-crossing
    and taken-branch penalties, without consulting the model's own cycle counts."""
    m = enter(rom, entry, lead=lead)
    waits, start, nmi, independent = 0, None, 0, 0
    for _ in range(3_000_000):
        pc, depth = m.mpu.pc, len(m.nmi_depth)
        if not depth:
            if pc == WAIT_EXIT:
                waits += 1
            if pc == WAIT_RETURN and waits == 2 and start is None:
                start = m.mpu.processorCycles
                if quiet:
                    m.ctrl &= 0x7F
                    m.pending_nmi = False
            if outside_nmi(m, WRITER):
                cycles = None if start is None else m.mpu.processorCycles - start - nmi
                return {"waits": waits, "cycles": cycles, "nmi_cycles": nmi,
                        "independent": independent if quiet else None}
        expected = None
        if quiet and start is not None:
            opcode = m.rom_byte(pc)
            expected = COSTS[opcode]
            if opcode in (0xB9, 0xBD):
                base = m.rom_byte(pc + 1) | m.rom_byte(pc + 2) << 8
                expected += crossed(base, base + (m.mpu.y if opcode == 0xB9 else m.mpu.x))
            elif opcode == 0xB1:
                zp = m.rom_byte(pc + 1)
                base = m.ram[zp] | m.ram[(zp + 1) & 0xFF] << 8
                expected += crossed(base, base + m.mpu.y)
        before = m.mpu.processorCycles
        m.step()
        if expected is not None:
            if m.rom_byte(pc) in BRANCHES and m.mpu.pc != (pc + 2) & 0xFFFF:
                expected += 1 + crossed(pc + 2, m.mpu.pc)
            independent += expected
        if start is not None and (m.nmi_depth or len(m.nmi_depth) != depth):
            nmi += m.mpu.processorCycles - before
    raise AssertionError("the draw never reached the writer at $B3D4")


def with_nmi(rom, entry, pc, bank=4, settle=3):
    """`show` with one NMI forced just before the first non-NMI execution of `pc` in `bank`; did it fire."""
    m = enter(rom, entry)
    fired = []

    def hook(mm):
        if not fired and mm.prg == bank and not mm.nmi_depth:
            mm.pending_nmi = True
            fired.append(mm.frame)
    m.on_pc[pc] = hook
    start = m.frame
    m.run(lambda mm: (mm.ram[SCENE] == 0x0B and R.shown(mm)) or mm.frame - start > 400, limit=60_000_000)
    m.frames(settle)
    return m, bool(fired)
