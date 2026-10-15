# Twelve website clones

十二站运行代码与素材保存在 `qutianlin/`，每站独立目录。这是 2026-10-15 的实现快照，并非十二站均已完整验收。

| 站点 | 默认端口 | 上传时状态 |
| --- | --- | --- |
| [onedrive](qutianlin/onedrive-clone/) | 18100 | 桌面核心范围验收通过 |
| [icloud](qutianlin/icloud-clone/) | 18110 | 功能部分完成，尚未完成全范围验收 |
| [ticktick](qutianlin/ticktick-clone/) | 18120 | 已冻结授权范围验收通过 |
| [basecamp](qutianlin/basecamp-clone/) | 18130 | 功能部分完成，尚未完成全范围验收 |
| [linear](qutianlin/linear-clone/) | 18140 | 功能部分完成，尚未完成全范围验收 |
| [teamwork](qutianlin/teamwork-clone/) | 18150 | 桌面核心范围验收通过 |
| [photopea](qutianlin/photopea-clone/) | 18160 | 桌面核心范围验收通过 |
| [make](qutianlin/make-clone/) | 18170 | 功能部分完成，尚未完成全范围验收 |
| [ifttt](qutianlin/ifttt-clone/) | 18180 | 已冻结授权范围验收通过 |
| [surveymonkey](qutianlin/surveymonkey-clone/) | 18190 | 功能部分完成，尚未完成全范围验收 |
| [reclaim](qutianlin/reclaim-clone/) | 18200 | 功能部分完成，尚未完成全范围验收 |
| [cal](qutianlin/cal-clone/) | 18210 | 桌面核心范围验收通过 |

## 下载和启动

仓库使用 Git LFS 存放大文件，必须安装 Git LFS 并拉取实际文件，GitHub 的普通 ZIP 下载不应作为完整运行副本使用。

```bash
git lfs install
git clone https://github.com/quanty6225/web1.git
cd web1
git lfs pull
cd qutianlin/ticktick-clone
bash setup.sh
bash start.sh
```

各站 README 提供端口和启动方式。需要邮件的流程使用 SMTP，默认连接本地 Mailpit `127.0.0.1:1025`（界面 `8025`）。不附带外部邮箱凭据。
运行数据库会在首次启动时生成；原站 Cookie、原站账号密码、浏览器会话、探查记录和历史运行数据库不在此仓库。
原项目继续使用原位置，此上传快照不会随其后续修改自动更新。

## 完成范围

- TickTick、IFTTT：已冻结授权范围的验收记录通过。
- Photopea、OneDrive、Cal、Teamwork：桌面核心范围通过，不代表原产品所有功能全部实现。
- SurveyMonkey、Make、Reclaim、iCloud、Basecamp、Linear：已有可运行的核心功能，但全范围验收仍有缺口。
- OneDrive 的 Office 编辑、Photopea 全部格式和插件、Cal 深层设置等不应当作完整原产品能力。
- SurveyMonkey 仍有深层路由缺口；Make 模块覆盖有限；Reclaim、iCloud 的完整范围记录未闭合；Basecamp、Linear 有部分细节功能尚未收尾。

状态来自上传前已完成的本地审计，上传操作仅检查分发、启动和敏感信息，不重新声称完成全量功能验收。
所有品牌、第三方素材和随附组件的权利与许可证归其相应权利人；保留组件自带的许可证，本仓库未替它们重新授权。

本次上传副本的十二站独立启动与首页 HTTP 检查均通过，记录见 `STARTUP-CHECK.json`。离线依赖默认使用 Python 3.12；Basecamp 使用 Python 3.14。可以用 `PYTHON=/path/to/python bash setup.sh` 指定对应解释器。
