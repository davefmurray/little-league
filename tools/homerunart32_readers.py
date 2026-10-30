#!/usr/bin/env python3
"""Who else reads what the HOME RUN stage redraws: the stage's reader argument as checks, not prose.

    .venv/bin/python -B tools/homerunart32_readers.py build/analysisart32.nes [build/homerunart32.nes]

The stage replaces all of CHR $04 and $15, the planes of free set-$15 metatile ids, map $24 and palette record
$0E. checks() rechecks the reviewed direct-reader chains and pins their bytes. These scans are not a complete
reachability proof: indexed/indirect writes, table-driven CHR loads, non-immediate palette loads, masked CHR
aliases and scene increments outside banks 5/15 need separate review. The builder also pins the entire input
ROM. Changing that pin requires a new ownership audit; passing these checks alone does not authorize it.

CHR $15's only other selector is CHR preset 6 ($FB71, CHR0 $15), requested only after the bank-5 split screen
(screen 5), which only sequence 5 shows, which only scene $1C selects ($CC = 5, $10 set). The checks pin that
chain: reviewed absolute stores to the scene byte $047B and their inferred values, the bank-5 scene steps, the scene
$1A-$1D handlers and $A8A6-$A958, the $A959 sequence table and the $AC5C screen dispatch, every CHR preset
request and the preset table, the SPEED path's transient scene $1D ($F0C0-$F0FF), and the MMC1 control values
(always 4 KB CHR banks, so a CHR $14 selection never pairs with $15). Stores never write $1B or $1C, but the
shared play exit decrements the scene in place, and SPEED runs it on its own $1D: those transient $1C/$1B writes
are pinned too, with the SPEED wrapper that replaces them by $17 before the dispatcher can read them. It is a
static argument: byte-aligned scans over-approximate code and entry points. The reviewed chains are pinned
below, and root's real-core census must still confirm CHR $15 shows only in home-run windows.

Bank 7 holds a stale copy of the original fixed bank; the field HUD maps it at $8000 for its short-name loader.
Scans cover it and keep its findings, but its copies of fixed-bank code only run at their $C000 addresses.
"""
import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys

from py65.devices.mpu6502 import MPU

from build_draw32 import read
import homerunart32_assets as model

STALE_BANK = 7
SCENE = 0x047B
LENGTHS = {"imp": 1, "acc": 1, "imm": 2, "zpg": 2, "zpx": 2, "zpy": 2, "inx": 2, "iny": 2, "rel": 2, "abs": 3,
           "abx": 3, "aby": 3, "ind": 3}
OPCODES = {op: tuple(MPU().disassemble[op]) for op in range(256)}
LOAD_IMMEDIATE = {"STA": 0xA9, "STX": 0xA2, "STY": 0xA0}
PASS_THROUGH = {1: {0xEA}, 2: {0x85, 0x86, 0x84}, 3: {0x8D, 0x8E, 0x8C}}  # NOP; STA/STX/STY zp; STA/STX/STY abs

