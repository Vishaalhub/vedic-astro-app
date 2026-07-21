"""
varga.py
--------
Computes divisional (Varga) charts from a planet's sidereal longitude.

Every varga uses the SAME two-step algorithm:
  1. Split each 30-degree sign into N equal parts -> find which part number
     (0-indexed) the planet's degree-in-sign falls into.
  2. Map that part number to an actual rasi using a "starting sign" rule
     that is specific to that varga (from Brihat Parashara Hora Shastra).

NOTE ON VARIANTS: A few vargas (notably D16, D20, D27, D40, D45, D60) have
more than one rule quoted across classical texts and modern software
(Parashara's Light, Jagannatha Hora, Shri Jyoti Star sometimes disagree by
one sign). The rules below follow the most widely used convention
(matches Jagannatha Hora's default). They are isolated in ELEMENT_START /
PARITY_START tables below specifically so you can swap in an alternate
school's rule later without touching the core engine.
"""

from __future__ import annotations
from typing import Callable, Dict, List
from app.ephemeris import SIGNS, sign_index, degree_in_sign

MOVABLE = {0, 3, 6, 9}    # Aries, Cancer, Libra, Capricorn
FIXED = {1, 4, 7, 10}     # Taurus, Leo, Scorpio, Aquarius
DUAL = {2, 5, 8, 11}      # Gemini, Virgo, Sagittarius, Pisces

FIRE = {0, 4, 8}          # Aries, Leo, Sagittarius
EARTH = {1, 5, 9}         # Taurus, Virgo, Capricorn
AIR = {2, 6, 10}          # Gemini, Libra, Aquarius
WATER = {3, 7, 11}        # Cancer, Scorpio, Pisces


def _sign_name(idx: int) -> str:
    return SIGNS[idx % 12]


def _count_forward(start_idx: int, steps: int) -> int:
    """Classical 'counting' is inclusive of the starting sign as step 0."""
    return (start_idx + steps) % 12


# ---------------------------------------------------------------------------
# Individual varga rules. Each function takes (sign_idx 0-11, part 0-indexed)
# and returns the resulting sign_idx (0-11).
# ---------------------------------------------------------------------------

def d1_rasi(sign_idx: int, part: int) -> int:
    return sign_idx


def d2_hora(sign_idx: int, part: int) -> int:
    # part 0 = first half (0-15deg), part 1 = second half (15-30deg)
    odd_sign = (sign_idx % 2 == 0)  # Aries=0 is odd-numbered (1st sign)
    if odd_sign:
        return 4 if part == 0 else 3   # Leo, then Cancer
    else:
        return 3 if part == 0 else 4   # Cancer, then Leo


def d3_drekkana(sign_idx: int, part: int) -> int:
    # part 0 -> same sign, part 1 -> 5th sign, part 2 -> 9th sign (trine)
    offset = [0, 4, 8][part]
    return _count_forward(sign_idx, offset)


def d4_chaturthamsa(sign_idx: int, part: int) -> int:
    # quadrant scheme: same, 4th, 7th, 10th sign from itself
    offset = [0, 3, 6, 9][part]
    return _count_forward(sign_idx, offset)


def d7_saptamsa(sign_idx: int, part: int) -> int:
    odd_sign = (sign_idx % 2 == 0)
    start = sign_idx if odd_sign else _count_forward(sign_idx, 6)  # 7th sign from it
    return _count_forward(start, part)


def d9_navamsa(sign_idx: int, part: int) -> int:
    if sign_idx in MOVABLE:
        start = sign_idx
    elif sign_idx in FIXED:
        start = _count_forward(sign_idx, 8)   # 9th sign from it
    else:  # DUAL
        start = _count_forward(sign_idx, 4)   # 5th sign from it
    return _count_forward(start, part)


def d10_dashamsa(sign_idx: int, part: int) -> int:
    odd_sign = (sign_idx % 2 == 0)
    start = sign_idx if odd_sign else _count_forward(sign_idx, 8)  # 9th sign from it
    return _count_forward(start, part)


def d12_dwadashamsa(sign_idx: int, part: int) -> int:
    return _count_forward(sign_idx, part)  # always sequential from same sign


def d16_shodashamsa(sign_idx: int, part: int) -> int:
    if sign_idx in MOVABLE:
        start = 0   # Aries
    elif sign_idx in FIXED:
        start = 4   # Leo
    else:
        start = 8   # Sagittarius
    return _count_forward(start, part)


def d20_vimshamsa(sign_idx: int, part: int) -> int:
    if sign_idx in MOVABLE:
        start = 0   # Aries
    elif sign_idx in FIXED:
        start = 8   # Sagittarius
    else:
        start = 4   # Leo
    return _count_forward(start, part)


def d24_chaturvimshamsa(sign_idx: int, part: int) -> int:
    odd_sign = (sign_idx % 2 == 0)
    start = 4 if odd_sign else 3   # Leo for odd, Cancer for even
    return _count_forward(start, part)


def d27_bhamsha(sign_idx: int, part: int) -> int:
    if sign_idx in FIRE:
        start = 0    # Aries
    elif sign_idx in EARTH:
        start = 3    # Cancer
    elif sign_idx in AIR:
        start = 6    # Libra
    else:
        start = 9    # Capricorn
    return _count_forward(start, part)


