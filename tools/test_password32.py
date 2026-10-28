#!/usr/bin/env python3
"""Test v1 host and 6502 codecs against a frozen results32 ROM.

    .venv/bin/python tools/test_password32.py build/results32.nes

The ROM must have SHA-256 9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b.
CPU calls execute real instructions without PPU, NMI, controller or mapper
emulation. The stock codec and $8200 seeder come from that ROM unchanged.
"""
import argparse
import hashlib
from pathlib import Path
import random
import subprocess
import sys
import unittest

from py65.devices.mpu6502 import MPU

import password32 as model
import password32_6502 as asm
from build_bank11 import assemble

ROM_SHA256 = "9a3a5d4fe17f69bfe926af07de9a6309240eb5c60d693be8ce0a966b29454d9b"
FRAME_CYCLES = 29781
ROM = None
MAX_CYCLES = {"decode": 0, "encode": 0, "restore": 0}
CPU_CASES = {"decode": 0, "encode": 0, "restore": 0}
SCRATCH_WRITES = set(range(5)) | set(range(asm.PAYLOAD, asm.PAYLOAD + 14)) | set(range(0x01F0, 0x0200))
RESTORE_WRITES = (set(range(asm.SLOTS, asm.SLOTS + 63)) | set(range(0x0200, 0x0300))
                  | set(range(0x01F0, 0x0200)) | set(asm.CPU_MASK_ADDRESSES)
                  | {0x02, 0x07C3, asm.PLAYED, 0x07ED, 0x07EF, 0x07F0})
EXAMPLES = (
    ((15, 0, 0, 0xFFFFFFDF), "749MS3YCSUT9XBB4H245S6"),
    ((16, 0, 0, 0xFFFFFFFF), "7DVMS3YCSUT8XBB4H2DCNH"),
)


def state_cases():
    rng = random.Random(0x5032)
    for played in range(32):
        mask = (1 << played) - 1
        for results, cpu_mask in ((0, 0), (mask, 0xFFFFFFFF),
                                  (0x55555555 & mask, 0xFFFFFFFF ^ (1 << played)),
                                  (rng.getrandbits(played), rng.getrandbits(32))):
            yield rng.randrange(32), played, results, cpu_mask


