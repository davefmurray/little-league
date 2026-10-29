#!/usr/bin/env python3
"""Add random first-round draws and v2 passwords to the pinned menuart32 ROM.

    .venv/bin/python tools/build_draw32.py build/menuart32.nes -o build/draw32.nes
    .venv/bin/python tools/build_draw32.py build/menuart32.nes -o build/draw32.nes --manifest

The draw runs only where the ROM already seeds a bracket: new-series creation
(bank 11 $86EF) and password restore ($8606). Bracket redraws never call it,
so a draw never changes after creation. WRAM $7760/$7761 holds the series
draw seed beside the heap it describes. A legacy series (seed 0) keeps
emitting byte-identical v1 passwords; a random series emits v2.

The only edits to existing code are two seeder-call operands, the decoder's
3-byte version gate and the encoder's crc16 operand. The routines live in
bank 11 and bank 12 padding (tools/draw32_6502.py).

This module also holds the stage machinery the pick32 and title32 builders
reuse: whole-region change manifests, byte and digest guards, and output
alias refusal.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal

from build_menuart32 import PROTECTED_SHA256 as PRIOR_SHA256, protect_output as protect_prior_output
from build_teamnames32 import HEADER, ROM_SIZE, ROOT, off
from draw32_6502 import CODEC_LABELS, CODEC_SEGMENT, CRC16, DRAW_LABELS, DRAW_SEGMENT, STOCK_SEEDER

BASE_SHA256 = "bcb7fcdc2c1decd47de2f3504c8c81d907a3d195629a1526ff4b0e919a89f2a3"
PROTECTED_SHA256 = PRIOR_SHA256 | {BASE_SHA256}
CHR_START = len(HEADER) + 16 * 0x4000


@dataclass(frozen=True)
class Region:
    name: str
    bank: int | Literal["chr"]
    start: int
    end: int


@dataclass(frozen=True)
class Change:
    name: str
    bank: int | Literal["chr"]
    addr: int
    before: bytes
    after: bytes


REGIONS = (
    Region("draw-code", 11, 0x8220, 0x8300),
    Region("restore-call", 11, 0x8607, 0x8609),
    Region("seed-entry-call", 11, 0x86F0, 0x86F2),
    Region("decode-gate", 12, 0x8058, 0x805B),
    Region("encode-call", 12, 0x8114, 0x8116),
    Region("codec-code", 12, 0x8200, 0x8300),
)

DEPENDENCIES = (
    ("seeder $8200", 11, 0x8200, "AD C3 07 8D 00 77 A2 01 8A 38 E9 01 CD 00 77 90 03 18 69 01 9D 00 77 E8 E0 20"
     " D0 EC 60"),
    ("new series $8380", 11, 0x8380, "A9 00 8D FC 07 A9 FF A2 20 9D 00 77 E8 E0 3F D0 F8 4C E0 86"),
    ("seed entry $86E0", 11, 0x86E0, "A9 32 8D EF 07 A9 01 8D ED 07 A9 00 8D F0 07 20 00 82 4C 00 80"),
    ("PRG writer $C14C", 15, 0xC14C, "A5 27 85 27 E6 2D 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF 4A 8D FF FF"
     " C6 2D 60"),
    ("password decode bridge $FCC0", 15, 0xFCC0, "A9 0C 20 4E C1 20 00 80 90 0B A9 01 20 4E C1 A9 00 8D ED 07 60"
     " A9 00 8D 00 20 A9 0B 20 4E C1 4C 00 86"),
    ("password encode bridge $FCE2", 15, 0xFCE2, "AD EF 07 C9 32 D0 12 AD ED 07 F0 0D A9 0C 20 4E C1 20 03 80"
     " A9 05 4C 4E C1 4C 36 A0"),
)
DIGESTS = (
    ("password restore $8600-$867F", 11, 0x8600, 0x80,
     "b06531ecdc2d5ae8d0fe25e627aa36dd7281c8dfc305ce91036620d0a144827a"),
    ("v1 codec $8000-$81AA", 12, 0x8000, 0x1AB, "24b3bc7aea6b45352f5f8222818571d0581d5b762fa9abeca326ff34cab66a19"),
    ("v1 codec tables $8F00-$8F7F", 12, 0x8F00, 0x80,
     "4481cc2cc351b1ac6d26713bee14d11ab628cd0269a63952c0412676053dc8c0"),
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def locate(bank, addr):
    return CHR_START + addr if bank == "chr" else off(bank, addr)


def read(rom, bank, addr, size):
    start = locate(bank, addr)
    return bytes(rom[start:start + size])


def word(addr):
    return addr.to_bytes(2, "little")


def check_guards(base, dependencies, digests=()):
    for label, bank, addr, text in dependencies:
        expected = bytes.fromhex(text)
        if read(base, bank, addr, len(expected)) != expected:
            raise ValueError(f"{label}: unexpected stock bytes")
    for label, bank, addr, size, digest in digests:
        if sha256(read(base, bank, addr, size)) != digest:
            raise ValueError(f"{label}: unexpected bytes")


def padded(code, region):
    size = region.end - region.start
    if len(code) > size:
        raise ValueError(f"{region.name} is {len(code)} bytes; its region holds {size}")
    return code + b"\xFF" * (size - len(code))


def claim(base, region, after, hook=None):
    """A change covering `region`. A hook must find its exact old bytes, given as bytes or as their
    SHA-256; anything else must be free padding."""
    before = read(base, region.bank, region.start, len(after))
    if hook is None and before != b"\xFF" * len(after):
        raise ValueError(f"{region.name}: reservation is not free space")
    if hook is not None and (sha256(before) if isinstance(hook, str) else before) != hook:
        raise ValueError(f"{region.name}: unexpected hook bytes")
    return Change(region.name, region.bank, region.start, before, after)


def apply_changes(base, changes, regions):
    """Write each change over exactly its region, once, after checking its old bytes."""
    owners = {r.name: r for r in regions}
    rom, claimed, names = bytearray(base), set(), set()
    for c in changes:
        region = owners.get(c.name)
        if (region is None or c.name in names or c.bank != region.bank or not c.after
                or len(c.before) != len(c.after) or (c.addr, c.addr + len(c.after)) != (region.start, region.end)):
            raise ValueError(f"{c.name}: overlapping, invalid or unowned change")
        start = locate(c.bank, c.addr)
        span = set(range(start, start + len(c.after)))
        if claimed & span:
            raise ValueError(f"{c.name}: overlapping change")
        if base[start:start + len(c.before)] != c.before:
            raise ValueError(f"{c.name}: unexpected input bytes")
        claimed |= span
        names.add(c.name)
        rom[start:start + len(c.after)] = c.after
    if names != set(owners):
        raise ValueError("incomplete change manifest")
    return bytes(rom)


def manifest_ranges(changes):
    return [
        {"name": c.name, "bank": c.bank, "address": c.addr, "file_offset": locate(c.bank, c.addr),
         "size": len(c.after), "before_sha256": sha256(c.before), "after_sha256": sha256(c.after),
         "changed_file_offsets": [locate(c.bank, c.addr) + i for i, (a, b) in enumerate(zip(c.before, c.after))
                                  if a != b]}
        for c in changes
    ]


def refuse_aliases(output, paths, protected_sha256):
    output = Path(output)
    for path in paths:
        path = Path(path)
        if (output.resolve() == path.resolve()
                or (output.exists() and path.exists() and output.samefile(path))):
            raise ValueError(f"output aliases protected input {path}")
    if output.is_file() and sha256(output.read_bytes()) in protected_sha256:
        raise ValueError("output aliases protected input ROM artifact")


def change_manifest(base):
    check_guards(base, DEPENDENCIES, DIGESTS)
    region = {r.name: r for r in REGIONS}
    return (
        claim(base, region["draw-code"], padded(DRAW_SEGMENT[1], region["draw-code"])),
        claim(base, region["restore-call"], word(DRAW_LABELS["restore_draw"]), word(STOCK_SEEDER)),
        claim(base, region["seed-entry-call"], word(DRAW_LABELS["new_series_draw"]), word(STOCK_SEEDER)),
        claim(base, region["decode-gate"], b"\x4C" + word(CODEC_LABELS["v2_gate"]), bytes.fromhex("AD 27 06")),
        claim(base, region["encode-call"], word(CODEC_LABELS["v2_fields"]), word(CRC16)),
        claim(base, region["codec-code"], padded(CODEC_SEGMENT[1], region["codec-code"])),
    )


def build_rom(base):
    if len(base) != ROM_SIZE or base[:len(HEADER)] != HEADER:
        raise ValueError("expected menuart32 ROM size and iNES header")
    if sha256(base) != BASE_SHA256:
        raise ValueError("input SHA-256 does not match pinned menuart32")
    return apply_changes(base, change_manifest(base), REGIONS)


def diff_manifest(base, rom):
    return {"input_sha256": sha256(base), "output_sha256": sha256(rom),
            "ranges": manifest_ranges(change_manifest(base))}


def protect_output(source, output):
    source, output = Path(source), Path(output)
    protect_prior_output(source, output)
    refuse_aliases(output, [ROOT / "build/menuart32.nes", source.resolve().parent / "menuart32.nes",
                            source.resolve(), ROOT / "tools/verify.sh",
                            *(ROOT / "art/title32").rglob("*"),
                            *(ROOT / "data/title32").rglob("*")], PROTECTED_SHA256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path, help="pinned menuart32 input")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--manifest", action="store_true", help="print the exact byte manifest as JSON")
    args = ap.parse_args()
    try:
        protect_output(args.rom, args.out)
        base = args.rom.read_bytes()
        rom = build_rom(base)
        args.out.write_bytes(rom)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if args.manifest:
        print(json.dumps(diff_manifest(base, rom), indent=2))
    else:
        diff = sum(a != b for a, b in zip(base, rom))
        print(f"wrote {args.out}: {sha256(rom)} ({diff} bytes changed)")


if __name__ == "__main__":
    main()