# D30 is classically UNEQUAL (5 planetary lords with unequal degree spans),
# not a plain 30-way equal split. Table = (upper_degree_bound, resulting_sign_idx)
_D30_ODD = [(5, 0), (10, 10), (18, 8), (25, 2), (30, 6)]     # Mars,Sat,Jup,Merc,Ven -> Ari,Aqu,Sag,Gem,Lib
_D30_EVEN = [(5, 1), (12, 5), (20, 11), (25, 9), (30, 7)]    # Ven,Merc,Jup,Sat,Mars -> Tau,Vir,Pis,Cap,Sco


def d30_trimshamsa(sign_idx: int, degree_in_sign_val: float, **_) -> int:
    odd_sign = (sign_idx % 2 == 0)
    table = _D30_ODD if odd_sign else _D30_EVEN
    for upper, result_sign in table:
        if degree_in_sign_val < upper:
            return result_sign
    return table[-1][1]


def d40_khavedamsa(sign_idx: int, part: int) -> int:
    odd_sign = (sign_idx % 2 == 0)
    start = 0 if odd_sign else 6   # Aries for odd, Libra for even
    return _count_forward(start, part)


def d45_akshavedamsa(sign_idx: int, part: int) -> int:
    if sign_idx in MOVABLE:
        start = 0   # Aries
    elif sign_idx in FIXED:
        start = 4   # Leo
    else:
        start = 8   # Sagittarius
    return _count_forward(start, part)


def d60_shashtiamsa(sign_idx: int, part: int) -> int:
    # Sequential count forward from the same sign, 60 parts (5 full cycles).
    return _count_forward(sign_idx, part)


# ---------------------------------------------------------------------------
# Registry: name -> (division count N, rule function, needs_raw_degree flag)
# ---------------------------------------------------------------------------
VARGA_REGISTRY: Dict[str, dict] = {
    "D1":  {"n": 1,  "label": "Rasi (Birth Chart)",     "fn": d1_rasi},
    "D2":  {"n": 2,  "label": "Hora (Wealth)",           "fn": d2_hora},
    "D3":  {"n": 3,  "label": "Drekkana (Siblings)",     "fn": d3_drekkana},
    "D4":  {"n": 4,  "label": "Chaturthamsa (Property/Fortune)", "fn": d4_chaturthamsa},
    "D7":  {"n": 7,  "label": "Saptamsa (Children)",     "fn": d7_saptamsa},
    "D9":  {"n": 9,  "label": "Navamsa (Marriage/Dharma)", "fn": d9_navamsa},
    "D10": {"n": 10, "label": "Dashamsa (Career)",       "fn": d10_dashamsa},
    "D12": {"n": 12, "label": "Dwadashamsa (Parents)",   "fn": d12_dwadashamsa},
    "D16": {"n": 16, "label": "Shodashamsa (Vehicles/Comforts)", "fn": d16_shodashamsa},
    "D20": {"n": 20, "label": "Vimshamsa (Spiritual Life)", "fn": d20_vimshamsa},
    "D24": {"n": 24, "label": "Chaturvimshamsa (Education)", "fn": d24_chaturvimshamsa},
    "D27": {"n": 27, "label": "Bhamsha/Nakshatramsa (Strengths/Weaknesses)", "fn": d27_bhamsha},
    "D30": {"n": 30, "label": "Trimshamsa (Misfortunes/Evils)", "fn": d30_trimshamsa, "unequal": True},
    "D40": {"n": 40, "label": "Khavedamsa (Maternal Legacy)", "fn": d40_khavedamsa},
    "D45": {"n": 45, "label": "Akshavedamsa (Paternal Legacy/General)", "fn": d45_akshavedamsa},
    "D60": {"n": 60, "label": "Shashtiamsa (Overall Past Karma)", "fn": d60_shashtiamsa},
}


def compute_varga(longitude: float, varga_key: str) -> dict:
    """
    Returns {sign, sign_index, part_index} for a single planet's longitude
    in the requested divisional chart.
    """
    meta = VARGA_REGISTRY[varga_key]
    s_idx = sign_index(longitude)
    deg_in_sign = degree_in_sign(longitude)
    n = meta["n"]

    if meta.get("unequal"):
        result_idx = meta["fn"](s_idx, deg_in_sign)
        part = None
    else:
        part_size = 30.0 / n
        part = int(deg_in_sign // part_size)
        part = min(part, n - 1)  # guard float rounding at 29.999...
        result_idx = meta["fn"](s_idx, part)

    return {
        "varga": varga_key,
        "label": meta["label"],
        "sign": _sign_name(result_idx),
        "sign_index": result_idx,
        "part_index": part,
    }


def compute_all_vargas(planet_longitudes: Dict[str, float],
                        keys: List[str] = None) -> Dict[str, Dict[str, dict]]:
    """
    planet_longitudes: {"Sun": 123.45, "Moon": 10.2, ...}
    Returns: {"D9": {"Sun": {...}, "Moon": {...}}, "D10": {...}, ...}
    """
    keys = keys or list(VARGA_REGISTRY.keys())
    result: Dict[str, Dict[str, dict]] = {}
    for key in keys:
        result[key] = {
            planet: compute_varga(lon, key)
            for planet, lon in planet_longitudes.items()
        }
    return result
