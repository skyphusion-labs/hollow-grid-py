# Architecture

How hollow-grid-py is put together. The north star is upstream `docs/protocol.md`
and `smoke.mjs`. Nothing here invents protocol; it implements it.

## The shape

```
player (wscat / bot / smoke.mjs)
         |  WebSocket /ws  (UTF-8 text, CRLF lines)
         v
hollow_grid/transport/server.py
         |  per connection:
         v
       Session  --- asyncio command loop ---
         |
    +----+-------------+
    v                  v
hollow_grid/world   hollow_grid/store
(rooms, races)      (FileStore now, Grid later)
    |
hollow_grid/event   (@event <name> <json>)
```

Each connection owns its session coroutine. Shared presence (who is in which room)
lives in `transport/hub.py`.

## Verdigris Spool vs the reference world

The **canonical anchor graph** (room ids, exits, mob ids the arc depends on) matches
`docs/worlds.md` so `smoke.mjs` can score this node. **Prose, banner, and the Spool
Yard graft** differentiate Verdigris Spool from hollow, Dustfall, and Rust Choir.

Graft point: `workshop` `east` -> `spool-yard` (Rust Choir grafts east from `tunnels`).

## The `@event` channel

`hollow_grid/event.py` formats `@event <name> <json>`. The transport interleaves these
with prose and flushes a whole response as one WebSocket message.

Rule: if a client, bot, or test would need it, it is an event, not prose-only.

## Persistence

`store.FileStore` writes one JSON file per character name (case-insensitive key). The
`CharStore` interface is the federation seam: swap in an HTTP Grid Hub client without
touching transport logic.

## Health

`GET /health` and `GET /health/deep` mirror protocol.md section 1 so the same monitor
config works across TS, Go, and Python worlds.
