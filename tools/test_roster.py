#!/usr/bin/env python3
"""Team-color checks for the roster CLI, tools/roster.py, run as users run it.

    python3 tools/test_roster.py
    ROSTER_ROM16='Little League Baseball - Championship Series (USA).nes' \\
    ROSTER_ROM32=build/homerunart32.nes python3 tools/test_roster.py

Always, on a synthetic 16-team image: extract and apply the three-byte
"uniform" (cap, jersey, hair) records; ignore an old two-color "colors" object
that still matches the ROM and refuse one that was edited; refuse colors on a
32-team image; show the colors; refuse to write an output over an input; and
round-trip CLI extract -> Roster Lab import and export -> CLI extract through
web/rom.js (tools/web_colors_export.mjs). With the ROMs, the same on the real
16-team ROM, plus Preview 8's live colors in show32 and no bank-7 writes. It
needs Node for the round trip. Outputs go to a temporary directory.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import llbcs_map  # noqa: E402

HEADER, BANK = 16, 0x4000
STOCK_SHA = "58e038f10748b5531779a0b1fab07d1f5e3b8d7b0ca8b5f2a05cee42dfb8481e"
P8_SHA = "a66add03e811bbeb127a7867d82c512984d251693b116c9bd2ffbd65a4c2993b"
SHORT_WIDTHS = [10, 11, 13, 14, 10, 11, 12, 10, 10, 10, 12, 10, 10, 10, 11, 10]
SLOTS = ("cap", "jersey", "hair")
OLD_COLORS_NOTICE = "Older roster.py versions read them from the wrong bytes"


def prg(bank, cpu):
    return HEADER + bank * BANK + cpu - (0xC000 if bank == 7 else 0x8000)


COLORS16 = prg(7, 0xFAC0)          # 0x1FAD0: team t's cap, jersey, hair at + 3t


def synthetic_stock():
    """A 16-team image with valid tables at the measured offsets; filler elsewhere."""
    data = bytearray((i * 31 + 7) & 0xFF for i in range(HEADER + 8 * BANK + 16 * 0x2000))
    data[:HEADER] = bytes([0x4E, 0x45, 0x53, 0x1A, 8, 16, 0x10, 0]) + bytes(8)
    entry = prg(1, 0x92A0)
    for t in range(16):
        data[prg(1, 0x9180 + 16 * t):prg(1, 0x9190 + 16 * t)] = f"CLUB {t}".ljust(14).encode() + b"\xff\xff"
        cpu = entry - prg(1, 0x8000) + 0x8000
        data[prg(1, 0x9280 + 2 * t):prg(1, 0x9282 + 2 * t)] = cpu.to_bytes(2, "little")
        width = SHORT_WIDTHS[t]
        data[entry:entry + width + 2] = bytes([4]) + f"C{t}".ljust(width).encode() + b"\xff"
        entry += width + 2
        data[prg(3, 0xB224 + 4 * t):prg(3, 0xB228 + 4 * t)] = bytes((t + r) % 4 + 1 for r in range(4))
        base = prg(4, 0x8420 + 0x120 * t)
        for p in range(15):
            skill = 7 if (t, p) == (4, 2) else (t + p) % 5
            attrs = [p % 3, 0xFF, p * 4, (t * 16 + p) & 0xFF, 0x90 | ((t + p) & 15), skill, 8 * (p + 1) if p < 3 else 0, 0, p % 3, 0]
            data[base + 16 * p:base + 16 * p + 16] = f"T{t:02d}P{p:02d}".encode() + bytes(attrs)
        data[base + 0xF0:base + 0x100] = b"\xff" * 16
        data[prg(4, 0x96CA + 9 * t):prg(4, 0x96D3 + 9 * t)] = bytes((i << 4) | (i + 1) for i in range(9))
        data[COLORS16 + 3 * t:COLORS16 + 3 * t + 3] = bytes([(5 * t + 1) & 63, [0x0D, 0x1D, 0x2E, 0x30][t & 3], (9 * t + 2) & 63])
    return bytes(data)


def synthetic_32():
    """A 32-team-sized image (16 PRG banks): the CLI must never write colors to its stale bank 7."""
    data = bytearray(HEADER + 16 * BANK + 16 * 0x2000)
    data[:HEADER] = bytes([0x4E, 0x45, 0x53, 0x1A, 16, 16, 0x10, 0]) + bytes(8)
    stock = synthetic_stock()
    for bank in (1, 3, 4, 7):
        data[HEADER + bank * BANK:HEADER + (bank + 1) * BANK] = stock[HEADER + bank * BANK:HEADER + (bank + 1) * BANK]
    team16 = HEADER + 8 * BANK + 16 * 0x170
    data[team16:team16 + 6] = b"HIGH16"          # the bank-8 roster block roster.py uses to spot a 32-team build
    for t in range(16, 32):
        data[prg(1, 0xBCC0 + 8 * (t - 16)):prg(1, 0xBCC8 + 8 * (t - 16))] = f"HIGH{t}".ljust(7).encode() + b"\xff"
    return bytes(data)


def cli(*args, check=True):
    result = subprocess.run([sys.executable, str(TOOLS / "roster.py"), *map(str, args)], capture_output=True, text=True)
    if check and result.returncode:
        raise AssertionError(f"roster.py {' '.join(map(str, args))} failed: {result.stderr}")
    return result


def fresh(scratch, name):
    path = Path(scratch) / name
    assert not path.exists(), f"{path} already exists"
    return path


def extract(scratch, rom, name):
    out = fresh(scratch, name)
    cli("extract", rom, "-o", out)
    return json.loads(out.read_text())


def apply(scratch, rom, doc, name, check=True):
    doc_path = fresh(scratch, f"{name}.json")
    doc_path.write_text(json.dumps(doc))
    out = fresh(scratch, name)
    result = cli("apply", rom, doc_path, "-o", out, check=check)
    return (out.read_bytes() if out.exists() else None), result


def changed(a, b):
    return [i for i in range(len(a)) if a[i] != b[i]]


def old_colors(rom, t):
    """What older roster.py versions exported as "colors": $FAC0 + t and $FAD0 + t of bank 7."""
    return {"primary": rom[COLORS16 + t], "secondary": rom[COLORS16 + 16 + t]}


def check_stock(scratch, path, label):
    rom = Path(path).read_bytes()
    doc = extract(scratch, path, f"{label}-extract.json")
    assert doc["palette"] == "nes-2c02-6bit-v1"
    assert all("colors" not in team for team in doc["teams"])
    for t, team in enumerate(doc["teams"]):
        assert team["uniform"] == dict(zip(SLOTS, rom[COLORS16 + 3 * t:COLORS16 + 3 * t + 3])), (label, t)
        assert list(team)[:8] == ["id", "name", "short_name", "short_width", "short_attr", "ratings", "uniform", "lineup"]
    same, _ = apply(scratch, path, doc, f"{label}-same.nes")
    assert same == rom, f"{label}: extract -> apply is byte-identical"

    edited = json.loads(json.dumps(doc))
    edited["teams"][5]["uniform"]["jersey"] = 0x30
    out, _ = apply(scratch, path, edited, f"{label}-jersey.nes")
    assert changed(out, rom) == ([COLORS16 + 16] if rom[COLORS16 + 16] != 0x30 else []), "team 5's jersey is one byte at 0x1FAE0"
    assert COLORS16 + 16 == 0x1FAE0

    old = json.loads(json.dumps(doc))
    del old["palette"]
    for t, team in enumerate(old["teams"]):
        del team["uniform"]
        team["colors"] = old_colors(rom, t)
    out, _ = apply(scratch, path, old, f"{label}-old.nes")
    assert out == rom, f"{label}: an old extract applies with no color change"
    for t in (0, 9):
        old["teams"][t]["colors"]["secondary"] ^= 0x01
    out, result = apply(scratch, path, old, f"{label}-old-edited.nes", check=False)
    assert result.returncode and out is None, f"{label}: edited old colors are refused and nothing is written"
    names = [doc["teams"][t]["name"] for t in (0, 9)]
    assert f"team 0 ({names[0]}), team 9 ({names[1]})" in result.stderr and OLD_COLORS_NOTICE in result.stderr, result.stderr

    for i, (bad, why) in enumerate((({"cap": 1, "jersey": 2}, "exactly cap, jersey and hair"),
                                    ({"cap": 1, "jersey": 2, "hair": 64}, "not 64"), ({"cap": True, "jersey": 2, "hair": 3}, "not True"),
                                    ({"cap": 1.0, "jersey": 2, "hair": 3}, "not 1.0"), ({"cap": "15", "jersey": 2, "hair": 3}, "not '15'"),
                                    ({"cap": 1, "jersey": 2, "hair": 3, "trim": 4}, "exactly cap, jersey and hair"))):
        bad_doc = json.loads(json.dumps(doc))
        bad_doc["teams"][2]["uniform"] = bad
        out, result = apply(scratch, path, bad_doc, f"{label}-bad-{i}.nes", check=False)
        assert result.returncode and out is None and why in result.stderr, (bad, result.stderr)
    wrong = json.loads(json.dumps(doc))
    wrong["palette"] = "rgb"
    out, result = apply(scratch, path, wrong, f"{label}-palette.nes", check=False)
    assert result.returncode and out is None and "unknown team color palette" in result.stderr

    shown = show_lines(path)
    for t in range(16):
        assert f" c {rom[COLORS16 + 3 * t]:02X}/{rom[COLORS16 + 3 * t + 1]:02X}/{rom[COLORS16 + 3 * t + 2]:02X} " in shown[t + 1]
    return doc


def check_round_trip(scratch, path, doc, label, synthetic):
    """CLI extract -> Roster Lab import and export -> CLI extract; the CLI's own apply writes the same bytes."""
    rom = Path(path).read_bytes()
    edited = json.loads(json.dumps(doc))
    edited["teams"][3]["uniform"] = {"cap": 0x16, "jersey": 0x3E, "hair": 0x0D}
    doc_path = fresh(scratch, f"{label}-web.json")
    doc_path.write_text(json.dumps(edited))
    web = fresh(scratch, f"{label}-web.nes")
    subprocess.run(["node", str(TOOLS / "web_colors_export.mjs"), *(["--synthetic"] if synthetic else []), str(path), str(web),
                    f"import:{doc_path}"], check=True, stdout=subprocess.DEVNULL)
    again = extract(scratch, web, f"{label}-web-extract.json")
    assert [t["uniform"] for t in again["teams"]] == [t["uniform"] for t in edited["teams"]], label
    cli_out, _ = apply(scratch, path, edited, f"{label}-cli.nes")
    assert cli_out == web.read_bytes(), f"{label}: Roster Lab and the CLI write the same bytes"
    assert changed(web.read_bytes(), rom) == [i for i in range(COLORS16 + 9, COLORS16 + 12) if rom[i] != edited["teams"][3]["uniform"][SLOTS[i - COLORS16 - 9]]]


