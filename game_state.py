"""
FireRed (U) — Squirrels ROM — RAM game-state reader.

Run get_game_mode(core) after core.run_frame() to print a labelled dump of the
addresses that tell us what mode the game is in.

Memory API: core.memory.u8[addr], core.memory.u16[addr], core.memory.u32[addr]

------------------------------------------------------------------------------
Calibration story (why these addresses)
------------------------------------------------------------------------------
The original table guessed fixed EWRAM offsets for the save block and had no
signal at all for "a cutscene / script is running". That meant the recap that
this ROM plays on Continue ("Previously on your quest...") was reported as
OVERWORLD (free roam), because the field engine's callback1 runs during scripted
cutscenes exactly as it does during free roam — callback1 alone cannot tell them
apart.

Two signals fix this, both verified empirically against the live ROM. The lock
byte was found by diffing RAM: it is the byte that stays 1 throughout the locked
recap, is 0 across many free-roam frames, and is also 1 while the Start menu is
open (the only such byte).

  * gSaveBlock1Ptr (0x03005008) holds a *pointer* to SaveBlock1 in EWRAM. The
    player's live coords and map id live at fixed offsets inside it. We follow
    the pointer every frame, so this self-adjusts to wherever the save block
    lands — no hardcoded EWRAM offset to drift. The pointer is 0 until the save
    is loaded, which doubles as an "in game yet?" check.

  * FIELD_LOCK (0x02002D50, u8) is the field-control lock. It reads 1 whenever
    something other than the player has control of the field — a cutscene, a
    running map script, a dialog box, or the open Start menu — and 0 during
    free roam. Verified: 1 for the whole "Previously on your quest" recap
    (frames 496-735 of a fresh boot), flips to 0 the moment full-colour free
    roam begins, stays 0 while walking/standing, and goes 1 again while the
    Start menu is open.

The save pointer is read live every frame, and is 0 until the save loads, so
reading coords/map before the overworld simply reports "save not loaded"
instead of garbage.
"""

# ---------------------------------------------------------------------------
# Memory read helpers
# ---------------------------------------------------------------------------

def _r8(core, addr: int) -> int:
    return core.memory.u8[addr] & 0xFF

def _r16(core, addr: int) -> int:
    return core.memory.u16[addr] & 0xFFFF

def _r32(core, addr: int) -> int:
    return core.memory.u32[addr] & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Verified addresses — FireRed (U) "Squirrels" build
# ---------------------------------------------------------------------------

# gMain struct (IWRAM). callback1 changes on every major mode switch.
GMAIN_CB1   = 0x030030F4   # top-level mode fn ptr
GMAIN_CB2   = 0x030030FC   # sub-state fn ptr
GMAIN_STATE = 0x03003104   # sub-state step counter

# gSaveBlock1Ptr (IWRAM) -> SaveBlock1 (EWRAM). Follow the pointer, then read
# these offsets inside the block.
SAVEBLOCK1_PTR = 0x03005008
SB1_X        = 0x00   # u16  player x
SB1_Y        = 0x02   # u16  player y
SB1_MAPGROUP = 0x04   # u8
SB1_MAPNUM   = 0x05   # u8

# Field-control lock. 1 whenever a SCRIPT, CUTSCENE, MENU, MAP TRANSITION, or an
# NPC conversation has control; 0 during free roam. Verified 1 for: save-select,
# map warp/load, the Continue recap, the overworld Start menu, and talking to an
# NPC (a Poke Center nurse reads 1 the whole interaction).
#
# CAVEAT (verified): it stays 0 for signpost / "tips sign" style messages. Those
# pop a message box but never engage this lock, so field_locked alone canNOT
# tell free roam from a signpost dialogue. That is the case that slipped through
# (a "...TRAINER tips signs" message read field_locked=0). See _classify_mode.
FIELD_LOCK = 0x02002D50

# Battle data (EWRAM).
#
# IMPORTANT: neither of these resets when a battle ends -- both RETAIN their last
# value out in the overworld (verified: after a wild fight, callback1 is back to
# Overworld but gBattleTypeFlags still reads 0x04 and gBattleOutcome still reads
# the result). So they are ONLY meaningful while we are actually in a battle.
# "Are we in a battle?" must be answered by callback1 == CB1_BATTLE, NOT by these.
BATTLE_TYPE_FLAGS = 0x02022B4C   # while in battle: wild single = 0x04
                                 # (BATTLE_TYPE_IS_MASTER); trainer adds 0x08.
# gBattleOutcome (verified address for this build by forcing a win and a run):
# 0 while the battle is ongoing; set at the end. 1=won 2=lost 3=drew 4=ran
# 5=teleported 6=wild fled 7=caught. (The old 0x020244EC was wrong -- it read
# junk like 68/200.)
BATTLE_OUTCOME    = 0x02023E8A

# EWRAM address window, used to sanity-check the save-block pointer.
EWRAM_LO = 0x02000000
EWRAM_HI = 0x02040000


# ---------------------------------------------------------------------------
# Callback1 -> mode name  (FireRed "Squirrels")
# Thumb pointers; strip low bit for the true ROM address.
# ---------------------------------------------------------------------------

