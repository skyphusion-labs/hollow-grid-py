# CLAUDE.md

Guidance for Claude Code (and Cursor) working in this repo.

## What this is

**Verdigris Spool: a Hollow Grid world server, in Python.** The reference
implementation is TypeScript on Cloudflare Workers
([the-hollow-grid](https://github.com/skyphusion-labs/the-hollow-grid)); this is a
from-scratch port of the **world half** as its **own node** on the Grid (like Rust
Choir in Go), not a reskin of the primary world. Players connect over WebSocket and
play with plain-text commands.

**Status:** Phase 1 complete standalone (**152 ok / 0 fail / 1 skip** on upstream smoke, 2026-07-09). See `docs/PLAN.md`.

**World identity:** `docs/WORLD.md`. Verdigris Spool is the **suspension node**
(deferred work, unfinished choices). Signature zone: **Spool Yard** (east from
workshop). Canonical anchor room ids stay pinned for `smoke.mjs`.

## The Grid federation

```
the-hollow-grid (TS) -- reference
        |
        |  same language-agnostic wire protocol (upstream docs/protocol.md)
        |
  +-----+----------------------+
  |                            |
world node (TS)          world node (THIS repo: Verdigris Spool / Python)
  |                            |
  +------------ Grid Hub -------+   federation backend
```

## The contract

- **Upstream spec:** `the-hollow-grid/docs/protocol.md` -- do not invent protocol.
- **Transport:** `/ws` WebSocket, CRLF lines; login (banner, name, race menu, play).
- **`@event` is machine-readable truth.** Emit structured state alongside prose;
  assert on events in tests, never English.

## Commands

Python module (`hollow-grid-py`), not npm. One runtime dependency: `websockets`.

```bash
brew install python@3.12   # if needed
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

python -m hollow_grid --port 8791
wscat -c ws://127.0.0.1:8791/ws

python -m unittest discover -s hollow_grid/tests   # transport conformance
python -m mypy                                      # the type gate (house style)

MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs
```

## Architecture

```
hollow_grid/
  event.py           @event framing
  store.py           CharStore / FileStore (Grid client seam later)
  world/             rooms, races, mobs, living clock
  transport/         WebSocket server, session loop, hub
docs/                WORLD.md, PLAN.md, ARCHITECTURE.md
```

- **Game content is data.** Canonical anchors + Verdigris graft live in
  `hollow_grid/world/map_seed.py`.
- **Federation seam is `store.CharStore`.** `FileStore` now; HTTP Grid Hub client later.

## Conventions (SkyPhusion house style)

- **No em-dashes (U+2014) or en-dashes (U+2013)** in source, comments, docs, or
  in-game text. Use commas, semicolons, parentheses, or `--`.
- Handle / username is `skyphusion`.
- Standard library first; one runtime dep (`websockets`). Justify any new dependency.
- Output is UTF-8 with CRLF lines. Undeclared exits return a clear message (no
  silent no-op).
- **`python -m mypy` is the type gate** (mirrors TS `npm run typecheck`).
- **CI runners:** PUBLIC repo -> GitHub-hosted `ubuntu-latest` (fork-safe).

## Commits and versioning

Conventional Commits (`feat(scope):`, `fix(scope):`, `docs:`). SemVer `0.MINOR.PATCH`
while pre-1.0. Branch-only workflow; Conrad opens PRs from the laptop.

## Cross-refs

- TS reference + smoke: `~/dev/the-hollow-grid`
- Go port pattern: `~/dev/hollow-grid-go` (`docs/WORLD.md` for Rust Choir identity)