def check_32(scratch, path, label, real=False):
    rom = Path(path).read_bytes()
    doc = extract(scratch, path, f"{label}-extract.json")
    assert "palette" not in doc and all("uniform" not in t and "colors" not in t for t in doc["teams"]), "no colors from a 32-team ROM"
    with_colors = json.loads(json.dumps(doc))
    with_colors["teams"][0]["uniform"] = {"cap": 1, "jersey": 2, "hair": 3}
    out, result = apply(scratch, path, with_colors, f"{label}-uniform.nes", check=False)
    assert result.returncode and out is None and "Edit 32-team colors in Roster Lab" in result.stderr, result.stderr
    old = json.loads(json.dumps(doc))
    for t, team in enumerate(old["teams"]):
        team["colors"] = old_colors(rom, t)
    out, _ = apply(scratch, path, old, f"{label}-old.nes")
    assert out[COLORS16:COLORS16 + 48] == rom[COLORS16:COLORS16 + 48], "no stale bank-7 color writes"
    if real:
        assert out[0x3FAD0:0x3FB00] == rom[0x3FAD0:0x3FB00] and out[0x3F389:0x3F410] == rom[0x3F389:0x3F410]
    old["teams"][1]["colors"]["primary"] ^= 0x01
    out, result = apply(scratch, path, old, f"{label}-old-edited.nes", check=False)
    assert result.returncode and out is None and 'edit 32-team colors in Roster Lab' in result.stderr
    return show_lines(path)


