#!/usr/bin/env python3
"""
gen3_extractor.py
Extracts all relevant game state from a Pokemon FireRed/LeafGreen save file.
Outputs JSON suitable for an AI agent to reason about.
"""

import struct
import json
import sys
from pathlib import Path

# ── Load FRLG lookup tables ──────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent / "oggen3_data" / "frlg"

def _load_json(filename: str) -> dict:
    p = _DATA_DIR / filename
    return json.loads(p.read_text()) if p.exists() else {}

_POKEMON_DATA:   dict = _load_json("pokemon_base.json")       # {str(dex_id): {name, types, ...}}
_MOVES_DATA:     dict = _load_json("moves.json")               # {str(move_id): {name, type, ...}}
_META:           dict = _load_json("meta.json")
_ITEM_NAMES:     dict = _META.get("items", {})                    # {str(item_id): str}
_NATURES:        list = _META.get("natures", [])                  # ordered list of 25 nature names
_LOCATION_NAMES: dict = _load_json("met_locations.json")       # {str(loc_id): str}


def _pokemon_name(species_id: int) -> str:
    return _POKEMON_DATA.get(str(species_id), {}).get("name", f"#{species_id}")

def _move_name(move_id: int) -> str:
    return _MOVES_DATA.get(str(move_id), {}).get("name", f"Move#{move_id}")

def _item_name(item_id: int) -> str:
    return _ITEM_NAMES.get(str(item_id), f"Item#{item_id}")

def _location_name(loc_id: int) -> str:
    return _LOCATION_NAMES.get(str(loc_id), f"Location#{loc_id}")

# ── Save layout ──────────────────────────────────────────────────────────────
SECTION_SIZE    = 0x1000        # 4096 bytes per section block
NUM_SECTIONS    = 14
SAVE_A_OFFSET   = 0x00000
SAVE_B_OFFSET   = 0x0E000
SECTION_SIG     = 0x08012025   # expected signature in every section footer

# Data bytes used per section ID (rest of the 4096-byte block is padding)
SECTION_DATA_SIZES = [3884, 3968, 3968, 3968, 3848,
                       3968, 3968, 3968, 3968, 3968,
                       3968, 3968, 3968, 2000]

# ── FRLG section offsets ──────────────────────────────────────────────────────
SEC0_PLAYER_NAME      = 0x0000   # 7 bytes
SEC0_GENDER           = 0x0008   # 1 byte  (0=male, 1=female)
SEC0_TRAINER_ID       = 0x000A   # 2 bytes public TID
SEC0_SECRET_ID        = 0x000C   # 2 bytes secret TID
SEC0_TIME_HOURS       = 0x000E   # 2 bytes
SEC0_TIME_MINUTES     = 0x0010   # 1 byte
SEC0_TIME_SECONDS     = 0x0011   # 1 byte
SEC0_SECURITY_KEY     = 0x0AF8   # 4 bytes — verified: XOR key for money/coins
SEC0_ALT_KEY          = 0x00AC   # 4 bytes — game code; XOR key for item quantities
SEC0_BADGE_BYTE       = 0x00C9   # 1 byte  — Kanto badge bitfield (community-documented)
SEC0_POKEDEX_SEEN     = 0x00B9   # 49 bytes (386 bits, National Dex seen)
SEC0_POKEDEX_OWNED    = 0x00DC   # 49 bytes (National Dex owned)

SEC1_TEAM_SIZE        = 0x0034   # 1 byte
SEC1_TEAM             = 0x0038   # 6 × 100 bytes
SEC1_MONEY            = 0x0290   # 4 bytes, XOR security_key
SEC1_COINS            = 0x0294   # 2 bytes, XOR (security_key & 0xFFFF)

# Item pockets in Section 1: (offset, max_slots)
ITEM_POCKETS = {
    'pc':        (0x0298, 30),
    'items':     (0x0310, 42),
    'key_items': (0x03B8, 30),
    'balls':     (0x0430, 13),
    'tms_hms':   (0x0464, 58),
    'berries':   (0x054C, 43),
}

# ── Pokemon encryption ────────────────────────────────────────────────────────
# Substructure order indexed by (personality_value % 24)
SUBSTRUCTURE_ORDER = [
    "GAEM","GAME","GEAM","GEMA","GMAE","GMEA",
    "AGEM","AGME","AEGM","AEMG","AMGE","AMEG",
    "EGAM","EGMA","EAGM","EAMG","EMGA","EMAG",
    "MGAE","MGEA","MAGE","MAEG","MEGA","MEAG",
]

