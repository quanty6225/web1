# TickTick local clone

Requires Linux x86_64 and Python 3.12. Runtime dependencies and frontend files are included.

```sh
./start.sh
```

Open http://127.0.0.1:18120 . The default demo account is `demo@ticktick.offline.invalid`, password `TickTick-Demo-2026!`.

To use a different assigned local port or data directory:

```sh
PORT=18122 TICKTICK_DATA_DIR=/absolute/path/to/local-data ./start.sh
```

New accounts require a local verification email. Reuse Mailpit at SMTP `127.0.0.1:1025`, inbox http://127.0.0.1:8025 . Set `WEBSITEBENCH_SMTP_HOST`, `WEBSITEBENCH_SMTP_PORT`, and `WEBSITEBENCH_SMTP_FROM` if this clone runs in another local environment. Keep existing data when restarting; do not clear the shared mailbox.

Accounts, tasks, permissions and sessions are stored in this clone's SQLite database. Original-site cookies are neither needed nor accepted. Third-party sign-in, checkout and external calendar integration use labelled local adapters; checkout never charges money. Remote calendar synchronization and unobserved Premium AI/global ranking are not claimed.

Adapted frontend code lives in `frontend/`; immutable captured resources live in `static/assets/`. The public resource URLs are mapped by `asset-routes.json`. Copy this whole directory when moving the application.

The 19-group portable regression suite is documented in `tests/README.md`. It needs Playwright and Chromium as development tools; running the website does not.

Public blog routes start at `/blog`. Five public task-list templates are available under `/pub/templates/project/<id>`; Save imports an independently owned local list. Source article illustrations that already fail at the original host are explicitly recorded in the workspace availability ledger. Source editorial accounts and production transactions are not included.