def forgeries():
    original = model.to_bytes(16, 15, 0x1234, 0xFFFEFFFF)
    for byte, bit in ((0, bit) for bit in range(6)):
        payload = bytearray(original)
        payload[byte] ^= 1 << bit
        yield payload
    for byte, bits in ((1, range(5, 8)), (2, range(5, 8)), (6, (7,)), (11, range(8))):
        for bit in bits:
            payload = bytearray(original)
            payload[byte] |= 1 << bit
            yield payload
    for played in range(32):
        payload = bytearray(model.to_bytes(played, played, 0, 0xFFFFFFFF))
        payload[3 + played // 8] |= 1 << (played % 8)
        yield payload


def forged_text(payload):
    payload = bytearray(payload)
    payload[12:] = model.crc16(payload[:12]).to_bytes(2, "big")
    bits = int.from_bytes(bytes(byte ^ mask for byte, mask in zip(payload, model.MASK)), "big")
    return "".join(model.ALPHABET[(bits >> shift) & 31] for shift in range(105, -1, -5))


def substitutions(text):
    for index, original in enumerate(text):
        for char in model.ALPHABET:
            if char != original:
                yield text[:index] + char + text[index + 1:]


def swaps(text):
    for index in range(21):
        if text[index] != text[index + 1]:
            yield text[:index] + text[index + 1] + text[index] + text[index + 2:]


def alias_text(text):
    aliases = {char: alias for alias, char in model.ALIASES.items()}
    return "".join(aliases.get(char, char) for char in text)


def stock_encode(payload, played):
    total = sum(payload) + played
    stream = payload + bytes(((played << 4) | ((total >> 6) & 15), total & 255))
    return "".join(model.ALPHABET[sum(((stream[(plane * 22 + index) // 8]
                                      >> ((plane * 22 + index) % 8)) & 1) << plane
                                    for plane in range(5))] for index in range(22))


def stock_decode(text):
    values = [model.VALUE[char] for char in text]
    bits = sum(((values[index % 22] >> (index // 22)) & 1) << index for index in range(110))
    stream = bits.to_bytes(14, "little")
    played = stream[12] >> 4
    checksum = ((stream[12] & 15) << 6) | (stream[13] & 63)
    teams = [nibble for byte in stream[2:10] for nibble in (byte >> 4, byte & 15)]
    if (sum(stream[:12]) + played) & 1023 != checksum or len(set(teams)) != 16:
        raise ValueError("invalid stock password")
    return stream[:12], played


def stock_cases():
    rng = random.Random(1)
    for _ in range(64):
        teams = list(range(16))
        rng.shuffle(teams)
        payload = (rng.getrandbits(16).to_bytes(2, "little")
                   + bytes((teams[2 * index] << 4) | teams[2 * index + 1] for index in range(8))
                   + rng.getrandbits(16).to_bytes(2, "little"))
        yield payload, rng.randrange(16)


def display_bytes(text):
    return (text[:6] + " " + text[6:12]).encode() + b"\xff" + (
        text[12:18] + " " + text[18:]).encode() + b"\xff"


class Memory(list):
    def __init__(self):
        super().__init__([0xA5] * 0x10000)
        self.writes = set()

    def __setitem__(self, address, value):
        if isinstance(address, int):
            self.writes.add(address)
        super().__setitem__(address, value)


def machine(bank, segments=()):
    memory = Memory()
    memory[0x8000:0xC000] = ROM[16 + bank * 0x4000:16 + (bank + 1) * 0x4000]
    memory[0xC000:] = ROM[0x3C010:0x40010]
    for address, data in segments:
        memory[address:address + len(data)] = data
    return MPU(memory=memory)


def call(cpu, entry, stop=0x0600):
    cpu.sp = 0xFF
    if stop == 0x0600:
        cpu.stPushWord(stop - 1)
    stack = cpu.sp
    cpu.pc = entry
    cpu.memory.writes.clear()
    start_cycles = cpu.processorCycles
    for _ in range(15000):
        if cpu.pc == stop:
            expected_stack = 0xFF if stop == 0x0600 else stack
            assert cpu.sp == expected_stack, (hex(entry), hex(cpu.sp))
            return cpu.processorCycles - start_cycles
        cpu.step()
    raise AssertionError(f"CPU did not stop from ${entry:04X}, PC=${cpu.pc:04X}")


def measured_call(cpu, name, entry, stop=0x0600):
    cycles = call(cpu, entry, stop)
    if cycles >= FRAME_CYCLES:
        raise AssertionError(f"{name} took {cycles} cycles, budget {FRAME_CYCLES}")
    MAX_CYCLES[name] = max(MAX_CYCLES[name], cycles)
    CPU_CASES[name] += 1
    return cycles


class HostTests(unittest.TestCase):
    def test_crc_and_design_examples(self):
        self.assertEqual(model.crc16(b"123456789"), 0x29B1)
        for state, expected in EXAMPLES:
            self.assertEqual(model.encode(*state), expected)
            self.assertEqual(model.decode(expected), state)
        self.assertEqual(model.MASK.hex(), "2181c9f0dc5ffb2996b1d38cd0aa")

    def test_round_trips_and_all_corruptions(self):
        substitutions_checked = swaps_checked = 0
        for state in state_cases():
            text = model.encode(*state)
            self.assertEqual(model.decode(text), state)
            self.assertEqual(model.decode(alias_text(text)), state)
            self.assertEqual(model.decode(" ".join((text[:6], text[6:12], text[12:18], text[18:])).lower()), state)
            self.assertEqual(model.display(text), display_bytes(text))
            for changed in substitutions(text):
                with self.assertRaises(ValueError):
                    model.decode(changed)
                substitutions_checked += 1
            for changed in swaps(text):
                with self.assertRaises(ValueError):
                    model.decode(changed)
                swaps_checked += 1
        print(f"host: 128 states, {substitutions_checked} substitutions, {swaps_checked} adjacent swaps", flush=True)

    def test_reserved_and_future_result_bits_with_valid_crc(self):
        for payload in forgeries():
            with self.assertRaises(ValueError):
                model.decode(forged_text(payload))
        for played in range(32):
            for bit in range(played, 32):
                payload = bytearray(model.to_bytes(0, played, 0, 0))
                payload[3 + bit // 8] |= 1 << (bit % 8)
                with self.assertRaises(ValueError):
                    model.decode(forged_text(payload))

    def test_host_boundaries(self):
        for index, maximum in enumerate((31, 31, 0x7FFFFFFF, 0xFFFFFFFF)):
            for invalid in (-1, maximum + 1, True, False, 1.0, "1", None):
                state = [0, 31, 0, 0]
                state[index] = invalid
                with self.assertRaises(ValueError):
                    model.encode(*state)
        for invalid in (-1, 32, True, 1.0, "1", None):
            with self.assertRaises(ValueError):
                model.seed_order(invalid)
        for played in range(32):
            with self.assertRaises(ValueError):
                model.encode(0, played, 1 << played, 0)
        text = model.encode(0, 0, 0, 0)
        for invalid in (text[:-1], text + "1", "", text + "\n", text[:-1] + "é",
                        text[:-1] + ":", text[:-1] + "\t", text.encode(), None):
            with self.assertRaises(ValueError):
                model.decode(invalid)
        for invalid in ([], list(range(31)), list(range(33)), [0] * 32,
                        [True] + list(range(1, 32)), ["0"] + list(range(1, 32)), None):
            with self.assertRaises(ValueError):
                model.advance(invalid, 0, 0)
        for played, results in ((-1, 0), (32, 0), (True, 0), (0, -1), (1, 2), (1, True)):
            with self.assertRaises(ValueError):
                model.advance(list(range(32)), played, results)
        for seed in range(32):
            self.assertEqual(model.seed_order(seed), [seed] + [team for team in range(32) if team != seed])
            self.assertEqual(model.advance(model.seed_order(seed), 31, 0)[62], seed)
            self.assertEqual(model.advance(model.seed_order(seed), 31, 0x7FFFFFFF)[62], 31 if seed != 31 else 30)

    def test_cli(self):
        script = str(Path(model.__file__).resolve())
        def command(*args):
            return subprocess.run([sys.executable, "-B", script, *args], capture_output=True, text=True)
        help_result = command("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for word in ("encode", "decode", "test", "110 bits"):
            self.assertIn(word, help_result.stdout)
        state, text = EXAMPLES[0]
        encoded = command("encode", "--seed", str(state[0]), "--cpu-mask", hex(state[3]))
        self.assertEqual(encoded.returncode, 0, encoded.stderr)
        self.assertEqual(encoded.stdout.strip(), text)
        decoded = command("decode", text)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertIn("seed=15 played=0 results=0x00000000 cpu_mask=0xFFFFFFDF", decoded.stdout)
        self.assertNotIn("champion:", decoded.stdout)
        self.assertEqual(command("encode", "--seed", "32").returncode, 2)
        self.assertEqual(command("encode", "--cpu-mask", "-1").returncode, 2)
        self.assertEqual(command("encode", "--results", "1").returncode, 2)
        self.assertEqual(command("decode", text[:-1]).returncode, 2)
        smoke = command("test", "--rounds", "2")
        self.assertEqual(smoke.returncode, 0, smoke.stderr)
        self.assertIn("4 round trips", smoke.stdout)
        self.assertEqual(command("test", "--rounds", "-1").returncode, 2)

    def test_stock_format_is_rejected(self):
        for payload, played in stock_cases():
            with self.assertRaises(ValueError):
                model.decode(stock_encode(payload, played))


class CpuTests(unittest.TestCase):
    def decode(self, text, expected=None):
        self.assertEqual(len(text), 22)
        cpu = machine(12, asm.BANK12_SEGMENTS)
        cpu.memory[asm.PASSWORD:asm.PASSWORD + 22] = text
        measured_call(cpu, "decode", asm.DECODE_ENTRY)
        self.assertEqual(cpu.p & 1, expected is None, bytes(text))
        self.assertFalse(cpu.memory.writes - SCRATCH_WRITES,
                         sorted(cpu.memory.writes - SCRATCH_WRITES))
        if expected is not None:
            self.assertEqual(bytes(cpu.memory[asm.PAYLOAD:asm.PAYLOAD + 14]), model.to_bytes(*expected))
        return cpu

    def test_segments_match_source_and_fit(self):
        self.assertEqual(assemble(asm.CODEC_ASM, asm.DECODE_ENTRY)[0], asm.BANK12_CODE)
        self.assertEqual(assemble(asm.RESTORE_ASM, asm.RESTORE_ENTRY)[0], asm.BANK11_RESTORE_CODE)
        self.assertEqual(len(asm.BANK12_CODE), 427)
        self.assertEqual(len(asm.BANK11_RESTORE_CODE), 113)
        self.assertEqual(sum(len(data) for _, data in asm.BANK12_SEGMENTS[1:]), 119)
        for bank, segments in ((12, asm.BANK12_SEGMENTS), (11, asm.BANK11_SEGMENTS)):
            self.assertIsInstance(segments, tuple)
            end = 0x8000
            for address, data in segments:
                self.assertIsInstance(data, bytes)
                self.assertGreaterEqual(address, end)
                end = address + len(data)
                offset = 16 + bank * 0x4000 + address - 0x8000
                self.assertEqual(ROM[offset:offset + len(data)], b"\xff" * len(data))
        self.assertEqual(asm.BANK12_CODE[:6], bytes((0x4C, asm.BANK12_LABELS["pw32_decode"] & 255,
                                                   asm.BANK12_LABELS["pw32_decode"] >> 8,
                                                   0x4C, asm.BANK12_LABELS["pw32_encode"] & 255,
                                                   asm.BANK12_LABELS["pw32_encode"] >> 8)))

    def test_encode_decode_model_parity(self):
        for state in state_cases():
            seed, played, results, mask = state
            text = model.encode(*state)
            self.decode(text.encode(), state)
            self.decode(alias_text(text).encode(), state)
            heap = model.advance(model.seed_order(seed), played, results)
            cpu = machine(12, asm.BANK12_SEGMENTS)
            cpu.memory[asm.SLOTS:asm.SLOTS + 63] = [0xFF if team is None else team for team in heap]
            cpu.memory[asm.PLAYED] = played
            for index, address in enumerate(asm.CPU_MASK_ADDRESSES):
                cpu.memory[address] = (mask >> (8 * index)) & 255
            measured_call(cpu, "encode", asm.ENCODE_ENTRY)
            self.assertEqual(bytes(cpu.memory[asm.PASSWORD:asm.PASSWORD + 26]), display_bytes(text), state)
            allowed = SCRATCH_WRITES | set(range(asm.PASSWORD, asm.PASSWORD + 26))
            self.assertFalse(cpu.memory.writes - allowed, sorted(cpu.memory.writes - allowed))

    def test_restore_real_seeder_all_seeds_and_played(self):
        for seed in range(32):
            masks = (0, 0xFFFFFFFF, 0x0000FFFF, 0xFFFF0000,
                     0xFFFFFFFF ^ (1 << seed), 1 << seed, 0x55555555, 0xAAAAAAAA)
            for played in range(32):
                result_mask = (1 << played) - 1
                results = (0, result_mask, 0x55555555 & result_mask,
                           0x2AAAAAAA & result_mask)[(seed + played) % 4]
                mask = masks[(seed + played) % len(masks)]
                state = seed, played, results, mask
                payload = model.to_bytes(*state)
                cpu = machine(11, asm.BANK11_SEGMENTS)
                cpu.memory[asm.PAYLOAD:asm.PAYLOAD + 14] = payload
                measured_call(cpu, "restore", asm.RESTORE_ENTRY, stop=0x8000)
                heap = model.advance(model.seed_order(seed), played, results)
                self.assertEqual(cpu.memory[asm.SLOTS:asm.SLOTS + 63],
                                 [0xFF if team is None else team for team in heap], state)
                self.assertEqual(cpu.memory[asm.PLAYED], played)
                self.assertEqual(bytes(cpu.memory[address] for address in asm.CPU_MASK_ADDRESSES), mask.to_bytes(4, "little"))
                self.assertEqual([cpu.memory[address] for address in (0x07C3, 0x07CA, 0x07ED, 0x07EF, 0x07F0)],
                                 [seed, 0xA5, 1, 0x32, 0])
                self.assertEqual(cpu.memory[0x0200:0x0300], [0xF0] * 256)
                self.assertEqual(bytes(cpu.memory[asm.PAYLOAD:asm.PAYLOAD + 14]), payload)
                self.assertFalse(cpu.memory.writes - RESTORE_WRITES, sorted(cpu.memory.writes - RESTORE_WRITES))

    def test_decode_restore_encode_chain(self):
        for index, state in enumerate(state_cases()):
            if index % 4 != 3:
                continue
            text = model.encode(*state)
            cpu = self.decode(text.encode(), state)
            start = 16 + 11 * 0x4000
            cpu.memory[0x8000:0xC000] = ROM[start:start + 0x4000]
            for address, data in asm.BANK11_SEGMENTS:
                cpu.memory[address:address + len(data)] = data
            measured_call(cpu, "restore", asm.RESTORE_ENTRY, stop=0x8000)
            self.assertFalse(cpu.memory.writes - RESTORE_WRITES)
            heap = model.advance(model.seed_order(state[0]), state[1], state[2])
            self.assertEqual(cpu.memory[asm.SLOTS:asm.SLOTS + 63],
                             [0xFF if team is None else team for team in heap])
            start = 16 + 12 * 0x4000
            cpu.memory[0x8000:0xC000] = ROM[start:start + 0x4000]
            for address, data in asm.BANK12_SEGMENTS:
                cpu.memory[address:address + len(data)] = data
            measured_call(cpu, "encode", asm.ENCODE_ENTRY)
            self.assertEqual(bytes(cpu.memory[asm.PASSWORD:asm.PASSWORD + 26]), display_bytes(text))
            self.assertFalse(cpu.memory.writes - SCRATCH_WRITES - set(range(asm.PASSWORD, asm.PASSWORD + 26)))

    def test_all_substitutions_and_adjacent_swaps(self):
        cases = ((15, 0, 0, 0xFFFFFFDF), (31, 31, 0x7FFFFFFF, 0x80000000))
        for state in cases:
            text = model.encode(*state)
            for changed in substitutions(text):
                self.decode(changed.encode())
            for changed in swaps(text):
                self.decode(changed.encode())

    def test_semantic_forgeries_with_valid_crc(self):
        for payload in forgeries():
            self.decode(forged_text(payload).encode())

    def test_input_bytes_and_unfilled_slots(self):
        state = 16, 31, 0x12345678, 0xFFFEFFFF
        text = model.encode(*state).encode()
        for invalid in range(256):
            if chr(invalid) not in model.VALUE:
                self.decode(text[:-1] + bytes((invalid,)))
        for length in range(22):
            self.decode(text[:length] + b"\x00" * (22 - length))
        cpu = machine(12, asm.BANK12_SEGMENTS)
        cpu.memory[asm.PASSWORD:asm.PASSWORD + 22] = text
        cpu.memory[asm.PASSWORD + 22] = 0x00
        measured_call(cpu, "decode", asm.DECODE_ENTRY)
        self.assertEqual(cpu.p & 1, 0)
        self.assertEqual(cpu.memory[asm.PASSWORD + 22], 0x00)

    def test_stock_codec_byte_parity_and_rejection(self):
        for payload, played in stock_cases():
            text = stock_encode(payload, played)
            self.assertEqual(stock_decode(text), (payload, played))
            encoder = machine(5)
            encoder.memory[0x074B:0x0757] = payload
            encoder.memory[0x0746] = played
            call(encoder, 0xA036)
            self.assertEqual(bytes(encoder.memory[0x0643:0x065D]), display_bytes(text))
            for spelling in (text, alias_text(text)):
                decoder = machine(1)
                decoder.memory[0x0643:0x0659] = spelling.encode()
                decoder.memory[0x07ED] = 0
                call(decoder, 0xA8A2)
                self.assertEqual(decoder.memory[0x07ED], 1)
                self.assertEqual(bytes(decoder.memory[0x074B:0x0757]), payload)
                self.assertEqual(decoder.memory[0x0746], played)
            changed = next(substitutions(text))
            try:
                stock_decode(changed)
                expected = 1
            except ValueError:
                expected = 0
            decoder = machine(1)
            decoder.memory[0x0643:0x0659] = changed.encode()
            decoder.memory[0x07ED] = 0
            call(decoder, 0xA8A2)
            self.assertEqual(decoder.memory[0x07ED], expected)
            self.decode(text.encode())
        payload = bytes.fromhex("feff0023456789abcdef0000")
        decoder = machine(1)
        decoder.memory[0x0643:0x0659] = stock_encode(payload, 0).encode()
        decoder.memory[0x07ED] = 0
        call(decoder, 0xA8A2)
        self.assertEqual(decoder.memory[0x07ED], 0)
        print("stock: 64 byte-identical encodes and decodes; aliases, corruption parity and duplicate rejection", flush=True)


def main():
    global ROM
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="frozen results32 ROM, read only")
    args = parser.parse_args()
    ROM = args.rom.read_bytes()
    if hashlib.sha256(ROM).hexdigest() != ROM_SHA256:
        parser.error("input SHA-256 does not match frozen results32")
    suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(HostTests),
                                unittest.defaultTestLoader.loadTestsFromTestCase(CpuTests)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"CPU cases: {CPU_CASES}; maximum cycles: {MAX_CYCLES}; each below {FRAME_CYCLES}", flush=True)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