# ── Character encoding (Gen III — both Western/English and Japanese) ──────────
# 0xFF terminates the string.
# Western: uppercase A-Z at 0x84-0x9D, lowercase a-z at 0x9E-0xB7
# Japanese: full-width A-Z at 0xBB-0xD4, full-width 0-9 at 0xA1-0xAA
# Both encodings are included; overlap regions default to Western in the
# 0x9E-0xB7 range (handled gracefully since Japanese saves use 0xBB+ for text).
CHAR_MAP: dict[int, str] = {
    # Accented uppercase
    0x00:" ", 0x01:"À", 0x02:"Á", 0x03:"Â", 0x04:"Ç",
    0x05:"È", 0x06:"É", 0x07:"Ê", 0x08:"Ë", 0x09:"Ì",
    0x0A:"Î", 0x0B:"Ï", 0x0C:"Ò", 0x0D:"Ó", 0x0E:"Ô",
    0x0F:"Œ", 0x10:"Ù", 0x11:"Ú", 0x12:"Û", 0x13:"Ñ",
    0x14:"ß",
    # Accented lowercase
    0x15:"à", 0x16:"á", 0x17:"ç", 0x18:"è", 0x19:"é",
    0x1A:"ê", 0x1B:"ë", 0x1C:"ì", 0x1D:"î", 0x1E:"ï",
    0x1F:"ò", 0x20:"ó", 0x21:"ô", 0x22:"œ", 0x23:"ù",
    0x24:"ú", 0x25:"û", 0x26:"ñ", 0x27:"º", 0x28:"ª",
    0x29:"&", 0x2A:"+",
    # Symbols
    0x34:"Lv", 0x35:"=", 0x36:";",
    0x40:"▯", 0x41:"¿", 0x42:"¡",
    0x43:"PK", 0x44:"MN", 0x4D:"Í",
    0x4E:"%", 0x4F:"(", 0x50:")",
    0x51:"â", 0x52:"í",
    0x57:"↑", 0x58:"↓", 0x59:"←", 0x5A:"→",
    0x5E:"ᵉ", 0x5F:"<", 0x60:">",
    # Spacing (0x61-0x67 all map to space variants)
    0x61:" ", 0x62:" ", 0x63:" ", 0x64:" ",
    0x65:" ", 0x66:" ", 0x67:" ",
    # Half-width digits (Western)
    0x6A:"0", 0x6B:"1", 0x6C:"2", 0x6D:"3", 0x6E:"4",
    0x6F:"5", 0x70:"6", 0x71:"7", 0x72:"8", 0x73:"9",
    # Punctuation
    0x74:"!", 0x75:"?", 0x76:".", 0x77:"-",
    0x78:"·", 0x79:"…", 0x7A:'"', 0x7B:'"',
    0x7C:"'", 0x7D:"'", 0x7E:"♂", 0x7F:"♀",
    0x80:"$", 0x81:",", 0x82:"×", 0x83:"/",
    # Half-width uppercase A–Z  (0x84–0x9D, Western)
    **{0x84 + i: chr(ord('A') + i) for i in range(26)},
    # Half-width lowercase a–z  (0x9E–0xB7, Western)
    **{0x9E + i: chr(ord('a') + i) for i in range(26)},
    # Misc (Western)
    0xC0:"►",
    0xF0:":", 0xF1:"Ä", 0xF2:"Ö", 0xF3:"Ü",
    0xF4:"ä", 0xF5:"ö", 0xF6:"ü",
    # Full-width digits ０–９ (0xA1–0xAA, Japanese)
    **{0xA1 + i: str(i) for i in range(10)},
    # Full-width uppercase Ａ–Ｚ (0xBB–0xD4, Japanese)
    **{0xBB + i: chr(ord('A') + i) for i in range(26)},
    # Full-width lowercase ａ–ｚ (0xD5–0xEE, Japanese)
    **{0xD5 + i: chr(ord('a') + i) for i in range(26)},
}

# ── Lookup tables ─────────────────────────────────────────────────────────────
KANTO_BADGES = [
    "Boulder Badge","Cascade Badge","Thunder Badge","Rainbow Badge",
    "Soul Badge","Marsh Badge","Volcano Badge","Earth Badge",
]

