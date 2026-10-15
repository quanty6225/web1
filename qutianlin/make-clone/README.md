# make

本目录是独立运行副本。2026-10-15 上传时状态：**功能部分完成，尚未完成全范围验收**。

```bash
git lfs pull
cd qutianlin/make-clone
bash setup.sh
bash start.sh
```

默认访问 http://127.0.0.1:18170 。已在 Linux x86_64 / CPython 3.12 环境整理；编译依赖与离线 wheels 受平台和 Python 版本约束。
`setup.sh` 创建独立 `.venv`，优先采用随项目提供的依赖或 wheels；无离线依赖的站点需要联网安装。

`DATA_DIR` 可覆盖默认的本目录 `data/`；`PORT` 可覆盖端口（IFTTT 通常限制为 18180–18189）。
SMTP 默认 `127.0.0.1:1025`，建议用 Mailpit 接收本地注册、重置密码等邮件，Web UI 默认 `8025`。
可通过 `WEBSITEBENCH_SMTP_HOST` / `WEBSITEBENCH_SMTP_PORT` / `WEBSITEBENCH_SMTP_FROM` 配置。
本地登录与原站账号独立；新建本地账号或使用应用源码声明的本地演示账号。此副本不附带原站登录 Cookie、原站账号密码或运行数据库。

本次上传保存已有实现，未把部分完成的站点重新标记为全功能完成。详细边界见仓库根目录 README。