def show_lines(path):
    """show's output rows; names decoded from filler bytes can hold characters str.splitlines() treats as breaks."""
    return cli("show", path).stdout.rstrip("\n").split("\n")


def check_guards(scratch, path):
    copy = fresh(scratch, "guard.nes")
    copy.write_bytes(Path(path).read_bytes())
    before = copy.read_bytes()
    for args in (("extract", copy, "-o", copy), ("patch", copy, "--team", "0", "--slot", "0", "--name", "X", "-o", copy)):
        result = cli(*args, check=False)
        assert result.returncode and "is one of this command's inputs" in result.stderr, result.stderr
    doc_path = fresh(scratch, "guard.json")
    cli("extract", copy, "-o", doc_path)
    for target in (copy, doc_path):
        result = cli("apply", copy, doc_path, "-o", target, check=False)
        assert result.returncode and "is one of this command's inputs" in result.stderr
    assert copy.read_bytes() == before and json.loads(doc_path.read_text())["teams"]


def main():
    assert llbcs_map.COLORS == 0xFAC0
    assert not hasattr(llbcs_map, "COLOR_PRIMARY") and not hasattr(llbcs_map, "COLOR_SECONDARY")
    stale = {
        "README.md": ["| Team colours | `0x1FAD0`, `0x1FAE0` | 16 bytes each |"],
        "docs/game-writeup.md": ["| Team colours | `0x1FAD0`, `0x1FAE0` | 16 + 16 bytes |"],
        "docs/datacrystal-rom-map.md": ["## Team colours — two 16-byte tables", "**two tables of 16**", "grouping is wrong",
                                        "Colour model: two 16-byte tables", "primary colour"],
        "docs/roster-format.md": ["**two 16-byte tables**", "| Team colors (second set) |", "Two 16-byte tables at `$FAC0`",
                                  "Exact palette interpretation is unverified."],
        "docs/expanding-teams-and-rosters.md": ["`$FAC0`, `$FAD0` (bank 7) | 16 + 16 palette bytes | 32 + 32"],
        "docs/prior-art-llbcs.md": ["3-byte model is WRONG", "the ROM show **two 16-byte tables**"],
    }
    for doc, claims in stale.items():
        text = (TOOLS.parent / doc).read_text()
        for claim in claims:
            assert claim not in text, f"{doc} still says {claim!r}"
        assert "cap" in text and "jersey" in text, f"{doc} names the three color bytes"
    print("L5: llbcs_map has one COLORS table; the docs drop the two-table color claims")

    with tempfile.TemporaryDirectory() as scratch:
        stock = fresh(scratch, "synthetic-16.nes")
        stock.write_bytes(synthetic_stock())
        doc = check_stock(scratch, stock, "synthetic")
        print("L1/L2 synthetic: extract writes uniform from 0x1FAD0 + 3t; apply writes only those bytes; "
              "an unchanged old two-color extract is a no-op and edited ones are refused, naming the teams")
        check_round_trip(scratch, stock, doc, "synthetic", synthetic=True)
        print("L4 synthetic: CLI extract -> Roster Lab import/export -> CLI extract keeps every color; the CLI writes the same bytes")
        big = fresh(scratch, "synthetic-32.nes")
        big.write_bytes(synthetic_32())
        lines = check_32(scratch, big, "synthetic-32")
        assert len(lines) == 33 and all(" c --/--/-- " in line for line in lines[1:]), "unknown 32-team builds show --"
        print("L3 synthetic: a 32-team image extracts no colors, refuses uniform writes, never writes bank 7, and show32 prints --")
        check_guards(scratch, stock)
        print("outputs: extract, patch and apply refuse to write over their inputs")

        stock_path, p8_path = os.environ.get("ROSTER_ROM16"), os.environ.get("ROSTER_ROM32")
        if not (stock_path and p8_path):
            print("SKIPPED real-ROM checks: set ROSTER_ROM16 and ROSTER_ROM32 to the accepted ROMs")
            return
        stock_rom, p8_rom = Path(stock_path).read_bytes(), Path(p8_path).read_bytes()
        assert hashlib.sha256(stock_rom).hexdigest() == STOCK_SHA and hashlib.sha256(p8_rom).hexdigest() == P8_SHA
        doc = check_stock(scratch, stock_path, "real16")
        assert doc["teams"][0]["uniform"] == {"cap": 0x05, "jersey": 0x20, "hair": 0x0F}
        check_round_trip(scratch, stock_path, doc, "real16", synthetic=False)
        print("L1/L2/L4 real 16-team ROM: as above; team 5's jersey edit is exactly byte 0x1FAE0")
        lines = check_32(scratch, p8_path, "real32", real=True)
        assert " c 1B/2B/0F " in lines[4] and " c 1B/2B/0F " in lines[20], "as built, teams 4 and 20 share a record"
        own = fresh(scratch, "venezuela.nes")
        subprocess.run(["node", str(TOOLS / "web_colors_export.mjs"), p8_path, str(own), "venezuela"], check=True, stdout=subprocess.DEVNULL)
        own_lines = show_lines(own)
        assert " c 16/30/38 " in own_lines[20] and " c 1B/2B/0F " in own_lines[4], "show32 reads the own-colors table"
        print("L3 real Preview 8: no colors extracted, uniform writes refused, no bank-7 writes; show32 prints the live "
              "shared records as built and each team's own record after Roster Lab's upgrade")
        assert Path(stock_path).read_bytes() == stock_rom and Path(p8_path).read_bytes() == p8_rom, "a source ROM changed"
        print("source ROMs unchanged")


if __name__ == "__main__":
    main()