GAME_ORIGINS = {
    1:"Sapphire", 2:"Ruby", 3:"Emerald",
    4:"FireRed",  5:"LeafGreen", 15:"Colosseum/XD",
}

LANGUAGES = {1:"Japanese", 2:"English", 3:"French", 4:"Italian", 5:"German", 7:"Spanish"}

# ── Core utilities ────────────────────────────────────────────────────────────

def decode_string(raw: bytes, max_len: int) -> str:
    out = []
    for b in raw[:max_len]:
        if b == 0xFF:
            break
        out.append(CHAR_MAP.get(b, f"[{b:02X}]"))
    return "".join(out).strip()


def _section_checksum(block: bytes, sec_id: int) -> int:
    size = SECTION_DATA_SIZES[sec_id]
    total = 0
    for i in range(0, size, 4):
        total += struct.unpack_from("<I", block, i)[0]
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


def load_sections(save_data: bytes, base: int) -> dict[int, bytes]:
    sections: dict[int, bytes] = {}
    for i in range(NUM_SECTIONS):
        block = save_data[base + i * SECTION_SIZE: base + (i + 1) * SECTION_SIZE]
        sig = struct.unpack_from("<I", block, 0xFF8)[0]
        if sig != SECTION_SIG:
            continue
        sec_id = struct.unpack_from("<H", block, 0xFF4)[0]
        sections[sec_id] = block
    return sections


def get_active_sections(save_data: bytes) -> dict[int, bytes]:
    """Return sections from the save block with the higher save index."""
    def save_index(base: int) -> int:
        # Read from whichever physical block holds section 0
        for i in range(NUM_SECTIONS):
            block = save_data[base + i * SECTION_SIZE: base + (i + 1) * SECTION_SIZE]
            sec_id = struct.unpack_from("<H", block, 0xFF4)[0]
            sig    = struct.unpack_from("<I", block, 0xFF8)[0]
            if sig == SECTION_SIG and sec_id == 0:
                return struct.unpack_from("<I", block, 0xFFC)[0]
        return 0

    idx_a = save_index(SAVE_A_OFFSET)
    idx_b = save_index(SAVE_B_OFFSET)
    return load_sections(save_data, SAVE_A_OFFSET if idx_a >= idx_b else SAVE_B_OFFSET)

# ── Pokemon parsing ───────────────────────────────────────────────────────────

def _decrypt_substructures(raw: bytes) -> bytes:
    """XOR the 48-byte encrypted block with (PV ^ OT_ID)."""
    pv    = struct.unpack_from("<I", raw, 0)[0]
    ot_id = struct.unpack_from("<I", raw, 4)[0]
    key   = pv ^ ot_id
    dec   = bytearray(raw)
    for i in range(0, 48, 4):
        val = struct.unpack_from("<I", raw, 0x20 + i)[0] ^ key
        struct.pack_into("<I", dec, 0x20 + i, val)
    return bytes(dec)


def _get_sub(dec: bytes, letter: str, pv: int) -> bytes:
    order = SUBSTRUCTURE_ORDER[pv % 24]
    idx   = order.index(letter)
    return dec[0x20 + idx * 12: 0x20 + (idx + 1) * 12]


