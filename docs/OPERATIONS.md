# Operations: backup and restore

## What holds state

Everything the engine stores lives under `VECTORFORGE_DATA_DIR` (`/data` on Fly): per collection a
manifest, a WAL, memory-mapped segments, and the latest index and state snapshot. A copy of the
directory taken after a checkpoint is a complete, consistent backup. A copy taken mid-write is still
recoverable, because recovery replays the WAL and drops only unacknowledged bytes.

## Backups

- **Fly volume snapshots** (`engine/fly.toml`): `scheduled_snapshots = true`, kept 14 days.
- **Manual snapshot before risky changes:** `fly volumes snapshots create <volume-id>`.
- **Off-platform copy:** stop writes (or accept WAL replay on restore), then
  `fly ssh sftp get /data/<collection> ./backup/<date>/` for each collection.
- **The demo collection needs no backup:** it is rebuilt from the repository with
  `VECTORFORGE_URL=... VECTORFORGE_ADMIN_KEY=... python bench/demo/seed_engine.py`.

## Restore

1. `fly volumes snapshots list <volume-id>` and pick a snapshot.
2. `fly volumes create vectorforge_data --snapshot-id <snapshot-id> --region <region>`.
3. Point the machine at the new volume (or destroy the old one), then deploy.
4. On start the engine loads each manifest, replays its WAL and reports `/readyz` 200.
5. Check: `GET /collections` with the admin key shows the expected counts.

## Not verified

These Fly commands and the `scheduled_snapshots` / `snapshot_retention` settings were written
from Fly's documentation and have not been run: `flyctl` is not installed here and nothing has
been deployed. Do a restore drill once after the first deploy.
