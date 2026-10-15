# Linear local clone

The commit signing feature requires the local executables `ssh-keygen`, `gpg`, and `gpgconf`. Its private key material is encrypted in SQLite; keep the data directory and its mode-0600 `.commit-signing-master` together when backing up.

Run `./run.sh` with Python 3.12 and the dependencies in `requirements.txt` installed. Default URL: http://127.0.0.1:18140. Set `PORT` and `LINEAR_DATA_DIR` as needed. The websitebench runtime is vendored locally; no sibling repository is imported. WebAuthn dependencies are in `vendor/`, including native Linux CPython 3.12 wheels, with exact versions in `vendor-requirements.txt`.

Sign up with a synthetic email and read the real SMTP login link or ten-character code in Mailpit at http://127.0.0.1:8025 (SMTP 1025). No source account or cookies are needed. Google/SAML entries use isolated local email verification. WebAuthn registration/login uses localhost, reached through a single-use local session bridge when starting from 127.0.0.1.

Each verified account has an independent SQLite workspace with the four source welcome issues. Tasks, comments, projects, views, labels, workflow states and settings persist. API keys enforce read/create/write scopes and revocation. Email changes require confirmation at the new address; exports and workspace deletion use real local SMTP. Workspace deletion removes business data and invalidates sessions; a later login creates a fresh fixture workspace.

Webhook configuration records signed issue/project creation and update events locally; it does not contact external endpoints. External authentication, integrations, billing and AI do not contact production services. Not all advanced workflows are implemented or source-verified; see the parent OPEN-DEFECTS.md and validation reports.

Keep `frontend`, `static`, `backend`, `websitebench`, `vendor`, `model.py`, `projects.py`, `passkeys.py`, `filters.py` and `signing_keys.py` beside `server.py`. Runtime assets are local. Data defaults to the parent `data/` directory and is not part of source templates.

Filter expressions run in the browser and use the source AND/OR URL format. Nested groups, multi-label operators, content filters and saved view conditions persist locally. Running the JavaScript expression tests additionally requires Node.js 20 or later; Node.js is not required to run the Python web server.
