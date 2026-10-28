#!/usr/bin/env python3
"""Run the assembled menuart32 ROM on a CPU/PPU model and render what it draws.

    .venv/bin/python tools/render_menu32.py build/menuart32.nes --out build/menu32-rom

The model executes real ROM bytes with py65: 2 KB RAM, PRG RAM, an MMC1 with its
serial port, a PPU with nametables, palette and OAM, OAM DMA with its 513/514
cycle stall, NTSC vblank timing with NMI, the serial controller port and APU
write logging. It is not a picture-accurate PPU: rendered PNGs are composed from
the VRAM the ROM wrote, the same way tools/menu32_convert.py renders its oracle.
The test suite (tools/test_menuart32.py) uses this machine for every runtime check.
"""
import argparse
from pathlib import Path
import sys

from py65.devices.mpu6502 import MPU

sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu32_convert as convert  # noqa: E402

FRAME = 29780.5            # NTSC CPU cycles per frame
VBLANK = 341 * 20 / 3      # 2273.3 CPU cycles from the vblank flag to the pre-render line
HEADER = 16
A, B, SELECT, START, UP, DOWN, LEFT, RIGHT = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01
RAM_FILL = bytes((a * 29 + 0x53) & 255 for a in range(0x800))
WRAM_FILL = bytes((a * 13 + 0x91) & 255 for a in range(0x2000))
STOP = 0x0000              # a never-executed address used as an RTS target


class Halt(Exception):
    pass


