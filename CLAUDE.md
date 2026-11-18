# Database: PostgreSQL on node01 only

J Zara / polyamide index (reads Zara) data lives in PostgreSQL on node01: PG18 at 100.77.195.48:5432, reached only over Tailscale, db `vgr`, schema `zara (read via zara_rw)`, login role ``<schema>_rw``.
The password is only in this machine's pgpass (Dell `~/.pgpass`, minipc01 `C:\Users\pals\.pgpass`, laptop `%APPDATA%\postgresql\pgpass.conf`). Never print, copy or commit it.

- Cut over on 2026-11-18. The old local SQLite (../zara-parser/layer3_consolidator/database/master.sqlite) is retired: it is read-only, with `MIGRATED_TO_POSTGRES.txt` beside it. Never read it, write it, copy it forward or create a new one, whether in scheduled runs or in development.
- `vgr_pg` (PG_ONLY_PATCH) sends the production path to node01 with or without the marker, and refuses SQLite there. Only a sandbox or test working on its own temp copy may set `VGR_DB=sqlite VGR_PG_ALLOW_SQLITE=1`.
- New code that needs storage goes through `vgr_pg` into this schema. Do not add a new SQLite file, and do not create schemas or roles: admin SQL runs only over SSH on node01.
- After 4 weeks of correct working (due 2026-12-16), the scheduled task `vgr-db-migration-4week-check` erases the old local copies automatically. The node01 dumps are kept.