# Stores to $047B that do not take an immediate loaded right before them, or that other code can enter between
# that load and the store: the values they write, every entry a byte scan finds into that window, and the code
# bytes the review read. An entry not listed here, or changed bytes, fail the check.
REVIEWED_SCENE_STORES = {
    (0, 0xAD30): ({0x06, 0x08}, {0xAD29, 0xAD36}, ((0, 0xAD2E, "A9 08 8D 7B 04 60 A9 06 D0 F8"),),
                  "LDA #$08 falls through; $AD34 LDA #$06 branches back from $AD36; $AD29 is a misaligned decode"),
    (4, 0xAA7F): ({0x0A, 0x0E}, {0xAA78}, ((4, 0xAA74, "A9 0A A6 A7 D0 05 EE E1 06 A9 0E 8D 7B 04"),),
                  "LDA #$0A branches past LDA #$0E when $A7 is set"),
    (4, 0xB6F3): ({0x00, 0x06}, {0xB6DD, 0xB6E6},
                  ((4, 0xB6D5, "A2 00 8E 7A 04 AC E2 04 F0 14 A2 06 AD D0 04 C9 02 F0 0B A9 05 8D 7C 04 A9 13 8D 7B 04 60"
                       " 8E 7B 04 60"),),
                  "STX: X = $00 from $B6D5 or $06 from $B6DF, each branching here"),
    (5, 0x9EC2): ({0x10, 0x16}, {0x9EAC, 0x9EB4},
                  ((5, 0x9E9D, "A9 01 8D EE 04 A2 10 AD 7E 04 49 01 8D EA 04 F0 14 20 6F C4 A2 16 4A 90 0C AD EF 04 AC"
                       " F0 04 8C EF 04 8D F0 04 8E 7B 04"),),
                  "STX: X = $10 from $9EA2 (branch at $9EAC) or $16 from $9EB1 (branch at $9EB4 or fall through)"),
    (5, 0xA901): ({0x13, 0x00}, set(), ((5, 0xA8FC, "A4 CC B9 0B A9 8D 7B 04 B9 11 A9 8D 7C 04 60 13 13 13 00 00 13"),),
                  "the cutscene player's next scene: $A90B indexed by the sequence $CC 0-5"),
    (7, 0xAE3F): ({0x17}, {0xAE94}, ((7, 0xAE3D, "A9 17 8D 7B 04 60"), (7, 0xAE92, "20 EE D0 A9 00")),
                  "stale copy of $EE3F; $AE94 decodes from inside JSR $D0EE's operand"),
    (10, 0xB4F5): ({0x06, 0x14}, {0xB535}, ((10, 0xB4F3, "A9 14 8D 7B 04"), (10, 0xB530, "20 38 B5 A9 06 4C F5 B4")),
                   "LDA #$14 falls through; $B533 LDA #$06 jumps here from $B535"),
    (15, 0xEE3F): ({0x17}, {0xEE94}, ((15, 0xEE3D, "A9 17 8D 7B 04 60"), (15, 0xEE92, "20 EE D0 A9 00")),
                   "$EE94 decodes from inside JSR $D0EE's operand at $EE92"),
}
SCENE_STEPS = {   # INC/DEC $047B in bank 5 (scenes $12-$1D) and the fixed bank (field scenes $02-$05)
    5: {("INC", 0x98D1), ("INC", 0xA8B2), ("INC", 0xA8CA)},
    model.FIXED: {("INC", 0xD010), ("INC", 0xD48C), ("INC", 0xD73C), ("DEC", 0xD80B), ("DEC", 0xD80E),
                  ("DEC", 0xD811)},
}
# The shared play exit lowers the scene in place: $D808 JSR $834F, then DEC $047B three times (scene 5 -> 2). SPEED
# runs it through its play wrapper with scene $17 or, after a half inning, $1D, so $1C and $1B are written there
# transiently; the wrapper reads the result once ($F0B1) and stores $17 ($F0B6) before anything else runs.
PLAY_EXIT = (0xD7EE, "AD 98 04 F0 46 CE 98 04 D0 41 AD D0 04 F0 0B AD 4D 05 D0 03 20 41 D9 4C 72 D8 20 4F 83 CE 7B 04"
                     " CE 7B 04 CE 7B 04")
SPEED_PLAY = (0xF0A9, "A9 06 20 4E C1 20 F8 D7 AD 7B 04 A2 17 8E 7B 04 C9 09 F0 03 4C 79 EE")
PLAY_EXIT_ENTRIES = {   # every byte-scan entry into $D7F8-$D813, reviewed
    (15, 0xD790): "scene 5 state 3, the home-run exit (scene 5)",
    (15, 0xD7F9): "decodes from inside LDA $04D0's operand",
    (15, 0xD7FB): "the exit's own branch to the decrement",
    (15, 0xD800): "the exit's own branch past JSR $D941",
    (15, 0xF0AE): "SPEED's play wrapper",
    (3, 0xACDA): "a sprite-table entry 03 4C 0C D8, not code",
    (7, 0x9790): "stale bank-7 copy of $D790",
    (7, 0xB0AE): "stale bank-7 copy of $F0AE",
}
SCENE_TABLE, SCENE_BANKS = 0xCC52, 0xCCAC          # $CC36: handler by scene, PRG bank by scene >> 1
PLAYER_SCENES = {0x1A: 0xA8A6, 0x1B: 0xA8D0, 0x1C: 0xA8B8, 0x1D: 0xA8D0}
PLAYER = (5, 0xA8A6, 0xA959 - 0xA8A6, "f41551a383c055fd8ab1022b5c0eece176b596bc07c20bdfeb5f4e774464515f")
SEQUENCES, SCREEN_DISPATCH, SPLIT_SCREEN = 0xA959, 0xAC5C, 5
PRESET_TABLE, PRESETS, SPLIT_PRESET, SPLIT_REQUEST = 0xFB4D, 9, 6, (5, 0xAC78)
SPEED_EXIT = 0xF0C0
CONTROL_WRITER, CONTROL_SHADOW = 0xC102, 0x22


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def origin(bank):
    return 0xC000 if bank == model.FIXED else 0x8000


