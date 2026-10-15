# Local OneDrive core clone

Run `PORT=18100 bash run.sh` with CPython 3.12 on Linux x86_64. Bundled dependencies load with `python -S`; no network installation is needed. Keep the SQLite database and `file-objects/` together in the data directory. `ONEDRIVE_DATA_DIR` can specify its location.

Local demo: `demo@onedrive.offline.invalid` / `OneDrive-Demo-2026!`.

SMTP: localhost:1025; sender `no-reply@onedrive.clone.test`. Use the existing local Mailpit inbox on port 8025 for registration and recovery codes. No emails or credentials are sent to Microsoft.

The user-approved core includes local account lifecycle, basic account/help, persistent file/folder operations, sharing, recycle bin, photos/albums and document previews. Deep help, full community, marketing long tail, paid fulfillment and nonessential AI are excluded.

Post-code registration and Office editing are authorized local equivalents. Source Office bytes remain intact; extracted text and local edits are stored separately. The source OneNote snapshot retains five sections/eight ink pages, with separate local text annotations. This does not reproduce full Office layout, spreadsheet recalculation, ink editing or real-time collaboration. Same-name uploads report a conflict without silently overwriting files.

Original provider authentication after registration is not claimed identical. Formal acceptance status and detailed differences are recorded in the workspace `scope/` and `run/delivery-gate-final.json`. A working runtime is not a claim that every source control passed the central audit.

Do not copy source session state or private reconnaissance files into this directory. This bundle does not require them.
