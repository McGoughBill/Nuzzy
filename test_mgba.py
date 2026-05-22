import mgba.core
import mgba.log
import mgba.vfs

ROM_PATH = "/Users/bill/Documents/emulators/1636 - Pokemon Fire Red (U)(Squirrels).gba"
SAV_PATH = "/Users/bill/Documents/emulators/1636 - Pokemon Fire Red (U)(Squirrels).sav"

mgba.log.silence()

core = mgba.core.load_path(ROM_PATH)
if not core:
    raise RuntimeError(f"Failed to load ROM: {ROM_PATH}")

core.reset()
vf = mgba.vfs.open_path(SAV_PATH, "r")
core.load_save(vf)

print(f"ROM loaded: {ROM_PATH}")
print(f"Save loaded: {SAV_PATH}")
print(f"Platform: {core.platform}")