class Machine:
    """One NES-shaped CPU bus. `pad(frame)` returns the buttons held during a frame."""

    def __init__(self, rom, pad=None):
        self.rom = rom
        self.nprg = rom[4]
        self.chr_rom = rom[HEADER + self.nprg * 0x4000:]
        self.ram = bytearray(RAM_FILL)
        self.wram = bytearray(WRAM_FILL)
        self.shift = self.count = 0
        self.control, self.chr, self.prg = 0x1E, [0, 1], 0
        self.ctrl = self.mask = 0
        self.blanked = False
        self.shows = []            # frames where rendering came back on after a blank
        self.vblank = False
        self.w = self.t = self.v = self.buffer = 0
        self.vram = bytearray(0x800)
        self.palette = bytearray(32)
        self.oam = bytearray(256)
        self.oam_addr = 0
        self.pad = pad or (lambda frame: 0)
        self.strobe = False
        self.pad_bits = 0
        self.frame = 0
        self.next_vblank = FRAME
        self.vblank_start = None
        self.pending_nmi = False
        self.stall = 0
        self.start = 0
        self.length = 0
        self.pc = 0                # address of the instruction being executed
        self.mpu = MPU(memory=self)
        self.mpu.sp = 0xFD
        self.apu = []              # (frame, address, value)
        self.ppu_writes = []       # (cycle, register, value, rendering on, offset into vblank or None)
        self.vram_late = []        # PPU data/scroll/mask writes made with rendering on outside vblank
        self.vblank_work = {}      # frame -> cycles from vblank start to the last PPU write of that vblank
        self.wram_access = []      # (R/W, address, chr0, chr1, pc)
        self.mapper = []           # (pc, register, value) completed MMC1 loads
        self.partial = []          # pcs that left a partial MMC1 sequence when the NMI fired
        self.reads = []            # optional ROM read tracing
        self.trace_reads = None    # (bank, lo, hi) to record
        self.zp_writes = []        # optional: writes to $00-$0F while a PC range runs
        self.watch_zp = None
        self.nmis = 0
        self.nmi_depth = []
        self.nmi_menu = []         # per nested NMI: taken while a menu held $2C
        self.ticks = []            # frame of each foreground $CF7B entry
        self.tick_marks = []       # len(self.apu) when each foreground tick began
        self.nmi_ticks = 0         # audio ticks run by an NMI taken in menu mode ($2C set)
        self.queue = []            # (frame, value) commands written into $0470-$0477

    def __len__(self):
        return 0x10000

    def prg_bank(self, addr):
        mode = (self.control >> 2) & 3
        if mode < 2:
            return (self.prg & 0x0E) | (1 if addr >= 0xC000 else 0)
        if mode == 2:
            return 0 if addr < 0xC000 else self.prg & 0x0F
        return self.prg & 0x0F if addr < 0xC000 else self.nprg - 1

    def __getitem__(self, a):
        if isinstance(a, slice):
            return [self[i] for i in range(*a.indices(0x10000))]
        if a < 0x2000:
            return self.ram[a & 0x7FF]
        if a < 0x4000:
            return self.ppu_read(0x2000 + (a & 7))
        if a == 0x4016:
            return self.pad_read()
        if a < 0x6000:
            return 0x40
        if a < 0x8000:
            self.wram_access.append(("R", a, self.chr[0], self.chr[1], self.pc))
            return self.wram[a - 0x6000]
        bank = self.prg_bank(a)
        if self.trace_reads and bank == self.trace_reads[0] and self.trace_reads[1] <= a < self.trace_reads[2]:
            self.reads.append((a, self.pc))
        return self.rom[HEADER + bank * 0x4000 + (a & 0x3FFF)]

    def __setitem__(self, a, v):
        v &= 0xFF
        if a < 0x2000:
            if a < 0x10 and self.watch_zp and self.watch_zp(self):
                self.zp_writes.append((a, self.pc, self.prg))
            if 0x0470 <= a < 0x0478 and v != 0xFF:
                self.queue.append((self.frame, v))
            self.ram[a & 0x7FF] = v
            return
        if a < 0x4000:
            self.ppu_write(0x2000 + (a & 7), v)
            return
        if a == 0x4014:
            self.oam_dma(v)
            return
        if a == 0x4016:
            self.strobe = bool(v & 1)
            if self.strobe:
                self.pad_bits = self.pad(self.frame)
            return
        if a < 0x4018:
            self.apu.append((self.frame, a, v))
            return
        if a < 0x6000:
            return
        if a < 0x8000:
            self.wram_access.append(("W", a, self.chr[0], self.chr[1], self.pc))
            self.wram[a - 0x6000] = v
            return
        if v & 0x80:
            self.shift = self.count = 0
            self.control |= 0x0C
            return
        self.shift |= (v & 1) << self.count
        self.count += 1
        if self.count == 5:
            register = (a >> 13) & 3
            if register == 0:
                self.control = self.shift
            elif register == 3:
                self.prg = self.shift
            else:
                self.chr[register - 1] = self.shift
            self.mapper.append((self.pc, register, self.shift))
            self.shift = self.count = 0

    def rendering(self):
        return bool(self.mask & 0x18)

    def write_cycle(self):
        return self.start + self.length - 1

    def in_vblank(self, cycle):
        return self.vblank_start is not None and 0 <= cycle - self.vblank_start < VBLANK

    def log_ppu(self, register, value):
        cycle = self.write_cycle()
        offset = cycle - self.vblank_start if self.vblank_start is not None else None
        on = self.rendering()
        self.ppu_writes.append((cycle, register, value, on, offset))
        if on and register in (0x2005, 0x2006, 0x2007, 0x2001, 0x2004, 0x4014):
            if not self.in_vblank(cycle):
                self.vram_late.append((cycle, register, value, offset, self.pc))
            else:
                self.vblank_work[self.frame] = max(self.vblank_work.get(self.frame, 0), offset)

    def mirror(self, addr):
        addr &= 0x0FFF
        table, offset = addr >> 10, addr & 0x3FF
        mode = self.control & 3
        page = (0, 1, table & 1, table >> 1)[mode]
        return page * 0x400 + offset

    def vram_write(self, addr, v):
        addr &= 0x3FFF
        if addr < 0x2000:
            return
        if addr < 0x3F00:
            self.vram[self.mirror(addr)] = v
            return
        index = addr & 0x1F
        if index & 0x13 == 0x10:
            index &= 0x0F
        self.palette[index] = v & 0x3F

    def vram_read(self, addr):
        addr &= 0x3FFF
        if addr < 0x2000:
            return self.pattern(addr)
        if addr < 0x3F00:
            return self.vram[self.mirror(addr)]
        index = addr & 0x1F
        if index & 0x13 == 0x10:
            index &= 0x0F
        return self.palette[index]

    def chr_bank(self, half):
        if self.control & 0x10:
            return self.chr[half]
        return (self.chr[0] & 0x1E) | half

    def pattern(self, addr):
        return self.chr_rom[self.chr_bank(addr >> 12) * 0x1000 + (addr & 0xFFF)]

    def ppu_read(self, reg):
        if reg == 0x2002:
            value = (0x80 if self.vblank else 0) | 0x10
            self.vblank = False
            self.w = 0
            return value
        if reg == 0x2007:
            value = self.buffer
            self.buffer = self.vram_read(self.v)
            if (self.v & 0x3FFF) >= 0x3F00:
                value = self.buffer
            self.v = (self.v + (32 if self.ctrl & 4 else 1)) & 0x7FFF
            return value
        return 0

    def ppu_write(self, reg, v):
        self.log_ppu(reg, v)
        if reg == 0x2000:
            if v & 0x80 and not self.ctrl & 0x80 and self.vblank:
                self.pending_nmi = True
            self.ctrl = v
            self.t = (self.t & ~0x0C00) | ((v & 3) << 10)
        elif reg == 0x2001:
            if not v & 0x18:
                self.blanked = True
            elif self.blanked:
                self.blanked = False
                self.shows.append(self.frame)
            self.mask = v
        elif reg == 0x2003:
            self.oam_addr = v
        elif reg == 0x2004:
            self.oam[self.oam_addr] = v
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        elif reg == 0x2005:
            if self.w == 0:
                self.t = (self.t & ~0x001F) | (v >> 3)
            else:
                self.t = (self.t & ~0x73E0) | ((v & 7) << 12) | ((v >> 3) << 5)
            self.w ^= 1
        elif reg == 0x2006:
            if self.w == 0:
                self.t = (self.t & 0x00FF) | ((v & 0x3F) << 8)
            else:
                self.t = (self.t & 0x7F00) | v
                self.v = self.t
            self.w ^= 1
        elif reg == 0x2007:
            self.vram_write(self.v, v)
            self.v = (self.v + (32 if self.ctrl & 4 else 1)) & 0x7FFF

    def oam_dma(self, page):
        self.log_ppu(0x4014, page)
        for i in range(256):
            self.oam[(self.oam_addr + i) & 0xFF] = self[(page << 8) | i]
        self.stall += 513 + (self.write_cycle() & 1)

    def pad_read(self):
        if self.strobe:
            self.pad_bits = self.pad(self.frame)
            return 0x40 | (self.pad_bits >> 7)
        bit = (self.pad_bits >> 7) & 1
        self.pad_bits = ((self.pad_bits << 1) | 1) & 0xFF
        return 0x40 | bit

    def step(self):
        m = self.mpu
        if self.pending_nmi:
            self.pending_nmi = False
            if self.count:
                self.partial.append(m.pc)
            self.nmis += 1
            self.nmi_depth.append(m.sp)
            self.nmi_menu.append(self.ram[0x2C] != 0)
            m.nmi()
        opcode = self[m.pc]
        self.pc = m.pc
        self.start, self.length = m.processorCycles, m.cycletime[opcode]
        if m.pc == 0xCF7B:
            if self.nmi_depth:
                self.nmi_ticks += self.nmi_menu[-1]
            else:
                self.ticks.append(self.frame)
                self.tick_marks.append(len(self.apu))
        m.step()
        if opcode == 0x40 and self.nmi_depth and m.sp == self.nmi_depth[-1]:
            self.nmi_depth.pop()
            self.nmi_menu.pop()
        if self.stall:
            m.processorCycles += self.stall
            self.stall = 0
        now = m.processorCycles
        if self.vblank and now - self.vblank_start >= VBLANK:
            self.vblank = False
        if now >= self.next_vblank:
            self.vblank_start = self.next_vblank
            self.next_vblank += FRAME
            self.frame += 1
            self.vblank = True
            if self.ctrl & 0x80:
                self.pending_nmi = True

    def run(self, until, limit=20_000_000):
        """Step until `until(self)` is true; Halt if the CPU leaves sane code."""
        for _ in range(limit):
            if until(self):
                return
            if self.mpu.pc == STOP:
                raise Halt("returned to the stop address")
            self.step()
        raise Halt(f"no stop after {limit} instructions, pc ${self.mpu.pc:04X}")

    def call(self, addr, a=None, limit=2_000_000):
        m = self.mpu
        ret = (STOP - 1) & 0xFFFF
        self.ram[0x100 + m.sp] = ret >> 8
        m.sp = (m.sp - 1) & 0xFF
        self.ram[0x100 + m.sp] = ret & 0xFF
        m.sp = (m.sp - 1) & 0xFF
        if a is not None:
            m.a = a
        m.pc = addr
        for _ in range(limit):
            if m.pc == STOP:
                return
            self.step()
        raise Halt(f"call ${addr:04X} did not return")

    def frames(self, count):
        target = self.frame + count
        self.run(lambda machine: machine.frame >= target)

    def map_bank(self, bank):
        """What $C14E does, without executing it."""
        self.prg = bank
        self.ram[0x27] = bank

    def palette32(self):
        """All 32 palette entries as the CPU reads them ($3F10/14/18/1C mirror $3F00/04/08/0C)."""
        return bytes(self.palette[i & 0x0F if i & 0x13 == 0x10 else i] for i in range(32))

    def nametable(self):
        return bytes(self.vram[self.mirror(0x2000 + i)] for i in range(0x400))

    def picture(self, scale=1):
        nt = self.nametable()
        half = 1 if self.ctrl & 0x10 else 0
        bank = self.chr_bank(half)
        chr_data = self.chr_rom[bank * 0x1000:bank * 0x1000 + 0x1000]
        sprite_bank = self.chr_bank(1 if self.ctrl & 0x08 else 0)
        oam = [tuple(self.oam[i:i + 4]) for i in range(0, 256, 4)]
        if sprite_bank != bank:
            raise ValueError("sprites and background use different pattern tables")
        image = convert.render(chr_data, nt[:960], nt[960:], self.palette32(),
                               [(y, tile, attr, x) for y, tile, attr, x in oam], scale)
        return image



