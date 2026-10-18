#!/usr/bin/env python3
"""TBL encoder/decoder/scanner for Little League Baseball (NES).

    python3 tools/tbl.py --encode "NEW YORK"
    python3 tools/tbl.py --decode 4e455720594f524b
    python3 tools/tbl.py ROM --scan --min 6
    python3 tools/tbl.py ROM --at 0x5180 --len 64
"""
import argparse
import os

DEFAULT_TBL = os.path.join(os.path.dirname(__file__), "..", "data", "llbcs.tbl")


def load(path):
    enc, dec = {}, {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "=" not in line:
            continue
        h, text = line.split("=", 1)
        try:
            b = int(h, 16)
        except ValueError:
            continue
        enc[text] = b
        dec[b] = text
    return enc, dec


def decode(data, dec, blank="."):
    return "".join(dec.get(b, blank) for b in data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", nargs="?")
    ap.add_argument("--tbl", default=DEFAULT_TBL)
    ap.add_argument("--encode")
    ap.add_argument("--decode")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--at")
    ap.add_argument("--len", type=int, default=32)
    ap.add_argument("--min", type=int, default=6)
    args = ap.parse_args()

    enc, dec = load(args.tbl)

    if args.encode is not None:
        out = bytearray()
        for ch in args.encode.upper():
            out.append(enc.get(ch, 0x20))
        print(out.hex(" "))
        return

    if args.decode:
        data = bytes.fromhex(args.decode.replace(" ", ""))
        print(decode(data, dec))
        return

    if not args.rom:
        ap.error("ROM required for --scan/--at")

    rom = open(args.rom, "rb").read()
    if args.at:
        off = int(args.at, 0)
        data = rom[off:off + args.len]
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            print(f"${off+i:05X}: {chunk.hex(' '):<47} {decode(chunk, dec)}")
        return

    # scan printable runs
    valid = set(dec)
    runs = []
    start = None
    for i, b in enumerate(rom):
        if b in valid:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= args.min:
                runs.append((start, i))
            start = None
    if start is not None and len(rom) - start >= args.min:
        runs.append((start, len(rom)))
    for a, b in runs:
        text = decode(rom[a:b], dec)
        print(f"${a:05X} {b-a:3d} {text}")


if __name__ == "__main__":
    main()
