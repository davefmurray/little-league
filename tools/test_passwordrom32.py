#!/usr/bin/env python3
"""Execute password hooks across MMC1 bank changes and bracket view transitions.

    .venv/bin/python tools/test_passwordrom32.py build/control32.nes --candidate build/password32.nes
"""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

from py65.devices.mpu6502 import MPU

import password32
from build_passwordrom32 import build_rom, off, patches, protect_output
from test_password32 import stock_cases, stock_encode

OUTPUT_SHA256 = "978abc4227eac24d0c779ea3fbbdfdc42c89ca0a1fcce350cff6db44501da34a"

class Memory(list):
    def __init__(self, rom, bank, buttons=lambda poll: 0):
        super().__init__([0] * 0x10000)
        self.rom = rom
        self.bank = bank
        self.serial = 0
        self.bits = 0
        self.buttons = buttons
        self.polls = 0
        self.pad = 0
        self.writes = []
        super().__setitem__(slice(0xC000, 0x10000), rom[off(15, 0xC000):off(15, 0x10000)])
        self.map_bank(bank)

    def map_bank(self, bank):
        self.bank = bank & 15
        super().__setitem__(slice(0x8000, 0xC000),
                            self.rom[off(self.bank, 0x8000):off(self.bank, 0xC000)])

    def __getitem__(self, address):
        if address == 0x2002:
            return 0x80
        if address == 0x4016:
            value = 0x40 | ((self.pad >> 7) & 1)
            self.pad = (self.pad << 1) & 255
            return value
        return super().__getitem__(address)

    def __setitem__(self, address, value):
        if isinstance(address, int):
            if address >= 0x8000:
                if value & 0x80:
                    self.serial = self.bits = 0
                else:
                    self.serial |= (value & 1) << self.bits
                    self.bits += 1
                    if self.bits == 5:
                        if address >= 0xE000:
                            self.map_bank(self.serial)
                        self.serial = self.bits = 0
                return
            if address == 0x4016 and value & 1:
                self.polls += 1
                self.pad = self.buttons(self.polls)
            self.writes.append((address, value))
        super().__setitem__(address, value)


def machine(rom, bank, buttons=lambda poll: 0):
    cpu = MPU(memory=Memory(rom, bank, buttons))
    cpu.sp = 0xFD
    cpu.memory[0x27] = bank
    return cpu


def run(cpu, entry, bank, stop, limit=50000):
    cpu.pc = entry
    for _ in range(limit):
        cpu.step()
        if cpu.pc == stop and cpu.memory.bank == bank:
            return
    raise AssertionError((hex(entry), hex(cpu.pc), cpu.memory.bank))


def install_state(memory, state):
    seed, played, results, mask = state
    memory[0x7700:0x773F] = [0xFF if value is None else value for value in
                            password32.advance(password32.seed_order(seed), played, results)]
    memory[0x07FC] = played
    memory[0x074B:0x074D] = mask.to_bytes(4, "little")[:2]
    memory[0x07F1:0x07F3] = mask.to_bytes(4, "little")[2:]
    memory[0x07ED] = 1
    memory[0x07EF] = 0x32


def test_round_trips(rom):
    count = 0
    for seed in (0, 15, 16, 31):
        for played in (0, 1, 15, 16, 23, 27, 29, 30, 31):
            state = (seed, played, 0x55555555 & ((1 << played) - 1), 0xFFFFFFFF ^ (1 << seed))
            cpu = machine(rom, 5)
            install_state(cpu.memory, state)
            stack = cpu.sp
            run(cpu, 0x9FF5, 5, 0x9FF8)
            assert cpu.sp == stack and cpu.memory[0x27] == 5
            encoded = bytes(cpu.memory[0x0643:0x065D])
            assert encoded == password32.display(password32.encode(*state)), state
            restored = machine(rom, 1)
            restored.memory[0x0643:0x0659] = password32.encode(*state).encode()
            restored.memory[0x07F0] = 1
            run(restored, 0xA584, 11, 0x8000)
            assert restored.memory[0x27] == 11 and restored.memory[0x2000] == 0
            assert restored.memory[0x7700:0x773F] == cpu.memory[0x7700:0x773F]
            assert restored.memory[0x07FC] == played
            assert restored.memory[0x074B:0x074D] == cpu.memory[0x074B:0x074D]
            assert restored.memory[0x07F1:0x07F3] == cpu.memory[0x07F1:0x07F3]
            assert restored.memory[0x07EF] == 0x32 and restored.memory[0x07ED] == 1
            assert restored.memory[0x07F0] == 0
            count += 1
    print(f"hooks: {count} display/decode/restore round trips across real MMC1 bank changes")


def test_invalid(rom):
    valid = password32.encode(31, 15, 1234, 0x7FFFFFFF)
    passwords = ["!" * 22, valid[:-1] + ("1" if valid[-1] != "1" else "A")]
    passwords.extend(stock_encode(payload, played) for payload, played in stock_cases())
    for text in passwords:
        cpu = machine(rom, 1)
        install_state(cpu.memory, (16, 2, 3, 0xFFFEFFFF))
        before = cpu.memory[0x7700:0x7740]
        mask = cpu.memory[0x074B:0x074D] + cpu.memory[0x07F1:0x07F3]
        cpu.memory[0x0643:0x0659] = text.encode()
        stack = cpu.sp
        run(cpu, 0xA584, 1, 0xA587)
        assert cpu.sp == stack and cpu.memory[0x27] == 1
        assert cpu.memory[0x07ED] == 0 and cpu.memory[0x07FC] == 2
        assert cpu.memory[0x7700:0x7740] == before
        assert cpu.memory[0x074B:0x074D] + cpu.memory[0x07F1:0x07F3] == mask
    print(f"invalid input: {len(passwords)} malformed, corrupt and stock passwords return to the stock error path")