def stock_machine(rom, pad=None, control=0x0F, chr_banks=(0x12, 0x16), song=0x06):
    """A machine in a plausible mid-game state: sound engine running `song`, gameplay CHR,
    a non-menu MMC1 control mode, guards clear and RAM holding unrelated garbage."""
    m = Machine(rom, pad)
    m.mpu.sp = 0xEF
    m.ram[0x04EA] = 0              # sound not muted, as after the reset path $CD20
    m.call(0xCF59)
    m.call(0xC249, a=song)
    m.ram[0x2D] = 0
    m.call(0xCF74)
    if m.ram[0x0401] != song:
        raise Halt(f"song ${song:02X} did not start")
    m.control = control
    m.chr = list(chr_banks)
    m.ram[0x23], m.ram[0x25] = chr_banks
    m.ram[0x2C] = m.ram[0x2D] = 0
    m.ram[0x04E4] = m.ram[0x04E6] = 0
    # A scene without raster effects or pending NMI work: no sprite-0 wait ($047A),
    # no palette/OAM jobs ($0190, $01B5) and an empty display list ($32).
    m.ram[0x047A] = m.ram[0x0190] = m.ram[0x01B5] = m.ram[0x32] = 0
    m.ram[0xAD] = 0x1E
    m.ram[0x20] = 0x90
    m.ram[0x22] = control
    m.ctrl, m.mask = 0x90, 0x1E
    m.apu.clear()
    m.queue.clear()
    m.ticks.clear()
    m.tick_marks.clear()
    return m


