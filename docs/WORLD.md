# Verdigris Spool: the Python fleet node on the Grid

**Verdigris Spool** is the Python port's identity in the Hollow Grid federation. It
speaks the same wire protocol and builds toward the same `smoke.mjs` conformance
suite as the reference world, but it is not a clone of hollow.skyphusion.org,
Dustfall, or Rust Choir.

**Status:** Deployed on fleet (2026-07-09). Live at `wss://verdigris.skyphusion.org/ws`,
registered on the shared Grid Hub with Dustfall and Rust Choir. **Soak bots
active** (Patina, Oxide, Hum, Rack) via mud-bots `v1.0.8` on biafra -- Mackaye
cleared steady-state after post-merge review of py PRs #8 / #9.

## The pitch

The primary world is the **moral crucible**. Dustfall is the same engine in a salt
pan. Rust Choir is the **memory node** (what the network remembers).

Verdigris Spool is the **suspension node**.

Where the others ask what you will do or what you will be remembered for, Verdigris
Spool asks **what you leave unfinished**. Its signature geography is the **Spool
Yard** tract (reachable east from the tinker's workshop): copper racks humming with
deferred work, a callback shaft still ringing, an oxide checkpoint where the Cinder
Front taxes passage, and a suspended gallery of processes frozen before they chose.

## What is different here

| Axis | Primary / Dustfall / Rust Choir | Verdigris Spool |
| --- | --- | --- |
| Identity | Reference / salt pan / archivist | **Verdigris Spool** (suspension node) |
| Signature zone | Canonical only / Grid Gate graft | **Spool Yard** graft east from workshop |
| Default port | 8787/8788 / 8790 | **8791** |
| Engine | TS Workers / Go fleet | **Python** (`hollow-grid-py`) |

Mechanically the races, Cinder Front arc, holding-pit rescue, and `@event` vocabulary
stay identical. Differentiation is **place and voice**, not protocol.

## Design rules

1. **Conformance first.** Creative content grafts from rooms the smoke suite does not
   pin (workshop `east` is the current graft point).
2. **Moral weight stays data.** Every meaningful choice emits `room.actions` with
   `valence`; rescues emit `grid.rescued`; oaths land in the trace ledger.
3. **Federation is additive.** The world runs standalone on a local `FileStore`; with
   `GRID_HUB_URL` it registers and syncs through the HTTP Grid Hub client (see `.env.example`).

## Play it (local dev)

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

python -m hollow_grid --port 8791
wscat -c ws://127.0.0.1:8791/ws

# east from the workshop -> the Spool Yard tract
```

Score with upstream smoke:

```sh
# local dev
MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs

# live federation (second world required for phase 12)
MUD_URL=wss://verdigris.skyphusion.org/ws \
  WORLD_NAME="Verdigris Spool" \
  DUSTFALL_URL=wss://dustfall.skyphusion.org/ws \
  node /path/to/the-hollow-grid/smoke.mjs
```

Fleet deploy runbook: `fleet-chezmoi/system/stacks/biafra/verdigris-spool/README.md`.