def test_mode_guards(rom):
    for active, marker in ((0, 0), (0, 0x32), (1, 0), (1, 0x32)):
        cpu = machine(rom, 5)
        cpu.memory[0x07ED], cpu.memory[0x07EF] = active, marker
        run(cpu, 0x9FF5, 12 if active and marker == 0x32 else 5,
            0x8003 if active and marker == 0x32 else 0xA036)
        cpu = machine(rom, 1)
        cpu.memory[0x07ED], cpu.memory[0x07EF] = active, marker
        cpu.stPushWord(0x05FF)
        run(cpu, 0x951C, 11 if active and marker == 0x32 else 1,
            0x8000 if active and marker == 0x32 else 0x0600)
        if active and marker == 0x32:
            assert cpu.memory[0x07F0] == 1 and cpu.memory[0x2000] == 0
        else:
            assert cpu.memory[0x047B:0x047D] == [0x13, 0]
        cpu = machine(rom, 1)
        cpu.memory[0x07ED], cpu.memory[0x07EF] = active, marker
        cpu.memory[0x07F0] = 1
        cpu.stPushWord(0x05FF)
        run(cpu, 0x94F8, 11 if active and marker == 0x32 else 1,
            0x8000 if active and marker == 0x32 else 0x0600)
        if active and marker == 0x32:
            assert cpu.memory[0x07F0] == 0 and cpu.memory[0x2000] == 0
        elif active:
            assert cpu.memory[0x047B:0x047D] == [0x13, 2]
        else:
            assert cpu.memory[0x047B] == 0x18
    print("mode guards: display, LIST and CONTINUE require both active-series state and the 32-team marker")


def test_view(rom):
    for played, view in ((0, 1), (15, 1), (30, 1), (31, 0), (32, 0), (255, 0)):
        for exit_button in (0x80, 0x40):
            buttons = lambda poll: 0x80 if poll < 5 else (0 if poll < 8 or poll >= 11 else exit_button)
            cpu = machine(rom, 11, buttons)
            cpu.memory[0x07FC], cpu.memory[0x07F0] = played, view
            run(cpu, 0x8680, 11, 0xFF90)
            assert cpu.memory.polls == 11
            assert cpu.memory[0x047B] == 6 and cpu.memory[0x047D] == 0 and cpu.memory[0x07F0] == 0
            assert cpu.memory[0x07FC] == played
            assert not any(0x7700 <= address < 0x7740 for address, _ in cpu.memory.writes)
    for played in (0, 1, 30):
        cpu = machine(rom, 11)
        cpu.memory[0x07FC] = played
        run(cpu, 0x8680, 11, 0x8100)
    print("view: held A ignored, fresh A/B exits after release, completed tournaments cannot launch")


def test_builder(base, rom):
    allowed = set()
    for bank, address, expected, code in patches():
        start = off(bank, address)
        allowed.update(range(start, start + len(code)))
    changed = {index for index, (old, new) in enumerate(zip(base, rom)) if old != new}
    assert changed <= allowed and len(rom) == len(base)
    for bank, first, last in ((1, 0xA8A2, 0xA96C), (5, 0xA036, 0xA146)):
        assert rom[off(bank, first):off(bank, last)] == base[off(bank, first):off(bank, last)]
    for offset in (0, off(1, 0xA584), off(15, 0xFCC0), off(12, 0x8000)):
        corrupt = bytearray(base)
        corrupt[offset] ^= 1
        try:
            build_rom(corrupt)
        except ValueError:
            pass
        else:
            raise AssertionError("damaged input accepted")
    print(f"ownership: {len(changed)} changed bytes inside guarded ranges; stock codecs preserved")


def test_output_guards(source):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        original = directory / "input.nes"
        original.write_bytes(source.read_bytes())
        symlink, hardlink = directory / "symlink.nes", directory / "hardlink.nes"
        symlink.symlink_to(original)
        os.link(original, hardlink)
        targets = [original, symlink, hardlink, Path(__file__).with_name("password32_6502.py")]
        for name in ("control32", "results32", "roles32", "teamtables32"):
            copy = directory / f"copy-{name}.nes"
            copy.write_bytes((source.parent / f"{name}.nes").read_bytes())
            targets.append(copy)
        stock = Path(__file__).resolve().parent.parent / "Little League Baseball - Championship Series (USA).nes"
        targets.append(stock)
        for target in targets:
            before = target.read_bytes()
            try:
                protect_output(original, target)
            except ValueError:
                pass
            else:
                raise AssertionError(f"protected output accepted: {target}")
            assert target.read_bytes() == before
    print("output guards: source code, input, hard/symbolic aliases and copied earlier ROMs are protected")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("--candidate", type=Path)
    args = ap.parse_args()
    base = args.rom.read_bytes()
    before = hashlib.sha256(base).digest()
    rom = build_rom(base)
    assert hashlib.sha256(rom).hexdigest() == OUTPUT_SHA256
    if args.candidate:
        assert args.candidate.read_bytes() == rom
    test_round_trips(rom)
    test_invalid(rom)
    test_mode_guards(rom)
    test_view(rom)
    test_builder(base, rom)
    test_output_guards(args.rom)
    assert hashlib.sha256(base).digest() == before
    print(f"password32 SHA256 {hashlib.sha256(rom).hexdigest()}")


if __name__ == "__main__":
    main()
