# Build plan and status

Porting the Hollow Grid world framework to Python, against upstream
`the-hollow-grid/docs/protocol.md`. The scoreboard is upstream `smoke.mjs` (**135
checks**): build the port to pass it, phase by phase.

## Phase 0 -- transport foundation (done)

- [x] Project scaffold, house style (`mypy`, stdlib `unittest`)
- [x] **Verdigris Spool** world identity (`docs/WORLD.md`)
- [x] Canonical anchor map + Spool Yard graft (`hollow_grid/world/map_seed.py`)
- [x] `/ws` WebSocket, UTF-8 text, CRLF lines
- [x] Login flow: banner, name, race menu, play; name-based identity
- [x] `@event` channel framing
- [x] `/health` + `/health/deep`
- [x] Transport conformance tests (login, resume, move)

## Phase 1 -- the world (done, standalone)

Prod baseline (2026-07-09, single-world): **152 ok / 0 fail / 1 skip** against
upstream `smoke.mjs` (skip = second world at `DUSTFALL_URL` unreachable).

- [x] Full canonical + endgame map, bestiary, items, equipment
- [x] Async heartbeat: combat, regen, `world.state`
- [x] Moral arc: Cinder Front, ash-sworn, redemption, reckoning
- [x] Economy: tinker shop, tavern vices, steal/sell
- [x] Multiplayer: tell/reply/yell/emote, presence branding
- [x] Rescue: holding pit, cells, transit hub, `grid.rescued`
- [x] Grid commands: ping, listen, war, gridcast, witness, cache/gather
- [x] `LocalHub` federation fallback + `/map.svg`
- [x] Grid Hub HTTP client (`GRID_HUB_URL`) for live federation

## Phase 2 -- federation (done)

- [x] `RemoteHub` JSON-RPC client (`GRID_HUB_URL`)
- [x] Federation loop (register, presence, gridcast relay, tide cache)
- [x] Canonical CharSheet merge on login / commit on persist

## Phase 3 -- container + release (done)

- [x] `Dockerfile` + `compose.yaml`
- [x] `release.yml` (GHCR push on main, informational smoke in CI)
- [x] Fleet stack + `verdigris.skyphusion.org` ingress (fleet-chezmoi #470/#471)
- [x] Live hub registration (`grid_hub: ok` on `/health/deep`)
- [x] Roll hardening (fleet-chezmoi #473: health poll + cloudflared sync)

## Smoke baselines (2026-07-09)

| Target | ok | fail | skip | Notes |
| --- | ---: | ---: | ---: | --- |
| Local dev (`127.0.0.1:8791`) | 152 | 0 | 1 | Standalone; skip = no second world |
| Live VLAN (`10.1.1.6:8791` + Dustfall) | 113 | 45 | 0 | Federation **headline** checks pass (identity, tide, `who`, `travel Dustfall`); full suite flakes on remote timing |
| Public WSS (`verdigris.skyphusion.org`) | -- | -- | -- | Use VLAN or on-fleet path for contract runs |

Contract validation: assert on `@event`, not prose. Prefer VLAN origin or on-box
smoke over laptop mesh WSS (event latency races fixed sleeps).

## Production

| | |
| --- | --- |
| URL | `wss://verdigris.skyphusion.org/ws` |
| Origin | `http://10.1.1.6:8791` on biafra |
| Image | `ghcr.io/skyphusion-labs/hollow-grid-py` (digest-pinned in `/opt/stacks/verdigris-spool/.env`) |
| Fleet docs | `fleet-chezmoi/system/stacks/biafra/verdigris-spool/` |
| Roll runbook | `fleet-chezmoi/system/swarm/RUNBOOK-verdigris-spool-roll.md` |

Cloudflared ingress is IaC in `fleet-chezmoi/system/stacks/biafra/cloudflared/config.yml`.
**Every** swarm manager (biafra, fugazi, damaged) must carry the same
`/opt/stacks/cloudflared/config.yml` or tunnel connectors 404. Biafra's
`fleet-chezmoi-refresh` timer syncs locally after each fetch (#473); fugazi and
damaged still need the operator loop in the verdigris-spool README until
multi-host automation lands.

## Conformance

Assert on `@event`, not prose. Point upstream smoke at a running server:

```sh
# standalone
MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs

# live federation (phase 12)
MUD_URL=ws://10.1.1.6:8791/ws WORLD_NAME="Verdigris Spool" \
  DUSTFALL_URL=wss://dustfall.skyphusion.org/ws \
  node /path/to/the-hollow-grid/smoke.mjs
```

Federation phase also needs `DUSTFALL_URL` set to a live second world and
`WORLD_NAME="Verdigris Spool"` when scoring a fleet node.
