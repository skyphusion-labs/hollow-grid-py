# CLAUDE.md

Guidance for Claude Code (and Cursor) working in this repo.

## What this is

**Verdigris Spool: a Hollow Grid world server, in Python.** Language port of the world
half; reference implementation is TypeScript on Cloudflare Workers
([the-hollow-grid](https://github.com/skyphusion-labs/the-hollow-grid)). Own node on the
Grid (like Rust Choir in Go), not a reskin of the primary world. Players connect over
WebSocket and play with plain-text commands.

**Protocol authority:** `the-hollow-grid/docs/protocol.md`. Do not invent protocol.
**Definition of done = upstream `smoke.mjs`** (score against current the-hollow-grid head).

**Status:** not deployed. The fleet host and `verdigris.skyphusion.org` are retired
(`docs/PLAN.md` Production, `README.md`). Run the world locally on port `8791`.
Prior soak bots are historical, not a standing population.

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

Distribution `hollow-grid-py`, import module `hollow_grid`, not npm. Runtime dependencies: `websockets` + `bcrypt` (`pyproject.toml`).

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
  store.py           CharStore / FileStore (offline fallback)
  world/             rooms, races, mobs, living clock
  transport/         WebSocket server, session loop, hub
docs/                WORLD.md, PLAN.md, ARCHITECTURE.md
```

- **Game content is data.** Canonical anchors + Verdigris graft live in
  `hollow_grid/world/map_seed.py`.
- **Federation seam is `store.CharStore`.** `FileStore` locally; `RemoteHub` HTTP JSON-RPC when `GRID_HUB_URL` is set (User-Agent required for Cloudflare).

## Conventions (SkyPhusion house style)

- **No em-dashes (U+2014) or en-dashes (U+2013)** in source, comments, docs, or
  in-game text. Use commas, semicolons, parentheses, or `--`.
- Handle / username is `skyphusion`.
- Standard library first; runtime deps are `websockets` and `bcrypt`. Justify any new dependency.
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

## Release / deploy

**Tag-gated GHCR publish, not a host deploy.** Merges to `main` run CI and build the image; they do not push it.
Cut an annotated SemVer tag on `main` to publish (`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`).
`release.yml` asserts the tag commit is an ancestor of `origin/main` before pushing `:<sha>` and `:latest`.
There is no fleet deploy step (host retired 2026-09-24).

## Release convention (bump-at-release)

One convention for every skyphusion-labs repo (Conrad, ruled 2026-11-10, fleet-chezmoi#1766). A version moves ONLY in a release PR: bump the version, then assemble the changelog. Feature and fix PRs do not bump. Releases go through a PR (fleet-chezmoi#1622) and the tag goes on that PR's merge commit.

- Version of record here: pyproject.toml.
- Tag shape: `v*`.
- Check before a release PR: does a tag already exist for the version currently in the manifest? Yes means the cycle is closed, so the release PR bumps. No means a bump already landed outside a release PR; stop and read why before bumping again.
