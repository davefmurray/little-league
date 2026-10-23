#!/usr/bin/env python3
"""Build direct31-pair22: capture/restore the field-entry pair.

Base: build/direct31-pair17.nes (pair13 prefill + pair16 no-zero +
pair17 forced copy).

pair22 adds:
  * $B247: call a helper that stores $0525 -> $0491 and, when both pair
    bytes are valid low-nibble group ids (< $10), copies them to
    $07F2/$07F3.
  * $AC09/$AC9E (scene-05 clears): call helpers that restore $0490/$0491
    from the captured values, clearing to 0 when no valid capture exists
    (boot path).  The following JSR $82A1 is left untouched.

Scratch: $07F2/$07F3 (documented debug scratch, no direct ROM refs).
Helpers: bank7 $BF00/$BF20/$BF30 (inside the $BB83-$BFEF $FF padding).

The handoff proposed $04D1/$04D2, but those are live: bank6 $AB55,
$AEF1, $AFAB/$AFB2/$AFFB/$B6FD/$B77C and bank7/bank15 $9ED4, plus
$04D2 at bank6 $AFBB/$B781.  Do not use them.

Usage: python3 tools/build_pitch_pair22.py
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "direct31-pair17.nes"
DST = ROOT / "build" / "direct31-pair22.nes"

HEADER = 16
BANK = 0x4000


def off(addr, bank):
    assert 0x8000 <= addr <= 0xBFFF, f"${addr:04X} is not in the switchable window"
    return HEADER + bank * BANK + (addr - 0x8000)


def expect(rom, addr, bank, want, label):
    o = off(addr, bank)
    got = rom[o:o + len(want)]
    if got != want:
        raise SystemExit(
            f"{label} at bank{bank} ${addr:04X}: expected {want.hex(' ')},"
            f" got {got.hex(' ')}"
        )


def patch(rom, addr, bank, data, label):
    o = off(addr, bank)
    rom[o:o + len(data)] = data
    print(f"  bank{bank} ${addr:04X} {label}: {data.hex(' ')}")


def main():
    rom = bytearray(SRC.read_bytes())
    src_sha = hashlib.sha256(rom).hexdigest()
    print(f"base {SRC.name} {src_sha}")

    # --- verify the pair17 sites we are replacing -------------------------
    expect(rom, 0xB247, 7, bytes.fromhex("8D 91 04"), "pair17 $B247 STA $0491")
    expect(rom, 0xAC09, 7, bytes.fromhex("A9 00 8D 90 04"), "pair17 $AC09 clear")
    expect(rom, 0xAC9E, 7, bytes.fromhex("A9 00 8D 91 04"), "pair17 $AC9E clear")
    expect(rom, 0xBF00, 7, b"\xff" * 0x40, "free helper area")

    # --- helper 1: store $0491 + guarded capture --------------------------
    # A = $0525 on entry.  Always perform the original store; capture only
    # when both pair bytes look like group ids (< $10).
    cap = bytes.fromhex(
        "8D 91 04"      # BF00 STA $0491
        "AD 24 05"      # BF03 LDA $0524
        "C9 10"         # BF06 CMP #$10
        "B0 0D"         # BF08 BCS $BF17
        "8D F2 07"      # BF0A STA $07F2
        "AD 25 05"      # BF0D LDA $0525
        "C9 10"         # BF10 CMP #$10
        "B0 03"         # BF12 BCS $BF17
        "8D F3 07"      # BF14 STA $07F3
        "60"            # BF17 RTS
    )
    assert len(cap) == 0x18

    # --- helper 2: restore $0490 (or clear when no valid capture) ---------
    res0 = bytes.fromhex(
        "AD F2 07"      # BF20 LDA $07F2
        "C9 10"         # BF23 CMP #$10
        "90 02"         # BF25 BCC $BF29
        "A9 00"         # BF27 LDA #$00
        "8D 90 04"      # BF29 STA $0490
        "60"            # BF2C RTS
    )
    assert len(res0) == 0x0D

    # --- helper 3: restore $0491 ------------------------------------------
    res1 = bytes.fromhex(
        "AD F3 07"      # BF30 LDA $07F3
        "C9 10"         # BF33 CMP #$10
        "90 02"         # BF35 BCC $BF39
        "A9 00"         # BF37 LDA #$00
        "8D 91 04"      # BF39 STA $0491
        "60"            # BF3C RTS
    )
    assert len(res1) == 0x0D

    print("helpers:")
    patch(rom, 0xBF00, 7, cap, "capture")
    patch(rom, 0xBF20, 7, res0, "restore $0490")
    patch(rom, 0xBF30, 7, res1, "restore $0491")

    print("sites:")
    patch(rom, 0xB247, 7, bytes.fromhex("20 00 BF"), "JSR capture")
    patch(rom, 0xAC09, 7, bytes.fromhex("20 20 BF EA EA"), "JSR restore $0490")
    patch(rom, 0xAC9E, 7, bytes.fromhex("20 30 BF EA EA"), "JSR restore $0491")

    DST.write_bytes(rom)
    sha = hashlib.sha256(rom).hexdigest()
    print(f"wrote {DST.relative_to(ROOT)} {sha}")
    print(f"size {len(rom)}")


if __name__ == "__main__":
    main()
