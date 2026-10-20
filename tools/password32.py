#!/usr/bin/env python3
"""32-team / 5-round password model.

Format (8 bytes = 16 hex chars):

    bytes 0-3  seed, little-endian 32-bit
    bytes 4-7  result bits 0-30 (1 = team A wins), bit 31 = version (1)

The seed deterministically shuffles team ids 0-31 (Fisher-Yates with the
xorshift32 stream below).  Match m pairs slots 2m/2m+1 and writes the
winner to slot 32+m, exactly like the bank-11 heap.  Slot 62 is the
champion.

    python3 tools/password32.py test
    python3 tools/password32.py encode --seed 0x12345678 --results 0x...
    python3 tools/password32.py decode 123456789abcdef0
"""
import argparse
import random

VERSION_BIT = 31
LETTERS = "ABCDEFGHIJKLMNOP"
# Candidate stock password alphabet (bank5 $908B, 16 tile codes).
STOCK_TILES = bytes([0x35, 0x37, 0x48, 0x4A, 0x4B, 0x4D, 0x4F, 0x51,
                     0x53, 0x55, 0x65, 0x67, 0x68, 0x6A, 0x6C, 0x6E])


def xorshift32(state):
    state &= 0xFFFFFFFF
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def seed_order(seed):
    """Deterministic 32-team order from a 32-bit seed."""
    state = seed or 0x9E3779B9
    order = list(range(32))
    for i in range(31, 0, -1):
        state = xorshift32(state)
        j = state % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def advance(order, results):
    """Apply 31 result bits to the 63-slot heap; return the slots."""
    slots = list(order) + [None] * 31
    for m in range(31):
        a, b = slots[2 * m], slots[2 * m + 1]
        if a is None or b is None:
            raise ValueError(f"match {m}: empty source slot")
        slots[32 + m] = a if (results >> m) & 1 else b
    return slots


def encode(seed, results):
    seed &= 0xFFFFFFFF
    results &= (1 << VERSION_BIT) - 1
    bits = results | (1 << VERSION_BIT)
    raw = seed.to_bytes(4, "little") + bits.to_bytes(4, "little")
    return raw.hex()


def decode(text):
    raw = bytes.fromhex(text.strip())
    if len(raw) != 8:
        raise ValueError(f"expected 8 bytes / 16 hex chars, got {len(raw)}")
    seed = int.from_bytes(raw[0:4], "little")
    bits = int.from_bytes(raw[4:8], "little")
    if not (bits >> VERSION_BIT) & 1:
        raise ValueError("not a 32-team password (version bit clear)")
    results = bits & ((1 << VERSION_BIT) - 1)
    order = seed_order(seed)
    return seed, results, order, advance(order, results)


def encode_letters(seed, results):
    """Same 8-byte password, rendered as 16 letters (A-P)."""
    hexstr = encode(seed, results)
    return "".join(LETTERS[int(c, 16)] for c in hexstr)


def decode_letters(text):
    text = text.strip().upper()
    if len(text) != 16 or any(c not in LETTERS for c in text):
        raise ValueError("expected 16 letters A-P")
    hexstr = "".join(f"{LETTERS.index(c):X}" for c in text)
    return decode(hexstr)


def encode_stock(seed, results):
    """Same 8-byte password as the 16 stock tile codes."""
    return bytes(STOCK_TILES[int(c, 16)] for c in encode(seed, results))


def decode_stock(raw):
    raw = bytes(raw)
    if len(raw) != 16 or any(b not in STOCK_TILES for b in raw):
        raise ValueError("expected 16 stock tile codes")
    hexstr = "".join(f"{STOCK_TILES.index(b):X}" for b in raw)
    return decode(hexstr)


def test(rounds=100):
    rng = random.Random(0x50415353)
    for _ in range(rounds):
        seed = rng.getrandbits(32)
        results = rng.getrandbits(31)
        text = encode(seed, results)
        dseed, dres, order, slots = decode(text)
        assert dseed == seed and dres == results
        expected = advance(seed_order(seed), results)
        assert slots == expected
        assert slots[62] is not None
    for _ in range(rounds):
        seed = rng.getrandbits(32)
        results = rng.getrandbits(31)
        text = encode_letters(seed, results)
        dseed, dres, _, dslots = decode_letters(text)
        assert dseed == seed and dres == results
        assert dslots == advance(seed_order(seed), results)

    for _ in range(rounds):
        seed = rng.getrandbits(32)
        results = rng.getrandbits(31)
        raw = encode_stock(seed, results)
        dseed, dres, _, dslots = decode_stock(raw)
        assert dseed == seed and dres == results
        assert dslots == advance(seed_order(seed), results)

    # Known edge: seed 0 with all-A wins -> champion is the first seed.
    text = encode(0, (1 << 31) - 1)
    _, _, order, slots = decode(text)
    assert slots[62] == order[0]
    print(f"password32: {rounds} hex + {rounds} letter + {rounds} stock-tile "
          f"round-trips OK; champion all-A = {slots[62]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test")
    t.add_argument("--rounds", type=int, default=100)
    e = sub.add_parser("encode")
    e.add_argument("--seed", type=lambda s: int(s, 0), default=0)
    e.add_argument("--results", type=lambda s: int(s, 0), default=0)
    d = sub.add_parser("decode")
    d.add_argument("text")
    args = ap.parse_args()

    if args.cmd == "test":
        test(args.rounds)
    elif args.cmd == "encode":
        print(encode(args.seed, args.results))
    else:
        seed, results, order, slots = decode(args.text)
        print(f"seed=0x{seed:08X} results=0x{results:08X}")
        print("order:", " ".join(f"{x:02X}" for x in order))
        print("slots:", " ".join("--" if x is None else f"{x:02X}" for x in slots))
        print(f"champion: {slots[62]:02X}")


if __name__ == "__main__":
    main()