def at(*pcs):
    targets = set(pcs)
    return lambda machine: machine.mpu.pc in targets


def press_script(steps, settle=4, hold=2, gap=2):
    """A pad function pressing each button mask in `steps` once, after `settle` frames."""
    timeline = {}
    frame = settle
    for buttons in steps:
        for f in range(frame, frame + hold):
            timeline[f] = buttons
        frame += hold + gap
    return (lambda f: timeline.get(f, 0)), frame


def selector_steps(team):
    """New layout: rows are pages; Down per row, Right per column, then A."""
    return [DOWN] * (team >> 3) + [RIGHT] * (team & 7)


def old_selector_steps(team):
    """Old four-page layout: Down for the lower row of a page, Right four per page and per column."""
    page, cursor = team >> 3, team & 7
    return ([DOWN] if cursor >= 4 else []) + [RIGHT] * (4 * page + (cursor & 3))


def enter_selector(rom, pad, control=0x0F):
    """Scene $12 runs bank 5 $98B9: JSR $FF20 maps bank 10 and jumps to $8000."""
    m = stock_machine(rom, pad, control=control)
    m.map_bank(5)
    m.mpu.pc = 0x98B9
    return m


def heap_after(selected, played, winners=None):
    """WRAM $7700-$773F after a new series with `selected` and `played` decided matches."""
    heap = convert.sample_heap(selected, played) if winners is None else winners
    return bytes(heap) + b"\xFF"