def prg(rom, bank):
    return read(rom, bank, origin(bank), 0x4000)


def decode(data, i):
    mnemonic, mode = OPCODES[data[i]]
    size = LENGTHS.get(mode, 1)
    if i + size > len(data):
        return mnemonic, mode, size, None
    return mnemonic, mode, size, data[i + 1] | data[i + 2] << 8 if size == 3 else data[i + 1] if size == 2 else None


def sites(rom, wanted, banks=range(16)):
    """Byte-aligned scan: (bank, pc, mnemonic, mode, operand) wherever `wanted(mnemonic, mode, operand)`."""
    found = []
    for bank in banks:
        data = prg(rom, bank)
        for i in range(len(data)):
            mnemonic, mode, _, arg = decode(data, i)
            if mnemonic != "???" and arg is not None and wanted(mnemonic, mode, arg):
                found.append((bank, origin(bank) + i, mnemonic, mode, arg))
    return found


def entries(rom, bank):
    """{target: sources}: every address a byte-aligned branch, JMP or JSR in `bank` names, an over-approximation."""
    found = {}
    for _, pc, op, mode, arg in sites(rom, lambda op, mode, arg: mode == "rel" or op in ("JMP", "JSR"), banks=(bank,)):
        found.setdefault(pc + 2 + (arg - 256 if arg > 127 else arg) if mode == "rel" else arg, set()).add(pc)
    return found


def immediate_before(rom, bank, pc, store):
    """(load address, value) when the bytes before the store at `pc` load the stored register with an immediate,
    through NOPs and stores elsewhere; (pc, None) otherwise."""
    data, i = prg(rom, bank), pc - origin(bank)
    while i >= 2:
        if data[i - 2] == LOAD_IMMEDIATE[store]:
            return origin(bank) + i - 2, data[i - 1]
        size = next((n for n, codes in PASS_THROUGH.items() if i >= n and data[i - n] in codes), None)
        if size is None:
            break
        i -= size
    return pc, None


def immediate_loader(rom, bank, pc, size=2):
    """The value an `LDA #imm` right before `pc` loads, or None."""
    return read(rom, bank, pc - size, 2)[1] if read(rom, bank, pc - size, 1)[0] == 0xA9 else None


def walk(rom, start, bank=6):
    """Exits of the code reachable from `start`: JSR is a call that returns, JMP and branches are followed.
    Sorted [(pc, how)] for every RTS, RTI, BRK, undefined opcode, indirect JMP or inline $C232 jump table."""
    view = {**{origin(bank) + i: b for i, b in enumerate(prg(rom, bank))},
            **{origin(model.FIXED) + i: b for i, b in enumerate(prg(rom, model.FIXED))}}
    seen, todo, exits = set(), [start], []
    while todo:
        pc = todo.pop()
        while pc not in seen and pc in view:
            seen.add(pc)
            mnemonic, mode = OPCODES[view[pc]]
            arg = view.get(pc + 1, 0) | view.get(pc + 2, 0) << 8
            if mnemonic == "JSR" and arg == 0xC232:
                exits.append((pc, "JSR $C232 table"))
                break
            if mnemonic in ("RTS", "RTI", "BRK", "???") or (mnemonic == "JMP" and mode == "ind"):
                exits.append((pc, mnemonic))
                break
            if mnemonic == "JMP":
                pc = arg
                continue
            if mode == "rel":
                offset = view[pc + 1]
                todo.append(pc + 2 + (offset - 256 if offset > 127 else offset))
            pc += 7 if mnemonic == "JSR" and arg == 0xC5C4 else LENGTHS.get(mode, 1)
    return sorted(exits)