CALLBACK1_NAMES = {
    # Boot / title
    0x080EC821: "GameIntro (copyright/boot)",
    0x080EC9D5: "TitleScreen (waiting for Start)",
    0x08078B9D: "TitleScreen (Start pressed / fading to menu)",

    # Menus
    0x0800C301: "PostStart (transitioning to save select)",
    0x0800C2D5: "SaveSelectMenu (Continue / New Game / Options)",

    # Overworld
    0x080565B5: "Overworld (field engine running)",
    0x080572D9: "MapWarp (brief — loading new map)",
    0x08056809: "MapLoad (brief — map tiles loading)",

    # Battle — VERIFIED in-session (wild Pidgey encounter)
    0x08011101: "Battle (main loop)",

    # Battle — UNVERIFIED (from pret decomp, not yet reached in session)
    0x080C56A9: "UNVERIFIED: CB2_InitBattle",
    0x080C56B5: "UNVERIFIED: BattleMainCB2",
    0x08076DB1: "UNVERIFIED: CB2_ReturnToField",
}

CB1_OVERWORLD   = 0x080565B5
CB1_MAP_WARP    = 0x080572D9
CB1_MAP_LOAD    = 0x08056809
CB1_TITLE       = 0x080EC9D5
CB1_SAVE_SELECT = 0x0800C2D5
CB1_BATTLE      = 0x08011101   # in a battle; flips back to CB1_OVERWORLD on exit


# ---------------------------------------------------------------------------
# Core read
# ---------------------------------------------------------------------------

def read_state(core) -> dict:
    """Read every state signal and return a flat dict (no printing)."""
    s = {}
    s["callback1"] = _r32(core, GMAIN_CB1)
    s["callback2"] = _r32(core, GMAIN_CB2)
    s["main_state"] = _r8(core, GMAIN_STATE)

    s["battle_type_flags"] = _r32(core, BATTLE_TYPE_FLAGS)
    s["battle_outcome"]    = _r8(core, BATTLE_OUTCOME)

    # Field-control lock: 1 = something scripted/menu has control.
    s["field_locked"] = _r8(core, FIELD_LOCK) != 0

    # SaveBlock1 via live pointer. Pointer is 0/invalid until the save loads.
    sb1 = _r32(core, SAVEBLOCK1_PTR)
    s["saveblock1_ptr"] = sb1
    s["in_game"] = EWRAM_LO <= sb1 < EWRAM_HI
    if s["in_game"]:
        s["x"]        = _r16(core, sb1 + SB1_X)
        s["y"]        = _r16(core, sb1 + SB1_Y)
        s["map_group"] = _r8(core, sb1 + SB1_MAPGROUP)
        s["map_num"]   = _r8(core, sb1 + SB1_MAPNUM)
    else:
        s["x"] = s["y"] = s["map_group"] = s["map_num"] = None

    s["mode"] = _classify_mode(s)
    return s


def _classify_mode(s: dict) -> str:
    """Classify game mode from callbacks, battle flags, and the field lock."""
    cb1 = s["callback1"]

    # Battle takes priority. Detected from callback1, NOT gBattleTypeFlags --
    # the flags persist after the battle ends, but callback1 reliably flips back
    # to Overworld. The flags are only read here to tell wild from trainer.
    if cb1 == CB1_BATTLE:
        return "BATTLE (trainer)" if s["battle_type_flags"] & 0x8 else "BATTLE (wild)"

    if cb1 == CB1_OVERWORLD:
        # callback1 is the same for free roam and scripted cutscenes; the field
        # lock is what tells them apart.
        if s["field_locked"]:
            return "OVERWORLD — LOCKED (cutscene / script / dialog / menu)"
        return "OVERWORLD — free roam"

    if cb1 in (CB1_MAP_WARP, CB1_MAP_LOAD):
        return "MAP_TRANSITION"
    if cb1 == CB1_SAVE_SELECT:
        return "MENU (save select)"
    if cb1 == CB1_TITLE:
        return "TITLE_SCREEN"

    return f"UNKNOWN (cb1=0x{cb1:08X})"


# ---------------------------------------------------------------------------
# Pretty dump
# ---------------------------------------------------------------------------

def get_game_mode(core) -> dict:
    """Read all game-state signals, print a labelled diagnostic dump, return dict."""
    s = read_state(core)

    where = (f"map {s['map_group']}.{s['map_num']}  ·  x={s['x']} y={s['y']}"
             if s["in_game"] else "save not loaded yet (pre-overworld)")

    if s["callback1"] == CB1_BATTLE:
        battle = f"{s['mode']}  (outcome {s['battle_outcome']})"
    else:
        battle = "—  (not in battle)"

    print(f"\n{'='*60}")
    print(f"  GAME STATE  (frame {core.frame_counter})")
    print(f"{'='*60}")
    print(f"  MODE      {s['mode']}")
    print(f"  WHERE     {where}")
    print(f"  BATTLE    {battle}")
    print(f"\n  raw: cb1=0x{s['callback1']:08X}  cb2=0x{s['callback2']:08X}  "
          f"lock={int(s['field_locked'])}  sb1=0x{s['saveblock1_ptr']:08X}")
    print(f"{'='*60}\n")

    return s