def parse_pokemon(raw: bytes, is_party: bool) -> dict | None:
    """Parse one Pokemon record.  Returns None for empty slots."""
    pv    = struct.unpack_from("<I", raw, 0)[0]
    ot_id = struct.unpack_from("<I", raw, 4)[0]
    if pv == 0 and ot_id == 0:
        return None

    dec  = _decrypt_substructures(raw)
    grow = _get_sub(dec, "G", pv)
    atk  = _get_sub(dec, "A", pv)
    evs  = _get_sub(dec, "E", pv)
    misc = _get_sub(dec, "M", pv)

    species = struct.unpack_from("<H", grow, 0)[0]
    if species == 0 or species > 440:          # sanity check
        return None

    held_item = struct.unpack_from("<H", grow, 2)[0]
    exp       = struct.unpack_from("<I", grow, 4)[0]
    friendship = grow[9]

    moves = [struct.unpack_from("<H", atk, i * 2)[0] for i in range(4)]
    pps   = list(atk[8:12])

    ev_hp, ev_atk, ev_def, ev_spe, ev_spa, ev_spd = evs[0:6]

    iv_word  = struct.unpack_from("<I", misc, 4)[0]
    ivs = {
        "hp":    iv_word & 0x1F,
        "atk":  (iv_word >>  5) & 0x1F,
        "def":  (iv_word >> 10) & 0x1F,
        "spe":  (iv_word >> 15) & 0x1F,
        "spa":  (iv_word >> 20) & 0x1F,
        "spd":  (iv_word >> 25) & 0x1F,
    }
    is_egg   = bool((iv_word >> 30) & 1)
    ability  = (iv_word >> 31) & 1

    origins  = struct.unpack_from("<H", misc, 2)[0]
    level_met    = origins & 0x7F
    game_origin  = (origins >> 7) & 0xF
    ball_used    = (origins >> 11) & 0xF
    ot_is_female = bool((origins >> 15) & 1)

    nickname = decode_string(raw[0x08:0x12], 10)
    language = LANGUAGES.get(raw[0x12], f"0x{raw[0x12]:02X}")
    ot_name  = decode_string(raw[0x14:0x1B], 7)

    mon: dict = {
        "species":      species,
        "species_name": _pokemon_name(species),
        "nickname":     nickname,
        "language":     language,
        "is_egg":       is_egg,
        "nature":       _NATURES[pv % 25],
        "ability_slot": ability,
        "exp":          exp,
        "friendship":   friendship,
        "held_item":    held_item,
        "held_item_name": _item_name(held_item) if held_item else None,
        "ot_name":      ot_name,
        "ot_id":        ot_id & 0xFFFF,
        "ot_secret_id": (ot_id >> 16) & 0xFFFF,
        "ot_is_female": ot_is_female,
        "met_location": misc[1],
        "met_location_name": _location_name(misc[1]),
        "level_met":    level_met,
        "game_origin":  GAME_ORIGINS.get(game_origin, game_origin),
        "ball_caught":  ball_used,
        "moves": [
            {"move_id": m, "move_name": _move_name(m), "pp": p, "pp_max": p}
            for m, p in zip(moves, pps) if m > 0
        ],
        "evs": {"hp": ev_hp, "atk": ev_atk, "def": ev_def,
                "spe": ev_spe, "spa": ev_spa, "spd": ev_spd},
        "ivs": ivs,
    }

    if is_party:
        mon["level"]      = raw[0x54]
        mon["status"]     = struct.unpack_from("<I", raw, 0x50)[0]
        mon["current_hp"] = struct.unpack_from("<H", raw, 0x56)[0]
        mon["max_hp"]     = struct.unpack_from("<H", raw, 0x58)[0]
        mon["stats"] = {
            "atk":  struct.unpack_from("<H", raw, 0x5A)[0],
            "def":  struct.unpack_from("<H", raw, 0x5C)[0],
            "spe":  struct.unpack_from("<H", raw, 0x5E)[0],
            "spa":  struct.unpack_from("<H", raw, 0x60)[0],
            "spd":  struct.unpack_from("<H", raw, 0x62)[0],
        }

    return mon

# ── Section parsers ───────────────────────────────────────────────────────────

def parse_trainer(sec0: bytes) -> dict:
    name      = decode_string(sec0[SEC0_PLAYER_NAME: SEC0_PLAYER_NAME + 7], 7)
    gender    = "female" if sec0[SEC0_GENDER] else "male"
    tid       = struct.unpack_from("<H", sec0, SEC0_TRAINER_ID)[0]
    sid       = struct.unpack_from("<H", sec0, SEC0_SECRET_ID)[0]
    hours     = struct.unpack_from("<H", sec0, SEC0_TIME_HOURS)[0]
    minutes   = sec0[SEC0_TIME_MINUTES]
    seconds   = sec0[SEC0_TIME_SECONDS]
    return {
        "name":         name,
        "gender":       gender,
        "trainer_id":   tid,
        "secret_id":    sid,
        "time_played":  f"{hours}h {minutes:02d}m {seconds:02d}s",
    }


def parse_party(sec1: bytes) -> list[dict]:
    size  = sec1[SEC1_TEAM_SIZE]
    party = []
    for i in range(min(size, 6)):
        raw = sec1[SEC1_TEAM + i * 100: SEC1_TEAM + (i + 1) * 100]
        mon = parse_pokemon(raw, is_party=True)
        if mon:
            party.append(mon)
    return party


