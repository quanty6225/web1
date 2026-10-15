# iCloud local clone — desktop edition

This edition prioritizes desktop home pages, secondary navigation, the observed iCloud applications and local account workflows. AI, advanced, paid and online collaboration features are outside the current scope. Use this working directory directly; no new archive is required.
Basic Pages text editing, Numbers sheets and formulas, and Keynote slide editing/playback are included. Changes are saved automatically to the local database, with revision conflicts reported instead of overwriting another window. Downloads use HTML or CSV; native iWork conversion and real-time collaboration are not included.

See `RELEASE-LIMITS.md` for the explicit scope and unavailable features. The original
full BALANCED formal acceptance is not claimed by this reduced-scope release.

For offline setup on Linux x86_64 (glibc 2.17 or newer), use CPython 3.12,
3.13 or 3.14 with the GIL enabled. Python itself must already be installed.
Create a new environment using the wheels supplied in this directory:

```sh
python install_offline.py --dest .venv
.venv/bin/python serve.py --port 18110
```

The installer never replaces an existing environment. It verifies every wheel
against `wheels/MANIFEST.json`, installs exact versions from
`requirements-offline.txt` with pip's hash checking and `--no-index`, and rejects
DNS/socket connection attempts. Upstream wheel licenses are retained. It neither
uses nor changes the shared development environment. For other Python/platform
combinations, `requirements.txt` remains the dependency declaration; the bundled
compiled wheels do not cover those combinations.

Open http://127.0.0.1:18110. Demo login:
`demo@icloud.offline.invalid` / `IcloudDemo2026!`.

Data is stored in `data/icloud.sqlite3`, with uploads in `data/uploads/`.
Use `--data-dir PATH` to choose a separate persistent directory. Do not share
the live data directory with a test instance. Restarting retains local changes.

Registration and password reset require local Mailpit SMTP on port 1025.
Mailpit's inbox is normally available on http://127.0.0.1:8025. Reuse an existing
Mailpit instance without clearing other projects' mail. SMTP failure is reported
to the caller, and is not treated as a successful delivery.

Registration has local image and spoken verification codes, country/phone
selection, birthday validation and persisted profile preferences. Email codes
can be requested again after the 60-second cooldown; issuing a new code revokes
the previous one. Verification steps survive refresh and server restart.
The spoken digit WAV files are included; no speech service or speech engine is
needed at runtime. `BASE_URL`, if set, controls the email link origin; leave it
unset when starting an isolated instance on another port.

The runtime uses independent local accounts and local media. Source cookies,
source sessions and the `run/` collection directory are not required. Demo
fixtures have irreversible privacy masks and synthetic identity fields. The release
review covered all thumbnail contact sheets, all document pages, detailed photos and
sampled video frames; conservative masks also cover sensitive moving regions.

For the portable account and server restart tests included in a review copy,
create a separate environment with the bundled test dependencies:

```sh
python install_offline.py --dest .venv-test --tests
.venv-test/bin/python -I -m pytest tests -q
```

These tests use local SMTP and the dedicated test port 18112. Their temporary
data is independent of the preview database. The Playwright browser driver is
separate audit tooling; the browser and its system libraries are not installed
by this runtime installer. Browser acceptance reports are supplied separately with the release summary.

Calendar time zones use the bundled IANA data and iCalendar libraries in `vendor/`.
They need no system timezone database or runtime download. Pinned versions and
upstream wheel hashes are in `vendor/MANIFEST.json`; package license files are
retained. Upstream iCalendar test/example fixtures are omitted. Calendar time zone
support is a per-account preference in each browser's local storage; the account
time zone itself is persisted in local settings. Existing events without zone
metadata retain their prior floating-time interpretation. Public subscription
feeds include explicit timezone transitions from year 1 through the exporter’s
year 9998 horizon; dates beyond that horizon are not claimed as verified.

## 一小时功能增补

新增文字排版/图片/表格/查找替换，表格行列删除/排序/筛选/CSV 导入/单元格格式/基础图表，演示文稿图片/布局/背景/转场，以及三个编辑器的复制/打印/20 个历史版本恢复/本地副本导入导出。提醒事项新增自选日期提醒时间和延后提醒。

编辑器新增功能以本地实用实现为界，不声明源站截图逐像素保真；详细能力上限见 RELEASE-LIMITS.md。


## 首页修正（2026-10-14）

登录后首页采用原站静态背景和云朵素材，恢复三列卡片与手机单列布局；本地中文后备字体避免缺字。快捷菜单包含十个应用及储存空间、方案、恢复、帮助入口；卡片可添加、移除、更换类型、重复添加及拖动排序，设置保存在本地账户。日历卡片按账户时区显示当天及重复/跨日事件，文件夹选择按 ID 保存，文档卡片展示实际本地文档。

本轮集中检查记录在 `artifacts/home-review-browser.json` 和 `artifacts/audit-home-final.json`（工作区）。截图中的个人内容已脱敏；本轮不宣称原始 BALANCED 全站验收完成。

## 2026-10-14 account-page finishing pass

Registration and recovery now include the captured account navigation and footer. A local searchable region picker returns to the corresponding form and preselects the registration country. The current public index contains 797 pages. Changed-page checks passed for navigation and real local SMTP authentication; three source-only empty/hidden element findings remain documented in the workspace, and formal full-site acceptance is not claimed.
