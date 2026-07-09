# hollow-grid-py

A **Hollow Grid world server, in Python.** The Hollow Grid is a federated MUD whose
reference implementation is TypeScript on Cloudflare Workers; this is a from-scratch
port of the *world half* as **Verdigris Spool**, a distinct node that speaks the
Grid's language-agnostic wire protocol and can join the federation when
`GRID_HUB_URL` is set.

> The Hollow Grid is a dead network that outlived its makers. Worlds are nodes on
> that network; the shared backend *is* the Grid. Verdigris Spool is where the
> network keeps work it started and never collected: deferred choices made legible
> as data, not buried in prose.

- **Upstream contract:** [`the-hollow-grid/docs/protocol.md`](https://github.com/skyphusion-labs/the-hollow-grid/blob/main/docs/protocol.md)
- **Definition of done:** upstream `smoke.mjs` (**135 checks**)
- **Status:** Phase 3 + 3.1 complete; **live on fleet** at
  `wss://verdigris.skyphusion.org/ws` (2026-07-09). Standalone smoke: **152 ok /
  0 fail / 1 skip** local; soak **steady-state** (Patina / Oxide / Hum / Rack).
  See `docs/PLAN.md`.
- **World identity:** [`docs/WORLD.md`](docs/WORLD.md) (not a clone of hollow, Dustfall, or Rust Choir)

## Quick start

```sh
brew install python@3.12   # if needed; Homebrew ships 3.12 as python3.12
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

python -m hollow_grid --port 8791
wscat -c ws://127.0.0.1:8791/ws

# score it (standalone)
MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs

# live federation (phase 12 needs Dustfall)
MUD_URL=wss://verdigris.skyphusion.org/ws WORLD_NAME="Verdigris Spool" \
  DUSTFALL_URL=wss://dustfall.skyphusion.org/ws node /path/to/the-hollow-grid/smoke.mjs

# container (local)
docker compose up --build
```

## What's built (Phases 0--3)

| System | What it does |
| --- | --- |
| **Transport** | `/ws` WebSocket, plain UTF-8, CRLF lines; login flow (banner, name, race menu, play) |
| **`@event` channel** | full protocol vocabulary (combat, moral, grid, comms, equipment, dreams, ...) |
| **Health** | `/health` (liveness) + `/health/deep` (per-dependency) + `/map.svg` |
| **The world** | Canonical anchor map + **Spool Yard** graft + endgame stronghold |
| **Combat** | async tick-resolved fights on `combat.*`, death respawn |
| **Multiplayer** | session registry, `tell`/`reply`/`yell`/`emote`, `room.info.players` |
| **Moral arc** | Cinder Front, ash-sworn, redemption, reckoning, rescue on `grid.rescued` |
| **Federation** | `LocalHub` offline fallback; live hub via `GRID_HUB_URL` (register, gridcast relay, canonical sheets) |
| **Persistence** | `FileStore` CharSheet seam; resume on a known name |
| **CI gate** | `python -m unittest discover` + `python -m mypy` |
| **Container** | `Dockerfile` + `compose.yaml`; GHCR via `release.yml` on merge to `main` |
| **Fleet** | `verdigris.skyphusion.org` on biafra (`:8791`); auto-roll via fleet-chezmoi |

## Production

| | |
| --- | --- |
| Play | `wss://verdigris.skyphusion.org/ws` |
| Health | `https://verdigris.skyphusion.org/health` |
| Image | `ghcr.io/skyphusion-labs/hollow-grid-py` (pinned on biafra) |
| Fleet IaC | [fleet-chezmoi `verdigris-spool`](https://github.com/skyphusion-labs/fleet-chezmoi/tree/main/system/stacks/biafra/verdigris-spool) |
| Hub | `https://grid-hub.skyphusion.org/rpc` (shared with Dustfall, Rust Choir) |

## Layout

```
hollow_grid/
  event.py              @event channel framing
  store.py              CharStore / FileStore
  world/                rooms, races, mobs, the living clock
  transport/            WebSocket server, session loop, presence hub
  tests/                transport conformance (real WebSocket sessions)
docs/                   WORLD.md (identity), PLAN.md, ARCHITECTURE.md
```

## Configuration

| Flag / env | Default | Meaning |
| --- | --- | --- |
| `--host` / `LISTEN_HOST` | `127.0.0.1` | bind address |
| `--port` / `LISTEN_PORT` | `8791` | listen port |
| `--world-name` / `WORLD_NAME` | `Verdigris Spool` | display name |
| `--world-url` / `WORLD_URL` | `wss://verdigris.skyphusion.org/ws` | federation registry URL |
| `--grid-hub-url` / `GRID_HUB_URL` | *(unset)* | Grid Hub HTTP RPC endpoint |
| `--grid-hub-token` / `GRID_HUB_TOKEN` | *(unset)* | Bearer token for hub RPC |
| `--admins` / `ADMINS` | `skyphusion` | comma-separated keeper names |
| `--data` / `DATA_DIR` | `data` | local character store directory |

## Development

```sh
python -m unittest discover -s hollow_grid/tests
python -m mypy
```

## Links

- **Wire spec:** [the-hollow-grid](https://github.com/skyphusion-labs/the-hollow-grid)
- **Go port (Rust Choir):** [hollow-grid-go](https://github.com/skyphusion-labs/hollow-grid-go)
- **Fleet deploy:** [fleet-chezmoi verdigris-spool](https://github.com/skyphusion-labs/fleet-chezmoi/tree/main/system/stacks/biafra/verdigris-spool)
- **Skyphusion Labs:** https://skyphusion.org

## License

AGPL-3.0-only (see [LICENSE](LICENSE)).
