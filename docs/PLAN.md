# Build plan and status

Porting the Hollow Grid world framework to Python, against upstream
`the-hollow-grid/docs/protocol.md`. The scoreboard is upstream `smoke.mjs` (**135
checks**): build the port to pass it, phase by phase.

## Phase 0 -- transport foundation (in progress)

- [x] Project scaffold, house style (`mypy`, stdlib `unittest`)
- [x] **Verdigris Spool** world identity (`docs/WORLD.md`)
- [x] Canonical anchor map + Spool Yard graft (`hollow_grid/world/map_seed.py`)
- [x] `/ws` WebSocket, UTF-8 text, CRLF lines
- [x] Login flow: banner, name, race menu, play; name-based identity
- [x] `@event` channel framing
- [x] `/health` + `/health/deep`
- [x] Transport conformance tests (login, resume, move)
- [ ] Grid Hub HTTP client (`GRID_HUB_URL`)
- [ ] Full `smoke.mjs` green run

## Phase 1 -- the world

Combat, economy, moral arc, persistence depth, dreams, rescue, and the rest of the
reference mechanics. Track against `hollow-grid-go/docs/PLAN.md` for parity ordering.

## Conformance

Assert on `@event`, not prose. Point upstream smoke at a running server:

```sh
MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs
```

Federation phase also needs `DUSTFALL_URL` set to a live second world.