def parse_boxes(sections: dict[int, bytes]) -> tuple[int, list[dict]]:
    """Reassemble PC buffer from sections 5–13, return (current_box, boxes)."""
    pc = bytearray()
    for sec_id in range(5, 14):
        block = sections.get(sec_id, bytes(SECTION_SIZE))
        limit = SECTION_DATA_SIZES[sec_id]
        pc.extend(block[:limit])

    current_box = struct.unpack_from("<I", pc, 0)[0]
    boxes       = []

    for box_num in range(14):
        name_off  = 0x8344 + box_num * 9
        box_name  = decode_string(pc[name_off: name_off + 9], 9) or f"BOX {box_num + 1}"
        mons      = []
        for slot in range(30):
            off = 4 + (box_num * 30 + slot) * 80
            raw = bytes(pc[off: off + 80])
            mon = parse_pokemon(raw, is_party=False)
            if mon:
                mon["slot"] = slot
                mons.append(mon)
        boxes.append({
            "box":        box_num + 1,
            "name":       box_name,
            "is_current": box_num == current_box,
            "count":      len(mons),
            "pokemon":    mons,
        })

    return current_box, boxes


def parse_items(sec1: bytes, alt_key: int) -> dict:
    """
    Item quantities use 'alt_key' (from sec0[0x00AC]).
    XOR key = (alt_key - 1) & 0xFFFF — verified: alt_key=1 on fresh saves → no XOR.
    """
    item_qty_key = (alt_key - 1) & 0xFFFF

    pockets: dict[str, list] = {}
    for pocket_name, (offset, max_slots) in ITEM_POCKETS.items():
        items = []
        for i in range(max_slots):
            off     = offset + i * 4
            item_id = struct.unpack_from("<H", sec1, off)[0]
            qty_raw = struct.unpack_from("<H", sec1, off + 2)[0]
            if item_id == 0:
                continue
            quantity = qty_raw ^ item_qty_key
            items.append({"item_id": item_id, "item_name": _item_name(item_id), "quantity": quantity})
        pockets[pocket_name] = items

    return pockets


def parse_pokedex(sec0: bytes) -> dict:
    seen, owned = [], []
    for num in range(386):
        byte_i = num >> 3
        bit_i  = num & 7

        seen_off  = SEC0_POKEDEX_SEEN  + byte_i
        owned_off = SEC0_POKEDEX_OWNED + byte_i

        if seen_off < len(sec0) and (sec0[seen_off] >> bit_i) & 1:
            seen.append(num + 1)
        if owned_off < len(sec0) and (sec0[owned_off] >> bit_i) & 1:
            owned.append(num + 1)

    return {
        "seen_count":  len(seen),
        "owned_count": len(owned),
        "seen":        seen,
        "owned":       owned,
    }


def parse_badges(sec0: bytes) -> dict:
    byte = sec0[SEC0_BADGE_BYTE]
    return {badge: bool((byte >> i) & 1) for i, badge in enumerate(KANTO_BADGES)}


# ── Main ──────────────────────────────────────────────────────────────────────

def extract(save_path: str) -> dict:
    save_data = Path(save_path).read_bytes()
    sections  = get_active_sections(save_data)

    sec0 = sections[0]
    sec1 = sections[1]

    security_key = struct.unpack_from("<I", sec0, SEC0_SECURITY_KEY)[0]
    alt_key      = struct.unpack_from("<I", sec0, SEC0_ALT_KEY)[0]

    money = struct.unpack_from("<I", sec1, SEC1_MONEY)[0] ^ security_key
    coins = struct.unpack_from("<H", sec1, SEC1_COINS)[0] ^ (security_key & 0xFFFF)

    current_box, boxes = parse_boxes(sections)

    total_boxed = sum(b["count"] for b in boxes)

    party = parse_party(sec1)

    return {
        "trainer":    parse_trainer(sec0),
        "money":      money,
        "coins":      coins,
        "pokedex":    parse_pokedex(sec0),
        "badges":     parse_badges(sec0),
        "party":      party,
        "party_size": len(party),
        "boxes":      boxes,
        "total_boxed": total_boxed,
        "current_box": current_box + 1,
        "items":      parse_items(sec1, alt_key),
    }


if __name__ == "__main__":
    path   = sys.argv[1] if len(sys.argv) > 1 else "my_firered_gamestate.sav"
    result = extract(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))