def pinned(rom, bank, address, text):
    return read(rom, bank, address, len(bytes.fromhex(text))) == bytes.fromhex(text)



def scene_values(rom):
    """{value: [store sites]} for every store to $047B, and the stores no rule or review resolves."""
    stores = sites(rom, lambda op, mode, arg: op in LOAD_IMMEDIATE and mode == "abs" and arg == SCENE)
    targets = {bank: entries(rom, bank) for bank in {s[0] for s in stores}}
    values, unresolved = {}, []
    for bank, pc, op, _, _ in stores:
        load, value = immediate_before(rom, bank, pc, op)
        window = range(load + 1, pc + 1) if value is not None else range(pc, pc + 1)
        into = {s for t in window for s in targets[bank].get(t, ())}
        review = REVIEWED_SCENE_STORES.get((bank, pc))
        if review is not None:
            allowed, sources, contexts, _ = review
            found = allowed if into == sources and all(pinned(rom, *c) for c in contexts) else None
        else:
            found = {value} if value is not None and not into else None
        if found is None:
            unresolved.append(f"{bank}:${pc:04X}")
            continue
        for v in found:
            values.setdefault(v, []).append(f"{bank}:${pc:04X}")
    return stores, values, unresolved


def scene_checks(rom):
    stores, values, unresolved = scene_values(rom)
    reviewed = {k for k in REVIEWED_SCENE_STORES if read(rom, k[0], k[1], 3)[1:] == SCENE.to_bytes(2, "little")}
    steps = {bank: {(op, pc) for _, pc, op, *_ in sites(rom, lambda op, mode, arg: op in ("INC", "DEC") and mode == "abs"
                                                        and arg == SCENE, banks=(bank,))} for bank in SCENE_STEPS}
    handlers = {s: int.from_bytes(read(rom, model.FIXED, SCENE_TABLE + 2 * s, 2), "little") for s in PLAYER_SCENES}
    banks = {s: read(rom, model.FIXED, SCENE_BANKS + (s >> 1), 1)[0] for s in PLAYER_SCENES}
    chain_entries = {(b, pc) for b in range(16) for t, sources in entries(rom, b).items() if 0xD7F8 <= t <= 0xD813
                     for pc in sources if b == model.FIXED or read(rom, b, pc, 1)[0] in (0x20, 0x4C)}
    bank, address, size, digest = PLAYER
    return [
        Check("every store to the scene byte $047B writes an immediate or a reviewed value set",
              not unresolved and reviewed == set(REVIEWED_SCENE_STORES),
              f"{len(stores)} stores, {len(REVIEWED_SCENE_STORES)} reviewed" + (f"; unresolved {' '.join(unresolved)}"
                                                                             if unresolved else "")),
        Check("no store writes scene $1B, $1C or anything above $1D: scene $1C is the only one that selects sequence 5",
              not {0x1B, 0x1C} & set(values) and max(values) <= 0x1D,
              "values " + " ".join(f"${v:02X}" for v in sorted(values))),
        Check("the play exit's DEC $047B x3 ($D80B-$D811) runs by fall-through from scene 5's play countdown ($D7F6), "
              "from scene 5's home-run exit ($D790) and from SPEED's play wrapper ($F0AE), which stores $17 right "
              "after it: SPEED's $1D passes $1C and $1B there and never reaches the dispatcher",
              pinned(rom, model.FIXED, *PLAY_EXIT) and pinned(rom, model.FIXED, *SPEED_PLAY)
              and chain_entries == set(PLAY_EXIT_ENTRIES),
              " ".join(f"{b}:${pc:04X}" for b, pc in sorted(chain_entries - set(PLAY_EXIT_ENTRIES)))),
        Check("the scene steps are INC $98D1 ($12), $A8B2 ($1A), $A8CA ($1C) in bank 5 and the field scenes' own",
              steps == SCENE_STEPS, " ".join(f"{b}:{op} ${pc:04X}" for b in steps for op, pc in sorted(steps[b]))),
        Check("scenes $1A-$1D dispatch to bank 5 $A8A6, $A8D0, $A8B8, $A8D0",
              handlers == PLAYER_SCENES and set(banks.values()) == {5},
              " ".join(f"${s:02X}:{banks[s]}:${h:04X}" for s, h in handlers.items())),
        Check("bank 5 $A8A6-$A958: scene $1A clears $10 and steps to $1B; the player recomputes the sequence through "
              "$A930 (0-2, or 3-4 for VICTORY) while $10 is clear; only scene $1C sets $10 and $CC = 5",
              hashlib.sha256(read(rom, bank, address, size)).hexdigest() == digest
              and pinned(rom, 5, 0xA8A6, "20 9F CA 85 B8 8D 7A 04 85 CD 85 10 EE 7B 04")
              and pinned(rom, 5, 0xA8B8, "20 9F CA 85 B8 8D 7A 04 85 CD A9 01 85 10 A9 05 85 CC EE 7B 04")
              and pinned(rom, 5, 0xA8E8, "A5 10 D0 03 20 30 A9")
              and pinned(rom, 5, 0xA949, "02 00 01 02 A9 04 85 CC")),
    ]


