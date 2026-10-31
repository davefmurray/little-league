"""Verified Little League (US) data map.

All values are CPU addresses in bank 4 unless noted. Sources:
`docs/datacrystal-rom-map.md`, `docs/prior-art-llbcs.md`.
"""

TEAM_NAMES = [
    "Japan", "Arizona", "Pennsylvania", "Chinese Taipei",
    "Korea", "New York", "California", "Texas",
    "Hawaii", "Spain", "Puerto Rico", "Mexico",
    "Canada", "Italy", "Illinois", "Florida",
]

# Roster bases, verified by reading the first player name at each address.
# The table is exactly $8420 + $120*team (Puerto Rico $8F60 and Mexico $9080
# included); it stays explicit so a board revision can differ per team.
TEAM_BASES = [
    0x8420, 0x8540, 0x8660, 0x8780,
    0x88A0, 0x89C0, 0x8AE0, 0x8C00,
    0x8D20, 0x8E40, 0x8F60, 0x9080,
    0x91A0, 0x92C0, 0x93E0, 0x9500,
]

RECORD = 16          # bytes per player row
PLAYERS = 15         # roster rows before the FF trailer
TRAILER = 0xF0       # base + 0xF0 = FF row
PITCHERS_AT = 0x18   # base + 0xF0 + 0x18 = first pitcher record

COLORS = 0xFAC0           # fixed bank: 16 x 3 bytes (cap and trim, jersey, hair),
                          # read by the palette routine at $FAC0 + 3*team
LINEUPS = 0x96CA          # 16 x 9 packed-nibble bytes
FLAGS = 0x976A            # 16 team flag records
POWER = 0xB224            # 16 x 4 power-analysis values


def base(team):
    return TEAM_BASES[team]


def trailer(team):
    return TEAM_BASES[team] + TRAILER
