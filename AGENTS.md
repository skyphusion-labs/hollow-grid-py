# hollow-grid-py

This file is the guide for any coding agent and any contributor. Follow it.

## What this project is

Verdigris Spool is a Hollow Grid world server, written in Python. It is a language port of the world half. The reference implementation is [the-hollow-grid](https://github.com/skyphusion-labs/the-hollow-grid). This node is not a reskin of the primary world. Players connect over WebSocket. They play with plain-text commands.

Protocol authority is `the-hollow-grid/docs/protocol.md`. Do not invent protocol. Definition of done is upstream `smoke.mjs`, scored against current the-hollow-grid head.

The public Python Worker serves https://verdigris.skyphusion.org/ and `wss://verdigris.skyphusion.org/ws`. Run the process server locally on port `8791`. Read [docs/PLAN.md](docs/PLAN.md) and [README.md](README.md) for the last recorded score. A dated score is not the current gate. Prior soak bots are historical. They are not a standing population.

World identity is in [docs/WORLD.md](docs/WORLD.md). Verdigris Spool is the suspension node: deferred work and unfinished choices. The signature zone is Spool Yard, east from the workshop. Canonical anchor room ids stay pinned for `smoke.mjs`.

## Federation

The TypeScript worlds and this world speak one wire protocol. The Grid Hub is the federation backend.

`FileStore` is the local character store. Set `GRID_HUB_URL` and `RemoteHub` speaks HTTP JSON-RPC. That client must send a User-Agent. Cloudflare requires it. The public Python Worker calls `GridHubService` through the `GRID` service binding. It authenticates as Verdigris Spool with the `GRID_WORLD_KEY` secret.

## Contract

Read `the-hollow-grid/docs/protocol.md`. Transport is `/ws` with CRLF lines. Login runs banner, name, race menu, then play. `@event` is machine-readable truth. Emit structured state next to prose. Tests assert on events. They do not assert on English.

## Commands

The distribution name is `hollow-grid-py`. The import module is `hollow_grid`. This is not an npm project. Runtime dependencies are `websockets` and `bcrypt`. See [pyproject.toml](pyproject.toml). It requires Python 3.12 or newer.

```bash
brew install python@3.12   # if needed
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

python -m hollow_grid --port 8791
wscat -c ws://127.0.0.1:8791/ws

python -m unittest discover -s hollow_grid/tests
python -m mypy

MUD_URL=ws://127.0.0.1:8791/ws node /path/to/the-hollow-grid/smoke.mjs
```

CI runs `python -m unittest discover -s hollow_grid/tests` and `python -m mypy`. See [.github/workflows/ci.yml](.github/workflows/ci.yml). `python -m mypy` is the type gate.

## Architecture

```
hollow_grid/
  event.py           @event framing
  store.py           CharStore and FileStore
  world/             rooms, races, mobs, living clock
  transport/         WebSocket server, session loop, hub
docs/                WORLD.md, PLAN.md, ARCHITECTURE.md
```

Game content is data. Canonical anchors and the Verdigris graft live in `hollow_grid/world/map_seed.py`.

## Conventions

Do not use an em dash (U+2014) or an en dash (U+2013) in source, comments, docs, or in-game text. Use a comma, parentheses, or two hyphens (`--`).

Prefer the standard library. Runtime dependencies stay `websockets` and `bcrypt`. Justify any new dependency. Output is UTF-8 with CRLF lines. An undeclared exit returns a clear message. Silence is not an answer.

This is a public repo. CI uses GitHub-hosted `ubuntu-latest`.

## Docs

Write Simplified Technical English. Use short sentences. Put one idea in each sentence. Use the active present tense. Use plain words. Use the same word every time.

State the limit next to the capability. Do not turn a measured result into a promise. Quote a smoke score with its date. Say that it is not the current gate.

## Commits and version

Use Conventional Commits (`feat(scope):`, `fix(scope):`, `docs:`). Use a branch and a pull request. Do not push straight to `main`.

The version of record is [pyproject.toml](pyproject.toml). The tag form is `v*`. While the project is pre-1.0, use `0.MINOR.PATCH`.

A version moves only in a release pull request. Bump `pyproject.toml` in that pull request. Then write the changelog entry. A feature pull request does not bump the version. A fix pull request does not bump the version. Put the tag on the merge commit of the release pull request.

Before a release pull request, look for a tag of the current version. A matching tag means the cycle is closed. The release pull request then bumps. No matching tag means a bump already landed outside a release pull request. Stop and read why.

## Release

The release workflow publishes tagged process images to GHCR. Deploy the public Python Worker separately with `pywrangler deploy`.

A merge to `main` runs CI and builds the image. It does not push the image.

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

[.github/workflows/release.yml](.github/workflows/release.yml) checks that the tag commit is an ancestor of `origin/main`. Then it pushes `ghcr.io/skyphusion-labs/hollow-grid-py` as `:<sha>` and `:latest`.

The release workflow requires upstream smoke to pass against the process image. Verify the public Python Worker separately.

## Safety

Do not put a secret in a tracked file. Do not put a secret in a log. Do not put a secret in an issue.
