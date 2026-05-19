# Nuzzy — Claude Agent Context

Nuzzy is going to be a Gen 3 Pokemon AI agent (Fire Red / Leaf Green) that reads live game state from a `.sav` file 
and makes decisions during battle and exploration. Right now, we are building out the codebase to develop this agent.

## Project files

| File | Purpose |
|------|---------|
| `gen3_extractor.py` | Reads `my_firered_gamestate.sav` and parses party, items, badges, location, etc. |

---

## Data directory (`oggen3_data/`)

The `oggen3_data/` directory contains game data (not state data) decomposed into purpose-specific files, modelled like a relational database. Load only the file(s) you need for answering a user's query.

Pokemon are keyed by their National Dex number as a string (`"94"` = Gengar). Moves are keyed by their Gen 3 move ID as a string (`"247"` = Shadow Ball).

---

### `oggen3_data/pokemon_base.json`
**When to load:** Any time you need to assess a pokemon's strength, typing, evolution tree, or stat profile.

One record per pokemon. Stats are flattened to the top level (not nested under `base_stats`). `bst` (Base Stat Total) is precomputed.

```json
"94": {
  "name": "Gengar",
  "types": ["Ghost", "Poison"],
  "bst": 500,
  "hp": 60,
  "atk": 65,
  "def": 60,
  "spa": 130,
  "spd": 75,
  "spe": 110,
  "evolves_to": null
}
```

Use `bst` to rank threats quickly. High `spa`/`spe` = fast special attacker. High `atk` = physical threat.

`evolves_to` has three forms:

- **`null`** — final form; does not evolve.
- **`{"id": N, "level": L, "condition": C}`** — single evolution. `level` is `null` for non-level triggers. `condition` is `null` for pure level-ups, otherwise a string describing the trigger (e.g. `"Fire Stone"`, `"trade"`, `"happiness"`, `"trade holding Metal Coat"`, `"max Beauty"`).
- **`[{"id": N, "level": L, "condition": C}, ...]`** — branching evolution (always a list). Used for Gloom, Poliwhirl, Slowpoke, Eevee, Tyrogue, Wurmple, Nincada, Clamperl. Same field semantics as the single form.

Bulbasaur (pure level-up):
```json
"evolves_to": {"id": 2, "level": 16, "condition": null}
```

Pikachu (stone trigger):
```json
"evolves_to": {"id": 26, "level": null, "condition": "Thunder Stone"}
```

Eevee (branching):
```json
"evolves_to": [
  {"id": 134, "level": null, "condition": "Water Stone"},
  {"id": 135, "level": null, "condition": "Thunder Stone"},
  {"id": 136, "level": null, "condition": "Fire Stone"},
  {"id": 196, "level": null, "condition": "happiness (daytime)"},
  {"id": 197, "level": null, "condition": "happiness (nighttime)"}
]
```

---

### `oggen3_data/moves.json`
**When to load:** To resolve a move ID to its name, type, category, power, or effect.

Keyed by move ID. `cat` is `"Physical"` or `"Special"` (Gen 3 uses type-based split, not physical/special split — in Gen 3, all Ghost moves are Special regardless of what `cat` says here). `effect` is `null` if the move has no secondary effect.

```json
"247": {
  "name": "Shadow Ball",
  "type": "Ghost",
  "cat": "Physical",
  "power": 80,
  "acc": 100,
  "pp": 15,
  "effect": {
    "stat_changes": [{"stat": "special-defense", "change": -1}],
    "stat_chance": 20,
    "desc": "Has a chance to lower the target's Special Defense by one stage."
  }
}
```

---

### `oggen3_data/pokemon_levelup.json`
**When to load:** To determine what moves a pokemon likely knows at a given level.

Keyed by pokemon ID. Each entry is a list of `{level, move_id}` pairs in level order. Resolve `move_id` against `moves.json`. Does not include TM/HM, egg, or tutor moves.

```json
"94": [
  {"level": 1,  "move_id": 122},
  {"level": 8,  "move_id": 50},
  {"level": 13, "move_id": 103},
  ...
]
```

To find moves known at level X: take all entries where `level <= X`, then keep only the last 4 (a pokemon can only hold 4 moves, learned in order).

---

### `oggen3_data/pokemon_learnpool.json`
**When to load:** Full movepool analysis — what a pokemon *could* know, not what it *does* know.

Keyed by pokemon ID. Contains TM/HM, egg, and tutor move IDs. Resolve IDs against `moves.json`. Rarely needed mid-battle; more useful for planning team coverage.

```json
"94": {
  "tm_hm":  [17, 21, 24, 29, 30, ...],
  "egg":    [],
  "tutor":  [34, 38, 76, 102]
}
```

---

### `oggen3_data/type_chart.json`
**When to load:** To calculate damage multipliers between types.

`type_chart[attacker_type][defender_type]` = multiplier. Values: `0` (immune), `0.5` (not very effective), `1` (neutral), `2` (super effective).

For dual-type defenders, multiply both values together.

```json
"Fire":  {"Grass": 2, "Water": 0.5, "Rock": 0.5, ...}
"Water": {"Fire":  2, "Grass": 0.5, ...}
```

---

### `oggen3_data/meta.json`
**When to load:** Nature lookups, item name resolution.

Top-level keys: `types`, `natures`, `nature_effects`, `items`

```json
// nature_effects["Adamant"] → boosts atk, reduces spa
"Adamant": {"boost": "atk", "reduce": "spa"}

// items["4"] → "Poké Ball"
```

Neutral natures (Hardy, Docile, Serious, Bashful, Quirky) have `boost: null, reduce: null`.

---

## Common query patterns

**"Is this opponent a serious threat?"**
→ Load `pokemon_base.json`. Check `bst`, dominant stat (`spa` vs `atk`), and `types`. Cross-reference `type_chart.json` against your active pokemon's types.

**"What moves could this Lv.42 Arcanine probably have?"**
→ Load `pokemon_levelup.json` for ID 59. Filter to `level <= 42`, and assess learn set from `pokemon_levelup.json`.

**"What does this pokemon's nature do?"**
→ Load `meta.json`, read `nature_effects[nature_name]`. `boost` and `reduce` are stat keys: `atk`, `def`, `spa`, `spd`, `spe`. A boosted stat is ×1.1; reduced is ×0.9.
