"""
Walkability segmentation extractor — FireRed (U) "Squirrels" build.

Companion to the screenshotter in test_play_pokemon.py: where save_screenshot()
captures the pixels, dump_segmentation() captures a player-centred 15x10 grid of
{walkable, blocked, oob} from RAM at the same instant, so (frame_XXXXX.png,
seg_XXXXX.json) form an aligned (pixels, label) pair. Emitted only in OVERWORLD
free-roam. Uses only the verified metatile COLLISION bit.
"""

import json
import os

from game_state import read_state, _r16, _r32

SEG_DIR = "/Users/bill/Desktop/screenshot_dump"
GBACKUP_MAP_LAYOUT = 0x03005040          # IWRAM { s32 width; s32 height; u16 *map; }
MAP_OFFSET = 7                            # player (x,y) -> grid cell (x+7, y+7)
SCREEN_W, SCREEN_H = 15, 10
PLAYER_COL, PLAYER_ROW = 7, 5


def build_segmentation(core):
    """Return the walkability label dict, or None outside overworld free-roam."""
    state = read_state(core)
    if not state.get("in_game") or state.get("mode") != "OVERWORLD — free roam":
        return None
    base = GBACKUP_MAP_LAYOUT
    width, height, map_ptr = _r32(core, base), _r32(core, base + 4), _r32(core, base + 8)
    if not (0 < width < 1000 and 0 < height < 1000 and 0x02000000 <= map_ptr < 0x03008000):
        return None

    gx0, gy0 = state["x"] + MAP_OFFSET, state["y"] + MAP_OFFSET
    grid = []
    for sr in range(SCREEN_H):
        row = []
        for sc in range(SCREEN_W):
            gx, gy = gx0 - PLAYER_COL + sc, gy0 - PLAYER_ROW + sr
            if not (0 <= gx < width and 0 <= gy < height):
                row.append("oob")
            else:
                cell = _r16(core, map_ptr + 2 * (gy * width + gx))
                row.append("blocked" if (cell & 0x0C00) else "walkable")
        grid.append(row)

    return {
        "frame": core.frame_counter,
        "map_group": state["map_group"],
        "map_num": state["map_num"],
        "player": {"x": state["x"], "y": state["y"]},
        "grid": grid,
    }


_fig = _im = None
_COLORS = {"walkable": (0.85, 0.95, 0.85), "blocked": (0.25, 0.25, 0.25), "oob": (0, 0, 0)}


def dump_segmentation(core, frame_number, show=False):
    """Save the walkability JSON next to the screenshots; optionally render it.
    Mirrors the screenshot helpers; used by the 'seg' command."""
    global _fig, _im
    seg = build_segmentation(core)
    if seg is None:
        print(f"No segmentation (not in overworld free-roam) — frame {frame_number}")
        return None

    os.makedirs(SEG_DIR, exist_ok=True)
    path = os.path.join(SEG_DIR, f"seg_{frame_number:05d}.json")
    with open(path, "w") as f:
        json.dump(seg, f, indent=2)
    print(f"Saved {path}")

    if show:
        import matplotlib.pyplot as plt
        rgb = [[_COLORS[c] for c in row] for row in seg["grid"]]
        if _fig is None or not plt.fignum_exists(_fig.number):
            plt.ion()
            _fig, ax = plt.subplots()
            ax.axis("off")
            _im = ax.imshow(rgb)
        else:
            _im.set_data(rgb)
        _fig.canvas.manager.set_window_title(f"seg {frame_number}")
        plt.pause(0.001)

    return seg
