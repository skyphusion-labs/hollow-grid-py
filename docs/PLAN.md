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

## Phase 3 -- container + release (in progress)

- [x] `Dockerfile` + `compose.yaml`
- [x] `release.yml` (GHCR push on main, informational smoke in CI)
- [ ] Fleet stack + `verdigris.skyphusion.org` ingress (fleet-chezmoi)
- [ ] Live federation smoke (`DUSTFALL_URL` + hub) to clear the last skip

## Conformance

Assert on `@event`, not prose. Point upstream smoke at a running server:

```sh
MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs
```

Federation phase also needs `DUSTFALL_URL` set to a live second world.
