# NeteaseIntelligentHomeAssistant

网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）的逆向与 API 提取仓库。

## 目录结构

| 路径 | 说明 |
|------|------|
| `docs/openapi.yaml` | OpenAPI 3.0.3 端点/schema 规范（99 个 path / 128 个 schema） |
| `docs/API工作原理.md` | API 工作机制说明（架构/认证/响应结构/模块组织/登录流程） |
| `apk/` | 原始安装包（Git LFS 跟踪） |
| `scripts/` | 生成器 `gen_openapi.py` 与辅助脚本 `extract_fields.sh` |

## 快速开始

- 重新生成 OpenAPI 规范：`python3 scripts/gen_openapi.py`
- 拉取 APK 实际内容：`git lfs pull`