def enter_bracket(rom, path, pad, heap, played, control=0x1F, view=None):
    """Put the machine at one of the five stock routes into bank 11 $8000."""
    m = stock_machine(rom, pad, control=control)
    m.wram[0x1700:0x1700 + len(heap)] = heap
    m.ram[0x07FC] = played
    m.ram[0x07EF], m.ram[0x07ED] = 0x32, 0x01
    if path == "list":
        m.map_bank(1)
        m.mpu.pc = 0xFEA0
    elif path == "continue":
        m.map_bank(1)
        m.ram[0x07F0] = 0
        m.mpu.pc = 0xFEB1
    elif path == "result":
        # Scene 11 with a finished game: $83A0 records the winner of match `played` and draws.
        m.map_bank(4)
        m.ram[0x04E2], m.ram[0x04D0] = 1, 1
        m.ram[0x048B], m.ram[0x048C] = 5, 2
        m.ram[0x04EF], m.ram[0x04F0] = heap[2 * played], heap[2 * played + 1]
        m.ram[0x07F0] = 0
        m.mpu.pc = 0xFFC0
    elif path == "password":
        # $FCC0 accepted a code: restore from $0628-$0631, then draw.
        m.map_bank(12)
        m.ram[0x0628], m.ram[0x0629] = heap[0], played
        bits = 0
        for i in range(played):
            bits |= (heap[32 + i] == heap[2 * i + 1]) << i
        m.ram[0x062A:0x062E] = bits.to_bytes(4, "little")
        m.ram[0x062E:0x0632] = bytes([0xFE, 0xFF, 0xFF, 0xFF])
        m.mpu.pc = 0xFCD5
    else:
        raise ValueError(path)
    if view is not None:
        m.ram[0x07F0] = view
    return m


def shown(m):
    """The screen came back on after the entry blanked it (old or new ROM alike)."""
    return bool(m.shows) and bool(m.mask & 0x18)


def settle(m, frames=12):
    """Run until the bracket or selector loop has drawn and shown its screen."""
    m.run(shown)
    m.frames(frames)



def render_samples(rom, out, scale=1):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for team in (0, 31):
        pad, _ = press_script(selector_steps(team))
        m = enter_selector(rom, pad)
        settle(m, 8 + 4 * len(selector_steps(team)) + 10)
        path = out / f"selector-{team:02d}.png"
        m.picture(scale).save(path)
        written.append(path)
    for played in (0, 15, 16, 23, 24, 28, 30, 31):
        m = enter_bracket(rom, "continue" if played < 31 else "list", None, heap_after(31, played), played)
        settle(m)
        m.run(lambda machine: (machine.ram[0x07F3] & 0x1F) == 1)
        m.frames(1)
        path = out / f"bracket-{played:02d}.png"
        m.picture(scale).save(path)
        written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()
    for path in render_samples(args.rom.read_bytes(), args.out, args.scale):
        print(f"rendered {path}")


if __name__ == "__main__":
    main()
