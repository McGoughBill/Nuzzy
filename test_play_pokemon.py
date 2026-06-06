"""
Headless Fire Red runner.

Controls
--------
- Press Enter to advance one frame
- Type a button name (a, b, start, select, up, down, left, right, l, r) then Enter to press it for one frame
- Type 'run N' to run N frames silently (default 60)
- Type 'skip' to mash A through cutscenes until free-roam overworld
- Type 'screenshot' to save the current frame as a PNG
- Type 'seg' to dump the RAM segmentation label (and render it)
- Type 'quit' to exit
"""

import sys
import select

import mgba.core
import mgba.image
import mgba.log
import matplotlib
matplotlib.use("TkAgg")  # macosx backend beachballs when driven from a blocking input() loop
import matplotlib.pyplot as plt
from game_state import get_game_mode, read_state
from visual_segmentation import dump_segmentation

ROM_PATH = "/Users/bill/Documents/emulators/1636 - Pokemon Fire Red (U)(Squirrels).gba"

KEYS = {
    "a":      "KEY_A",
    "b":      "KEY_B",
    "start":  "KEY_START",
    "select": "KEY_SELECT",
    "up":     "KEY_UP",
    "down":   "KEY_DOWN",
    "left":   "KEY_LEFT",
    "right":  "KEY_RIGHT",
    "l":      "KEY_L",
    "r":      "KEY_R",
}


def setup():
    mgba.log.silence()
    core = mgba.core.load_path(ROM_PATH)
    if not core:
        raise RuntimeError(f"Could not load ROM: {ROM_PATH}")

    width, height = core.desired_video_dimensions()
    screen = mgba.image.Image(width, height)
    core.set_video_buffer(screen)

    core.autoload_save()
    core.reset()

    return core, screen


def press(core, key_name, hold_frames=4, pass_frames=12,
          auto_screenshot=False, screen=None,counter=None):
    #if walking, pass_frame is 12, running is 4, cycle is 0.
    key = getattr(core, KEYS[key_name])
    core.set_keys(key)
    for _ in range(hold_frames):
        core.run_frame()
    core.clear_keys(key)
    for _ in range(pass_frames):
        core.run_frame()

    if auto_screenshot:
        save_screenshot(screen, core.frame_counter)
        show_screenshot(screen, core.frame_counter)
        counter += 1
    return counter




def skip_to_overworld(core, max_frames=6000):
    """Mash A until the game is in free-roam overworld (or we give up)."""
    start = core.frame_counter
    while core.frame_counter - start < max_frames:
        if read_state(core)["mode"] == "OVERWORLD — free roam":
            print(f"Reached free roam at frame {core.frame_counter}")
            return True
        press(core, "a")
    print(f"Gave up after {max_frames} frames — still not in free roam")
    return False


def save_screenshot(screen, frame_number):
    path = f"/Users/bill/Desktop/screenshot_dump/screenshot_{frame_number:05d}.png"

    with open(path, "wb") as f:
        screen.save_png(f)
    print(f"Saved {path}")


# Reused matplotlib handles so each screenshot overwrites the same window
# instead of opening a new one.
_fig = None
_im = None


def show_screenshot(screen, frame_number):
    global _fig, _im
    img = screen.to_pil().convert("RGB")

    if _fig is None or not plt.fignum_exists(_fig.number):
        plt.ion()
        _fig, ax = plt.subplots()
        ax.axis("off")
        _im = ax.imshow(img)
    else:
        _im.set_data(img)

    _fig.canvas.manager.set_window_title(f"frame {frame_number}")
    plt.pause(0.001)  # runs the event loop briefly so the image actually redraws


def prompt(message):
    """Like input(), but keeps the matplotlib window alive while we wait.

    A plain input() parks the main thread and starves the GUI event loop, so
    the plot window freezes/beachballs. Here we poll stdin and pump matplotlib
    events every 50ms until a line is ready.
    """
    sys.stdout.write(message)
    sys.stdout.flush()
    while True:
        if _fig is not None and plt.fignum_exists(_fig.number):
            _fig.canvas.flush_events()
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if ready:
            line = sys.stdin.readline()
            if line == "":          # EOF (Ctrl-D)
                raise EOFError
            return line


def main():
    core, screen = setup()
    print(f"Loaded: {core.game_title} ({core.game_code})")
    print("Commands: <button>, run [N], skip, screenshot, seg, quit")
    print("Buttons:", ", ".join(KEYS))

    screenshot_counter = 0

    while True:
        try:
            cmd = prompt(f"\n[frame {core.frame_counter}] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not cmd:
            core.run_frame()
            get_game_mode(core)

        elif cmd in KEYS:
            screenshot_counter = press(core, cmd, auto_screenshot=True,
                                       screen=screen, counter=screenshot_counter)
            print(f"Pressed {cmd} — frame {core.frame_counter}")
            get_game_mode(core)

        elif cmd.startswith("run"):
            parts = cmd.split()
            n = int(parts[1]) if len(parts) > 1 else 60
            for _ in range(n):
                core.run_frame()
            print(f"Ran {n} frames — now at frame {core.frame_counter}")
            get_game_mode(core)

        elif cmd == "skip":
            skip_to_overworld(core)
            get_game_mode(core)

        elif cmd == "screenshot":
            save_screenshot(screen, core.frame_counter)
            show_screenshot(screen, core.frame_counter)
            screenshot_counter += 1
            get_game_mode(core)

        elif cmd == "seg":
            dump_segmentation(core, core.frame_counter, show=True)
            get_game_mode(core)

        elif cmd == "quit":
            break

        else:
            print(f"Unknown command: {cmd!r}")


if __name__ == "__main__":
    main()
