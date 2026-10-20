#!/usr/bin/env python3
"""Unit tests for the 32-team bracket table (no base ROM needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bracket import gen32, rounds, read_table


def main():
    recs = gen32()
    assert len(recs) == 31, len(recs)
    assert [len(r) for r in rounds(recs, 16)] == [16, 8, 4, 2, 1]

    dests = [d for _, _, d in recs]
    assert dests == list(range(32, 63)), dests

    # Simulate the first team winning every match: leaf 0 -> champion 62.
    heap = list(range(32)) + [None] * 31
    for a, b, dest in recs:
        assert heap[a] is not None and heap[b] is not None
        heap[dest] = heap[a]
    assert heap[62] == 0

    # Round 32 table is 93 bytes; check read_table at bank5 $8941.
    rom = bytearray(16 + 6 * 0x4000)
    base = 16 + 5 * 0x4000 + (0x8941 - 0x8000)
    for i, (a, b, d) in enumerate(recs):
        rom[base + i * 3:base + i * 3 + 3] = bytes([a, b, d])
    assert read_table(bytes(rom), records=31) == recs

    print("test_bracket32: 31 records, rounds 16/8/4/2/1, champion 62, "
          "table round-trip OK")


if __name__ == "__main__":
    main()
