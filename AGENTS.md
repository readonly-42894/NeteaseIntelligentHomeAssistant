# AGENTS.md — NeteaseIntelligentHomeAssistant 协作约定

本文件是本仓库的常驻 agent 指令，跨会话生效（新会话打开本仓库时自动加载）。不绑定任何具体 CLI、harness 或模型。

## 项目说明

网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）的逆向与 API 提取仓库。

- 原始素材：`网易智造_5.3.5.apk` —— 逆向源文件，**已纳入 git 跟踪，禁止 ignore**（约 114MB，GitHub 单文件上限 100MB，推送前需评估 LFS 或自建远端）。
- 交付文档：`openapi.yaml` —— OpenAPI 3.0.3，覆盖全部端点与 schema。
- 生成器与反编译产物在磁盘临时区（**非 git 跟踪**）：`/var/tmp/gen_openapi.py`、`/var/tmp/nz_decompiled/sources/`。

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

- `openapi.yaml` 是唯一交付文档；新增/修正端点时，优先编辑 `/var/tmp/gen_openapi.py` 再重新生成，或直接编辑 YAML。
- API 层定义在各模块的 `Action.java`（`kernel`/`sweeper`/`firmware`/`host`/`hybrid`），位于 `/var/tmp/nz_decompiled/sources/`。
