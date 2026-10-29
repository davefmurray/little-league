#!/usr/bin/env python3
"""Series passwords: format v1 for legacy draws, format v2 for random draws.

    .venv/bin/python tools/password32v2.py encode --team 31 --played 24 --results 0x555555 \
        --cpu-mask 0x5AA55AA5 --draw-seed 0x1234
    .venv/bin/python tools/password32v2.py decode 4995FEC5ESTVP6KM5YCNYM

`team` is the selected team, which holds slot 0. `draw_seed` is the 14-bit
first-round draw of tools/draw32.py; 0 is the legacy ascending draw. The
frozen v1 module tools/password32.py is unchanged, and its `--seed` still
means the selected team.

A legacy series always uses v1, byte for byte, so the previous release can
read it. A random series uses v2. Both share the alphabet, whitening,
CRC-16/CCITT-FALSE and 22-symbol frame. v2 stores the draw seed in bits v1
requires to be zero, so the previous release rejects every v2 code.

v2 payload before whitening (results and mask little-endian, CRC big-endian):
  0      $10           version 2 in bits 3-5; bits 0-2 zero
  1      sss ttttt     t = selected team; s = draw seed bits 8-10
  2      sss ppppp     p = matches played; s = draw seed bits 11-13
  3-6    results       bit m set = second team won match m; bits >= played and bit 31 zero
  7-10   CPU mask      bit t set = team t is CPU-controlled
  11     draw seed bits 0-7
  12-13  CRC over bytes 0-11
A v2 code with draw seed 0 is not canonical and is rejected. An incompatible
later change needs a new version byte.
"""
import argparse
from dataclasses import dataclass

import draw32
import password32 as v1

V1_VERSION = v1.VERSION << 3
V2_VERSION = 2 << 3


def _integer(name, value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")


@dataclass(frozen=True, kw_only=True)
class Series:
    """Everything a password carries about a championship in progress."""
    team: int
    played: int
    results: int
    cpu_mask: int
    draw_seed: int

    def __post_init__(self):
        _integer("team", self.team, 31)
        _integer("played", self.played, 31)
        _integer("results", self.results, (1 << self.played) - 1)
        _integer("cpu_mask", self.cpu_mask, 0xFFFFFFFF)
        _integer("draw_seed", self.draw_seed, draw32.SEED_MAX)


def to_bytes(series):
    """The canonical 14-byte payload before whitening."""
    payload = bytearray(v1.to_bytes(series.team, series.played, series.results, series.cpu_mask))
    if series.draw_seed:
        payload[0] = V2_VERSION
        payload[1] |= (series.draw_seed >> 8 & 7) << 5
        payload[2] |= (series.draw_seed >> 11 & 7) << 5
        payload[11] = series.draw_seed & 0xFF
        payload[12:] = v1.crc16(payload[:12]).to_bytes(2, "big")
    return bytes(payload)


def frame(body):
    """22 symbols for any 12 payload bytes, with their CRC appended."""
    if len(body) != 12:
        raise ValueError("a payload body is 12 bytes")
    payload = bytes(body) + v1.crc16(body).to_bytes(2, "big")
    bits = int.from_bytes(bytes(byte ^ mask for byte, mask in zip(payload, v1.MASK)), "big")
    return "".join(v1.ALPHABET[(bits >> shift) & 31] for shift in range(105, -1, -5))


def encode(series):
    return frame(to_bytes(series)[:12])


def _payload(text):
    if not isinstance(text, str) or not text.isascii():
        return None
    text = text.replace(" ", "").upper()
    if len(text) != v1.SYMBOL_COUNT or any(char not in v1.VALUE for char in text):
        return None
    bits = 0
    for char in text:
        bits = (bits << 5) | v1.VALUE[char]
    return bytes(byte ^ mask for byte, mask in zip(bits.to_bytes(14, "big"), v1.MASK))


def decode(text):
    """The Series a valid v1 or v2 code describes. Raises ValueError otherwise.

    A v2 payload is normalised to its v1 equivalent and checked by the frozen
    v1 decoder, as the ROM's v2 gate does, so both versions share every
    reserved-bit, result and canonical-form rule."""
    try:
        team, played, results, cpu_mask = v1.decode(text)
    except ValueError as error:
        v1_error = error
    else:
        return Series(team=team, played=played, results=results, cpu_mask=cpu_mask, draw_seed=0)
    payload = _payload(text)
    if (payload is None or payload[0] != V2_VERSION
            or v1.crc16(payload[:12]) != int.from_bytes(payload[12:], "big")):
        raise v1_error
    draw_seed = payload[11] | (payload[1] >> 5) << 8 | (payload[2] >> 5) << 11
    if draw_seed == 0:
        raise ValueError("v2 password needs a nonzero draw seed")
    body = bytearray(payload[:12])
    body[0], body[1], body[2], body[11] = V1_VERSION, body[1] & 0x1F, body[2] & 0x1F, 0
    team, played, results, cpu_mask = v1.decode(frame(body))
    return Series(team=team, played=played, results=results, cpu_mask=cpu_mask, draw_seed=draw_seed)


def display(text):
    """The stock 26-byte display buffer the ROM encoder writes for a valid code."""
    text = encode(decode(text))
    return (text[:6] + " " + text[6:12]).encode("ascii") + b"\xff" + (
        text[12:18] + " " + text[18:]).encode("ascii") + b"\xff"


def heap(series):
    """The 63 bracket slots the series has reached; None marks an undecided winner."""
    return v1.advance(draw32.draw_order(series.team, series.draw_seed), series.played, series.results)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    integer = lambda value: int(value, 0)
    encoder = sub.add_parser("encode", help="encode a series; draw seed 0 emits a v1 code")
    encoder.add_argument("--team", type=integer, required=True, help="selected team id, 0..31")
    encoder.add_argument("--played", type=integer, default=0, help="matches played, 0..31")
    encoder.add_argument("--results", type=integer, default=0, help="bit m selects slot 2m+1; bits >= played are zero")
    encoder.add_argument("--cpu-mask", type=integer, default=0xFFFFFFFF, help="32 bits; set means CPU-controlled")
    encoder.add_argument("--draw-seed", type=integer, required=True, help="0 = legacy ascending draw, else 1..16383")
    decoder = sub.add_parser("decode", help="decode 22 symbols, allowing ASCII spaces and I/O/Q/Z aliases")
    decoder.add_argument("text")
    args = parser.parse_args()
    try:
        if args.command == "encode":
            print(encode(Series(team=args.team, played=args.played, results=args.results,
                                cpu_mask=args.cpu_mask, draw_seed=args.draw_seed)))
            return
        series = decode(args.text)
    except ValueError as error:
        parser.error(str(error))
    print(f"team={series.team} played={series.played} results=0x{series.results:08X} "
          f"cpu_mask=0x{series.cpu_mask:08X} draw_seed=0x{series.draw_seed:04X} "
          f"(v{2 if series.draw_seed else 1})")
    slots = heap(series)
    print("order:", " ".join(f"{team:02X}" for team in slots[:32]))
    print("slots:", " ".join("--" if team is None else f"{team:02X}" for team in slots))
    if series.played == 31:
        print(f"champion: {slots[62]:02X}")


if __name__ == "__main__":
    main()
