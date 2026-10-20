#!/usr/bin/env python3
"""Generate a 32-team roster JSON from the 16-team base.

    python3 tools/gen_roster32.py data/roster.json data/teams32.json \
        -o data/roster32.json

Teams 0-15 are copied byte-for-byte. Teams 16-31 get 20 generated players
each: country-flavoured surnames (6 chars max), deterministic power/speed/
skill, three pitcher slots (8/16/24), and a 48-byte trailer with three
pitcher records. This is the data source for `build_extra_rosters.py`.
"""
import argparse
import json
import random

# 10 country-flavoured surnames per new team; truncated to 6 chars.
POOLS = {
    16: ["HARRIS", "WILSON", "TAYLOR", "BROWN", "CAMPBELL", "MURPHY", "KELLY", "RYAN", "WALKER", "HUGHES"],
    17: ["GARCIA", "RODRIG", "MARTIN", "LOPEZ", "GONZAL", "PEREZ", "SANCHE", "RAMOS", "TORRES", "DIAZ"],
    18: ["SANTOS", "REYES", "CRUZ", "JIMENE", "MENDEZ", "VARGAS", "CASTIL", "ORTIZ", "ROSARI", "PENA"],
    19: ["HERNAN", "SUAREZ", "BLANCO", "RIVAS", "MORA", "SILVA", "ACOSTA", "LEON", "PARRA", "VEGA"],
    20: ["CHAVEZ", "AROSEM", "BETHAN", "QUINTE", "GOMEZ", "MURGAS", "CEDENO", "ESPINO", "BARRIO", "SAAVED"],
    21: ["DEJONG", "VANDYK", "BAKKER", "VISSER", "SMIT", "MEIJER", "DEBOER", "MULDER", "GROOT", "JANSEN"],
    22: ["MULLER", "SCHMID", "SCHNEI", "FISCHE", "WEBER", "MEYER", "WAGNER", "BECKER", "HOFFMA", "KOCH"],
    23: ["NEL", "VANWYK", "BOTHA", "SMIT", "PRETOR", "JANSEN", "KRUGER", "FOURIE", "MOLEFE", "DLAMIN"],
    24: ["SILVA", "SANTOS", "OLIVEI", "SOUZA", "LIMA", "PEREIR", "COSTA", "ALMEID", "RIBEIR", "CARVAL"],
    25: ["GOMEZ", "RODRIG", "GUTIER", "MARTIN", "GARCIA", "LOPEZ", "HERRER", "MEDINA", "CASTRO", "ROJAS"],
    26: ["LOPEZ", "MARTIN", "GARCIA", "HERNAN", "MENDOZ", "URBINA", "LACAYO", "CENTEN", "SEQUEI", "BLANDO"],
    27: ["SANTOS", "REYES", "CRUZ", "GARCIA", "MENDOZ", "TORRES", "FLORES", "RAMOS", "BAUTIS", "VILLAN"],
    28: ["CHAN", "WONG", "LEE", "CHEUNG", "LAM", "NG", "HO", "YIP", "TSE", "LO"],
    29: ["CRUZ", "SANTOS", "PEREZ", "QUINAT", "TAITAN", "FLORES", "BLAS", "CAMACH", "MENDIO", "LEE"],
    30: ["SMITH", "JONES", "WILLIA", "BROWN", "TAYLOR", "WILSON", "THOMPS", "CLARK", "HARRIS", "MARTIN"],
    31: ["NOVAK", "SVOBOD", "DVORAK", "CERNY", "PROCHA", "KUCHAR", "VESELY", "HORAK", "NEMEC", "POKORN"],
}

GLOBAL = [
    "ADAMS", "ALVAREZ", "ANDERS", "BAKER", "BENNET", "BROOKS", "CARTER", "COLEMAN",
    "DAVIS", "DIXON", "EDWARDS", "ELLIS", "FOSTER", "GARCIA", "GRAY", "GREEN",
    "HALL", "HAMILT", "HARRIS", "HAYES", "HENDRIX", "HILL", "HOWARD", "HUDSON",
    "JACKSON", "JAMES", "JENKINS", "JOHNSON", "KELLY", "KENNEDY", "KING", "KNIGHT",
    "LARSON", "LAWREN", "LEWIS", "LONG", "MARTIN", "MASON", "MILLER", "MITCHEL",
    "MOORE", "MORGAN", "MORRIS", "MURPHY", "NELSON", "OLIVER", "PARKER", "PATTER",
    "PEARSON", "PERRY", "PETERS", "PHILLIP", "PORTER", "PRICE", "QUINN", "REED",
    "REYNOL", "RICE", "ROBERTS", "ROBINS", "ROGERS", "ROSS", "RUSSELL", "SANDERS",
    "SCOTT", "SHAW", "SIMMONS", "SMITH", "SNYDER", "STEVENS", "STONE", "SULLIVAN",
    "TAYLOR", "THOMAS", "THOMPS", "TURNER", "WALKER", "WALLACE", "WARREN", "WATSON",
    "WEAVER", "WELLS", "WEST", "WHITE", "WILLIAM", "WILSON", "WOODS", "WRIGHT",
    "YOUNG", "ZIMMER",
]


def name6(s):
    return s.upper()[:6].ljust(6)


def make_team(team_id, meta, rng):
    pool = list(POOLS[team_id])
    # Add 10 more names from the global pool, deterministically offset.
    start = (team_id * 7) % len(GLOBAL)
    for i in range(10):
        pool.append(GLOBAL[(start + i * 9) % len(GLOBAL)])
    # Deduplicate while preserving order.
    seen, names = set(), []
    for n in pool:
        n6 = name6(n)
        if n6 not in seen:
            seen.add(n6)
            names.append(n6)
    while len(names) < 20:
        names.append(name6(GLOBAL[len(names) % len(GLOBAL)]))

    players = []
    pitcher_slots = {0: 8, 1: 16, 2: 24}
    for p in range(20):
        skill = rng.randint(1, 4)
        power = rng.randint(40, 220)
        speed = rng.randint(40, 220)
        body = rng.choice([0, 1, 2, 128, 129, 130])
        slot = pitcher_slots.get(p, 0)
        attrs = [body, 255, rng.choice([0, 8, 16, 32, 64, 128]),
                 power, speed, skill, slot, 0, rng.choice([0, 2]), 0]
        players.append({"name": names[p], "padded": names[p],
                        "attrs": attrs})

    ratings = [rng.randint(1, 4) for _ in range(4)]
    return {
        "id": team_id,
        "name": meta["name"],
        "short_name": meta["name"],
        "short_width": 10,
        "short_attr": 4,
        "ratings": ratings,
        "players": players,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roster16", default="data/roster.json", nargs="?")
    ap.add_argument("teams32", default="data/teams32.json", nargs="?")
    ap.add_argument("-o", "--out", default="data/roster32.json")
    args = ap.parse_args()

    base = json.load(open(args.roster16))
    teams = json.load(open(args.teams32))["teams"]
    out = {"rom": base.get("rom", ""), "teams": list(base["teams"])}
    for tid in range(16, 32):
        rng = random.Random(0x4C4C0000 + tid)
        out["teams"].append(make_team(tid, teams[tid], rng))
    json.dump(out, open(args.out, "w"), indent=2)
    open(args.out, "a").write("\n")
    print(f"wrote {args.out}: {len(out['teams'])} teams")
    for t in out["teams"][16:18]:
        print(t["id"], t["name"], t["ratings"], [p["name"] for p in t["players"][:6]])


if __name__ == "__main__":
    main()