def sequence_checks(rom):
    rows = [read(rom, 5, SEQUENCES + 8 * s, 8) for s in range(6)]
    screens = [int.from_bytes(read(rom, 5, SCREEN_DISPATCH + 5 + 2 * k, 2), "little") for k in range(6)]
    requests = {(b, pc): immediate_loader(rom, b, pc)
                for b, pc, *_ in sites(rom, lambda op, mode, arg: op == "JSR" and mode == "abs" and arg == 0xC6C1)
                if b != STALE_BANK}
    presets = [read(rom, model.FIXED, PRESET_TABLE + 6 * i, 6) for i in range(PRESETS)]
    controls = {(b, pc): immediate_loader(rom, b, pc)
                for b, pc, *_ in sites(rom, lambda op, mode, arg: op == "JSR" and mode == "abs" and arg == CONTROL_WRITER)
                if b != STALE_BANK}
    shadow = [pc for b, pc, *_ in sites(rom, lambda op, mode, arg: op == "STA" and mode == "zpg" and arg == CONTROL_SHADOW)
              if b != STALE_BANK]
    speed = sorted({pc for pc, _ in walk(rom, SPEED_EXIT) + walk(rom, 0xEE43)})
    selections = []
    for bank, pc, op, _, arg in sites(rom, lambda op, mode, arg: op in ("LDA", "LDX", "LDY") and mode == "imm"
                                      and arg in model.FRAME_CHR.values()):
        data, i = prg(rom, bank), pc - origin(bank) + 2
        for _ in range(3):
            if i >= len(data):
                break
            follow, mode, size, target = decode(data, i)
            if (follow == "ST" + op[2] and mode == "zpg" and target in (0x23, 0x24, 0x25, 0x26)) or (
                    follow == "JSR" and target in (0xC11C, 0xC134)):
                selections.append((bank, pc, arg))
                break
            i += size
    return [
        Check("sequence table $A959: screen 5 appears only in sequence 5",
              [r.count(SPLIT_SCREEN) for r in rows] == [0, 0, 0, 0, 0, 1], " ".join(r.hex() for r in rows)),
        Check("screen dispatch $AC5C: screen 5 is the split-screen draw at $AC6D, which then requests preset 6",
              pinned(rom, 5, SCREEN_DISPATCH, "A5 B9 20 32 C2") and screens[SPLIT_SCREEN] == 0xAC6D
              and pinned(rom, 5, 0xAC6D, "20 C4 C5 15 33 12 20 E6 B8 A9 06 20 C1 C6"),
              " ".join(f"${a:04X}" for a in screens)),
        Check("every CHR preset request ($C6C1) loads an immediate; preset 6 only at 5:$AC78",
              None not in requests.values() and [k for k, v in requests.items() if v == SPLIT_PRESET] == [SPLIT_REQUEST],
              " ".join(f"{b}:${pc:04X}=#{v}" for (b, pc), v in sorted(requests.items()))),
        Check("preset table $FB4D: CHR $15 only in preset 6, CHR $04 in none",
              [i for i, p in enumerate(presets) if model.FRAME_CHR["b"] in p[1:5]] == [SPLIT_PRESET]
              and not [i for i, p in enumerate(presets) if model.FRAME_CHR["a"] in p[1:5]]),
        Check("SPEED's scene $1D ($F0CA) is replaced by $17 ($EE3D) or $0A ($F0FA) before any return",
              speed == [0xEE42, 0xF0FF] and pinned(rom, model.FIXED, 0xEE3D, "A9 17 8D 7B 04 60")
              and pinned(rom, model.FIXED, 0xF0FA, "A9 0A 8D 7B 04 60"), " ".join(f"${pc:04X}" for pc in speed)),
        Check("no immediate $04 or $15 feeds a CHR shadow ($23-$26) or the CHR setters $C11C/$C134",
              not [s for s in selections if s[0] != STALE_BANK],
              " ".join(f"{b}:${pc:04X}=#${v:02X}" for b, pc, v in selections)),
        Check("MMC1 control: every $C102 call loads #$1E or #$1F (4 KB CHR banks); only $C102 stores $22",
              set(controls.values()) <= {0x1E, 0x1F} and shadow == [CONTROL_WRITER], f"{len(controls)} calls"),
    ]


