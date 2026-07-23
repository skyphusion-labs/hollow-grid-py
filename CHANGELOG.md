# Changelog

## v0.1.5

### Security (K3 post-audit)

- Sanitize player `title` before persistence and broadcast.

## v0.1.4

### Security (K3 re-pass #43)

- Sanitize player login names and chat before cross-client broadcast.
- Reject CRLF/control characters in names; strip injection from player-authored text.

## v0.1.3

### Security (K3 #39 follow-up, grid-hub #86 client)

- Grid Hub HTTP client: world/worldKey headers and updated RPC param shapes.
- `claim_character_lease` on login; `GRID_WORLD_KEY` env support.

## v0.1.2

### Security (K3 audit #38, #39)

- Bcrypt secret-phrase login; legacy characters migrate on next login.
- Keeper names require `ADMIN_TOKEN` in addition to the name match.
- Reject concurrent login when a character name is already connected.

## v0.1.1

Release sync bump (2026-07-21). No functional changes in this tag.

