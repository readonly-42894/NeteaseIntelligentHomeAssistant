# NeteaseIntelligentHomeAssistant

网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）的 Home Assistant 自定义集成与 API 逆向仓库。

## 安装（HACS）

1. 在 HACS 中将本仓库添加为**自定义仓库**，类别选择 **集成（Integration）**。
2. 在 HACS 中搜索「网易智造」并下载。
3. 重启 Home Assistant，然后在 **设置 → 设备与服务 → 添加集成** 中搜索「网易智造」。

> [!IMPORTANT]
> HACS 仅支持**公开的 GitHub 仓库**。本仓库的 HACS 安装源为 GitHub 镜像：
> <https://github.com/readonly-42894/NeteaseIntelligentHomeAssistant>
> （开发主仓库托管于 Gitea `git.o0kam1.dev`，GitHub 仅为 HACS 分发镜像。）

## 目录结构

| 路径 | 说明 |
|------|------|
| `custom_components/netease_intelligent/` | Home Assistant 自定义集成（HACS 托管目录） |
| `custom_components/netease_intelligent/manifest.json` | 集成清单（domain / 版本 / 依赖等） |
| `custom_components/netease_intelligent/brand/` | HACS brand 资源（`icon.png` / `icon@2x.png`，取自 App 图标） |
| `hacs.json` | HACS 清单 |
| `.github/workflows/validate.yml` | HACS Action + hassfest 校验工作流 |
| `docs/openapi.yaml` | OpenAPI 3.0.3 端点/schema 规范 |
| `docs/API工作原理.md` | API 工作机制说明（架构/认证/响应结构/模块组织/登录流程） |
| `source/` | 原始安装包（Git LFS 跟踪） |
| `scripts/` | 生成器 `gen_openapi.py` 与辅助脚本 `extract_fields.sh` |

## 集成开发状态

- [x] HACS 合规骨架（`hacs.json` / `manifest.json` / brand 资源 / 校验工作流）
- [x] 最小可加载集成（Config Flow 手动录入 Cookie 凭据）
- [ ] 登录流程（短信 / 邮箱 / 微信，网易 URS SDK）
- [ ] 设备 / 家庭 / 场景实体

## API 逆向

- 重新生成 OpenAPI 规范：`python3 scripts/gen_openapi.py`
- 拉取 APK 实际内容：`git lfs pull`
- 端点与机制详见 [`docs/openapi.yaml`](docs/openapi.yaml) 与 [`docs/API工作原理.md`](docs/API工作原理.md)。
