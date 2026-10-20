#!/usr/bin/env python3
"""Verify the 32-team build's iNES layout and SHA-256 against a manifest.

    python3 tools/check_build.py build/direct31.nes --write
    python3 tools/check_build.py build/direct31.nes

The manifest (`docs/build-manifest.json`) pins the reproducible build hash;
a mismatch means the data/tools changed and the manifest must be refreshed
on purpose.
"""
import argparse
import hashlib
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", nargs="?", default="build/direct31.nes")
    ap.add_argument("--manifest", default="docs/build-manifest.json")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rom = open(args.rom, "rb").read()
    if rom[:4] != b"NES\x1a":
        raise SystemExit("not an iNES file")
    prg, chr_ = rom[4], rom[5]
    if prg != 16 or chr_ != 16:
        raise SystemExit(f"expected 16 PRG / 16 CHR banks, got {prg}/{chr_}")
    mapper = (rom[7] & 0xF0) | (rom[6] >> 4)
    if mapper != 1:
        raise SystemExit(f"expected mapper 1 (MMC1), got {mapper}")
    size = 16 + prg * 0x4000 + chr_ * 0x2000
    if len(rom) != size:
        raise SystemExit(f"size {len(rom)} != header size {size}")

    info = {
        "file": os.path.basename(args.rom),
        "bytes": len(rom),
        "prg_banks": prg,
        "chr_banks": chr_,
        "mapper": mapper,
        "sha256": hashlib.sha256(rom).hexdigest(),
    }

    if args.write:
        os.makedirs(os.path.dirname(args.manifest) or ".", exist_ok=True)
        open(args.manifest, "w").write(json.dumps(info, indent=1) + "\n")
        print(f"wrote {args.manifest}: {info['sha256']}")
        return

    if not os.path.exists(args.manifest):
        raise SystemExit(f"{args.manifest} missing; run with --write first")
    want = json.load(open(args.manifest))
    for key in ("bytes", "prg_banks", "chr_banks", "mapper"):
        if info[key] != want.get(key):
            raise SystemExit(f"{key}: {info[key]} != manifest {want.get(key)}")
    if info["sha256"] != want.get("sha256"):
        raise SystemExit(f"sha256: {info['sha256']} != manifest {want.get('sha256')}")
    print(f"check_build OK: {info['sha256']} ({len(rom)} bytes, mapper 1)")


if __name__ == "__main__":
    main()
