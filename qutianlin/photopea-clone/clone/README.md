# Photopea 本地核心版

入口：http://127.0.0.1:18160/ 。点击 Start using Photopea 进入编辑器；也可直接访问 `/#`。账号入口 `/account`，邮件收件箱 http://127.0.0.1:8025/ 。

当前按用户 2026-10-14 确认的核心范围交付，详见 `scope/ACCELERATED-PLAN.md`。功能已实现，最终中央门禁正在集中验证；本说明不代表全量 Photopea 或原始全站 BALANCED 已通过。

## 启动

```bash
source ../websitebench-pipeline/env.sh
source ./lane.env
./run-site.sh
```

独立运行时，复制整个 `clone/`，在其中执行 `PORT=18160 python3 -S server.py`。Python 3.12 依赖已随 `clone/vendor/` 提供。默认数据目录为 `clone/` 同级 `data/`，可通过 `PHOTOPEA_DATA_DIR` 指定。已有进程时不要重复启动；本站 PID 在 `run/server.pid`。停止前核对 `/proc/<PID>/cwd`，只停止本站进程。

邮件使用现有 Mailpit：`WEBSITEBENCH_SMTP_HOST=127.0.0.1`、`WEBSITEBENCH_SMTP_PORT=1025`、`WEBSITEBENCH_SMTP_FROM=no-reply@photopea.clone.test`。不需要真实外部邮箱授权，不重置共享邮箱。

演示账号：`demo@photopea.offline.invalid` / `PhotopeaLocal!2026`。这只是本地合成账号，和源站账号无关。也可注册新账号，从 Mailpit 读取验证码。

## 已实现

- 原编辑器新建、图片导入、图层、画笔、选择、文字、调整、滤镜、撤销/重做和 PSD、PNG、JPG 输出。
- 本地注册、真实 SMTP 验证、登录、资料修改、密码重置和服务器登出；会话和账号保存到 SQLite。
- PeaDrive 保存、保存副本、列表、打开、重命名、下载、删除，以及跨账号权限隔离。每个账号 500 MB，单个云端项目 64 MiB；更大文档可导出到设备。
- 基础帮助三页、手机视口、离线字体三组共 21 个字形文件，支持自行导入字体。

原站提供商登录后段没有完整取证，本地邮箱账号和 PeaDrive 为用户批准的等价实现。AI、广告、付费团队、外部云盘、模板/插件市场和深层帮助不在本轮范围；入口保留本地范围说明。原编辑器中的格式宣传不是本轮逐格式兼容性验收结论。

## 验证与数据

`tests/test_core.py` 覆盖邮件、验证码错误/过期/重发/并发消费、SMTP 失败、会话失效、权限、项目持久化与登录限制。浏览器证据见 `artifacts/core-browser.json`、`editing-tools.json`、`adjustments.json`；独立副本与重启证据见 `artifacts/clean-copy.json`。

```bash
python3 -m pytest -q tests
python3 tools/check-core-browser.py
python3 tools/check-editing-tools.py
python3 tools/check-adjustments.py
python3 tools/clean-copy.py
```

数据库 `data/photopea.sqlite3` 使用 WAL，启动初始化 schema v1。备份应使用 SQLite backup API；恢复时停止本站进程，用备份替换数据库，再启动。请勿复制源站私有 `run/` 凭据进入运行时。

未关闭问题及工具误报见 `OPEN-DEFECTS.md`；最终中央报告以 `scope/interaction-audit-report.json` 和 `run/verification/` 的实际结果为准。
