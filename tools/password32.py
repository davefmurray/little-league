#!/usr/bin/env python3
"""Format-v1 passwords for the 32-team heap in bank 11.

The stock frame holds 22 symbols, or 110 bits. A 14-byte big-endian stream
has two implicit leading zero bits. Before whitening, its bytes are version
byte 08, seed, played, four little-endian result bytes, four little-endian CPU
mask bytes, reserved zero, and the big-endian CRC-16/CCITT-FALSE of bytes
0..11. Result bit m selects slot 2m+1 when set, slot 2m otherwise.
"""
import argparse
import random

ALPHABET = "1AKV5EPR2BLW6FGS3CMX78HT4DNY09JU"
ALIASES = {"I": "1", "O": "0", "Q": "9", "Z": "2"}
VALUE = {char: index for index, char in enumerate(ALPHABET)}
VALUE.update({alias: VALUE[char] for alias, char in ALIASES.items()})
VERSION = 1
MASK = bytes.fromhex("2181c9f0dc5ffb2996b1d38cd0aa")
SYMBOL_COUNT = 22


def _integer(name, value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")


def _results(played, results):
    _integer("played", played, 31)
    _integer("results", results, (1 << played) - 1)


def seed_order(seed):
    """Return the real $8200 seeder's order, seed followed by the other ids."""
    _integer("seed", seed, 31)
    return [seed] + [team for team in range(32) if team != seed]


def advance(order, played, results):
    """Return 63 heap slots, with None in each unplayed winner slot."""
    _results(played, results)
    try:
        order = list(order)
    except TypeError as error:
        raise ValueError("order must contain each team 0..31 exactly once") from error
    if (len(order) != 32 or any(type(team) is not int for team in order)
            or sorted(order) != list(range(32))):
        raise ValueError("order must contain each team 0..31 exactly once")
    heap = order + [None] * 31
    for match in range(played):
        heap[32 + match] = heap[2 * match + ((results >> match) & 1)]
    return heap


def crc16(data):
    """CRC-16/CCITT-FALSE, polynomial 1021, initial FFFF, no final XOR."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def to_bytes(seed, played, results, cpu_mask):
    """Return the canonical 14-byte payload before whitening."""
    _integer("seed", seed, 31)
    _results(played, results)
    _integer("cpu_mask", cpu_mask, 0xFFFFFFFF)
    payload = bytearray([VERSION << 3, seed, played])
    payload.extend(results.to_bytes(4, "little"))
    payload.extend(cpu_mask.to_bytes(4, "little"))
    payload.append(0)
    payload.extend(crc16(payload).to_bytes(2, "big"))
    return bytes(payload)


def encode(seed, played, results, cpu_mask):
    """Encode (seed, played, results, cpu_mask) as 22 canonical symbols."""
    payload = to_bytes(seed, played, results, cpu_mask)
    bits = int.from_bytes(bytes(byte ^ mask for byte, mask in zip(payload, MASK)), "big")
    return "".join(ALPHABET[(bits >> shift) & 31] for shift in range(105, -1, -5))


def decode(text):
    """Return (seed, played, results, cpu_mask), accepting spaces and aliases."""
    if not isinstance(text, str) or not text.isascii():
        raise ValueError("expected 22 ASCII password symbols")
    text = text.replace(" ", "").upper()
    if len(text) != SYMBOL_COUNT or any(char not in VALUE for char in text):
        raise ValueError("expected 22 password symbols from the stock alphabet")
    bits = 0
    for char in text:
        bits = (bits << 5) | VALUE[char]
    payload = bytes(byte ^ mask for byte, mask in zip(bits.to_bytes(14, "big"), MASK))
    if crc16(payload[:12]) != int.from_bytes(payload[12:], "big"):
        raise ValueError("password CRC mismatch")
    if payload[0] != VERSION << 3:
        raise ValueError("unsupported version or nonzero reserved bits")
    if (payload[1] | payload[2]) & 0xE0 or payload[6] & 0x80 or payload[11]:
        raise ValueError("nonzero reserved bits")
    seed, played = payload[1:3]
    results = int.from_bytes(payload[3:7], "little")
    _results(played, results)
    return seed, played, results, int.from_bytes(payload[7:11], "little")


def display(text):
    """Return the stock 26-byte display buffer for a valid v1 password."""
    text = encode(*decode(text))
    return (text[:6] + " " + text[6:12]).encode("ascii") + b"\xff" + (
        text[12:18] + " " + text[18:]).encode("ascii") + b"\xff"


def test(rounds=100):
    """Run deterministic host round trips and every one-symbol substitution."""
    _integer("rounds", rounds, 10000)
    rng = random.Random(0x5032)
    states = [(0, 0, 0, 0), (31, 31, 0x7FFFFFFF, 0xFFFFFFFF)]
    for _ in range(rounds):
        played = rng.randrange(32)
        states.append((rng.randrange(32), played, rng.getrandbits(played), rng.getrandbits(32)))
    substitutions = swaps = 0
    aliases = {value: key for key, value in ALIASES.items()}
    for state in states:
        text = encode(*state)
        assert decode(text) == state
        alias = "".join(aliases.get(char, char) for char in text)
        assert decode(alias) == state
        heap = advance(seed_order(state[0]), state[1], state[2])
        assert heap[32 + state[1]:] == [None] * (31 - state[1])
        for index, original in enumerate(text):
            for char in ALPHABET:
                if char == original:
                    continue
                try:
                    decode(text[:index] + char + text[index + 1:])
                except ValueError:
                    substitutions += 1
                else:
                    raise AssertionError("one-symbol substitution accepted")
        for index in range(SYMBOL_COUNT - 1):
            if text[index] == text[index + 1]:
                continue
            changed = text[:index] + text[index + 1] + text[index] + text[index + 2:]
            try:
                decode(changed)
            except ValueError:
                swaps += 1
            else:
                raise AssertionError("adjacent swap accepted")
    assert crc16(b"123456789") == 0x29B1
    assert advance(seed_order(31), 31, 0)[62] == 31
    assert advance(seed_order(31), 31, 0x7FFFFFFF)[62] == 30
    print(f"password32 v1: {len(states)} round trips with aliases; "
          f"{substitutions} substitutions and {swaps} adjacent swaps rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("test", help="run deterministic host checks and exhaustive substitutions")
    check.add_argument("--rounds", type=int, default=100)
    encoder = sub.add_parser("encode", help="encode the four v1 state fields")
    integer = lambda value: int(value, 0)
    encoder.add_argument("--seed", type=integer, default=0, help="first team id, 0..31")
    encoder.add_argument("--played", type=integer, default=0, help="matches played, 0..31")
    encoder.add_argument("--results", type=integer, default=0, help="bit m selects slot 2m+1; bits >= played are zero")
    encoder.add_argument("--cpu-mask", type=integer, default=0xFFFFFFFF, help="32 bits; set means CPU-controlled")
    decoder = sub.add_parser("decode", help="decode 22 symbols, allowing ASCII spaces and I/O/Q/Z aliases")
    decoder.add_argument("text")
    args = parser.parse_args()
    try:
        if args.command == "test":
            test(args.rounds)
        elif args.command == "encode":
            print(encode(args.seed, args.played, args.results, args.cpu_mask))
        else:
            seed, played, results, cpu_mask = decode(args.text)
            print(f"seed={seed} played={played} results=0x{results:08X} cpu_mask=0x{cpu_mask:08X}")
            print("order:", " ".join(f"{team:02X}" for team in seed_order(seed)))
            heap = advance(seed_order(seed), played, results)
            print("slots:", " ".join("--" if team is None else f"{team:02X}" for team in heap))
            if played == 31:
                print(f"champion: {heap[62]:02X}")
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
