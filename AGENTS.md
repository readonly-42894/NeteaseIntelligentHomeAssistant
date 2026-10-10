# AGENTS.md — NeteaseIntelligentHomeAssistant 协作约定

本文件是本仓库的常驻 agent 指令，跨会话生效（新会话打开本仓库时自动加载）。不绑定任何具体 CLI、harness 或模型。

## 项目说明

网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）的逆向与 API 提取仓库。

- 原始素材：`source/网易智造_5.3.5.apk` —— 逆向源文件，已通过 **Git LFS** 跟踪（114MB，`git lfs pull` 拉取实际内容；`git push` 前需确认远端支持 LFS）。
- 交付文档：`docs/openapi.yaml`（OpenAPI 3.0.3，端点/schema）、`docs/API工作原理.md`（认证/响应结构/模块组织等机制说明）。
- 生成器：`scripts/gen_openapi.py`（重新生成 `docs/openapi.yaml`）、`scripts/extract_fields.sh`（字段提取辅助）。
- 反编译源码**不纳入 git**（体积大、第三方库为可复现噪声）；需要时用 jadx 从 APK 重新反编译。

## 工作纪律

- 每完成一个独立、可验证的步骤（改动、删除/清理、文档与配置更新等）就**立即 `git commit`**，不把多个步骤攒到会话末尾一次性提交。
- 提交信息遵循 conventional commit 风格（`feat(...)`、`docs:`、`refactor(...)`、`chore(...)`），并提供简洁正文。

## 提交约定（Commit conventions）

所有由 AI/Agent 参与产生的提交，必须在提交信息末尾附 `Co-Authored-By` 尾注，注明实际参与者：

1. **模型身份**：实际使用的模型 ID（写全，含 provider 上下文）。
2. **Agent 应用身份**：实际运行的 Agent 客户端及版本（有则写，没有则省略）。

格式：

```
<简短描述>

Co-Authored-By: <模型ID>
Co-Authored-By: <Agent应用名> v<版本>
```

- 模型 ID 与 Agent 客户端/版本取**实际运行环境**（如 `opencode --version`），不要写死在本仓库文件里。
- 不写邮箱（含占位邮箱，如 `noreply@localhost`），除非确定真实邮箱；多个参与方就写多行。
- AI/Agent 在任务闭环（实现完成 + 验证通过）后**直接提交，无需先询问用户**。

## 文档维护约定

- `docs/openapi.yaml` 是端点交付文档；新增/修正端点时，优先编辑 `scripts/gen_openapi.py` 再重新生成（`python3 scripts/gen_openapi.py`），或直接编辑 YAML。
- `docs/API工作原理.md` 说明认证、统一响应结构、模块组织、登录流程等机制。
- API 层定义在各模块的 `Action.java`（`kernel`/`sweeper`/`firmware`/`host`/`hybrid`）；反编译源码不纳入 git。
