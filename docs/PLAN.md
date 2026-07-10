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

## Phase 3.1 -- TS parity polish + soak (done, 2026-07-09)

Mackaye post-merge review (crew-bus `fleet` thread): **cleared for steady-state**.

- [x] [#8](https://github.com/skyphusion-labs/hollow-grid-py/pull/8) -- faction canonicalize
  (`char.affects` / hub sync), poison tick + regen gating, reliable forgiveness /
  redemption push (`push_event_reliable`). Merged `442de22`; fleet-rolled.
- [x] [#9](https://github.com/skyphusion-labs/hollow-grid-py/pull/9) -- race-menu prompt
  aligned to TS (`Type a number or a name.`). Merged `3c5903e`; fleet-rolled.
- [x] Soak bots unblocked via mud-bots **v1.0.8** ([#34](https://github.com/skyphusion-labs/mud-bots/pull/34)):
  char-create fallback matches Go/Python wording and overrides `look`/`worlds` before
  vitals. Fleet compose pin: fleet-chezmoi [#482](https://github.com/skyphusion-labs/fleet-chezmoi/pull/482).
- [x] Live bots on biafra: **Patina, Oxide, Hum, Rack** @
  `wss://verdigris.skyphusion.org/ws` (image `mud-bots-hg:v1.0.8`).

### Carry-forwards (not blockers)

| Item | Notes |
| --- | --- |
| Death-path `asyncio.create_task(send_scene())` | Fire-and-forget can swallow exceptions; add a logging `spawn()` helper if the pattern spreads (Mackaye #8 note). |
| Structured char-create | [the-hollow-grid#58](https://github.com/skyphusion-labs/the-hollow-grid/issues/58): `@event char.create` so bots never parse race-menu prose. TS first; Go/py follow. Next touch of char-create is the natural moment. |
| Inventory loop commands | Still missing vs TS/Go: `flee`, `get`/`drop`, `use`/`drink`, `say`. Soak does not need them (bots drive off `room.actions`). |

## Smoke baselines (2026-07-09)

| Target | ok | fail | skip | Notes |
| --- | ---: | ---: | ---: | --- |
| Local dev (`127.0.0.1:8791`) | 152 | 0 | 1 | Standalone; skip = no second world |
| CI container (release.yml) | 142 | 0 | 0 | Informational gate on `442de22` image |
| Local + Dustfall (no hub token) | 155 | 3 | 0 | 3 fails = hub identity/tide/`who` (local dev not registered) |
| Live VLAN (`10.1.1.6:8791` + Dustfall) | 105-126 | 32-45 | 0 | Federation **headline** checks pass; full suite flakes on remote timing / shared state / 600s timeout |
| Public WSS (`verdigris.skyphusion.org`) | -- | -- | -- | Use VLAN or on-fleet path for contract runs |

**Parity target:** Rust Choir (Go) prod baseline **158 ok / 0 fail / 1 skip** on live hub +
Dustfall. Verdigris matches that bar **locally**; live VLAN variance is timing/state, not
missing handlers for the smoke-covered surface.

Contract validation: assert on `@event`, not prose. Prefer VLAN origin or on-box
smoke over laptop mesh WSS (event latency races fixed sleeps).

## Production

| | |
| --- | --- |
| URL | `wss://verdigris.skyphusion.org/ws` |
| Origin | `http://10.1.1.6:8791` on biafra |
| Image | `ghcr.io/skyphusion-labs/hollow-grid-py` (digest-pinned in `/opt/stacks/verdigris-spool/.env`; `3c5903e` / #9 roll on 2026-07-09) |
| Health | `https://verdigris.skyphusion.org/health/deep` (`grid_hub: ok`) |
| Soak bots | Patina, Oxide, Hum, Rack (`mud-bots-hg:v1.0.8` on biafra) |
| Fleet docs | `fleet-chezmoi/system/stacks/biafra/verdigris-spool/` |
| Roll runbook | `fleet-chezmoi/system/swarm/RUNBOOK-verdigris-spool-roll.md` |
| Bots matrix | `fleet-chezmoi/system/stacks/biafra/mud-bots/README.md` |

## Handoff (rancid Cursor session, 2026-07-09)

Session work landed under Conrad's git identity on rancid before named Cursor crew
identities. Significant PRs go through review (Conrad or Mackaye); do **not**
auto-merge `fleet-chezmoi`.

| Artifact | Where |
| --- | --- |
| Parity + race prompt | this repo `#8`, `#9` on `main` |
| Bot char-create fix | mud-bots `v1.0.8` / `#34` |
| Fleet pin + Active soak | fleet-chezmoi `#482` |
| Char-create contract issue | the-hollow-grid `#58` |
| Mackaye soak clearance | crew-bus `fleet` thread `thr_65ff1c4fb2b94f14b7f724cdc23770c3` |

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