def screen_checks(rom):
    calls = []
    for bank in range(16):
        data, start = prg(rom, bank), 0
        while (i := data.find(b"\x20\xC4\xC5", start)) >= 0:
            calls.append((bank, origin(bank) + i, data[i + 3:i + 7]))
            start = i + 1
    live = [c for c in calls if c[0] != STALE_BANK]
    records = {(b, pc): immediate_loader(rom, b, pc)
               for b, pc, *_ in sites(rom, lambda op, mode, arg: op == "JSR" and mode == "abs" and arg == 0xC1A4)
               if b != STALE_BANK}
    camera = read(rom, 2, 0x97C0, 0x100)
    return [
        Check("set $15 is drawn only with maps $24, $2A and $33",
              sorted(args[1] for _, _, args in live if args[0] == model.HR_SET)
              == sorted((model.HR_MAP, *model.SHARED_MAPS.values())),
              " ".join(f"{b}:${pc:04X} {a.hex()}" for b, pc, a in live if a[0] == model.HR_SET)),
        Check("map $24 and CHR1 $04/$15 are loader arguments only at fixed $D767",
              [(b, pc) for b, pc, a in live if a[1] == model.HR_MAP or a[2] in model.FRAME_CHR.values()]
              == [(model.FIXED, 0xD767)]),
        Check("state 3 flips CHR1 between $D793 = $04, $15",
              read(rom, model.FIXED, 0xD793, 2) == bytes(model.FRAME_CHR.values())),
        Check("palette record $0E is loaded by immediate only at $D75D",
              [k for k, v in records.items() if v == model.HR_RECORD] == [(model.FIXED, 0xD75F)]),
        Check("the bank-5 cutscene player's palette records exclude $0E", model.HR_RECORD not in read(rom, 5, 0xADD2, 12)),
        Check("the field camera table selects no palette $0E and no CHR $04 or $05",
              all(v >> 4 != model.HR_RECORD and v & 0x0F not in (4, 5) for v in camera)),
    ]


def checks(rom):
    """Every reader check on `rom`, in report order."""
    return scene_checks(rom) + sequence_checks(rom) + screen_checks(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roms", type=Path, nargs="+")
    args = ap.parse_args()
    failed = 0
    for path in args.roms:
        for c in checks(path.read_bytes()):
            failed += not c.ok
            print(f"{'PASS' if c.ok else 'FAIL'} {path.name}: {c.name}" + (f"  ({c.detail})" if c.detail else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
