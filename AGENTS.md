# AGENTS.md — 提交纪律

本文件是本仓库的常驻 agent 指令，跨会话生效（新会话打开本仓库时自动加载）。它不绑定任何具体 CLI、harness 或模型。项目背景、测试、代码与文案约定见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 工作纪律

- 每完成一个独立、可验证的步骤（功能改动、修复、清理、文档与配置更新、测试通过等）就**立即 `git commit`**，不把多个步骤攒到会话末尾一次性提交。
- 提交信息遵循 conventional commit 风格（如 `feat:`、`fix:`、`refactor:`、`docs:`、`chore:`、`build:`），并提供简洁正文。
- 提交时用 `git commit --author "<模型名> <模型id@llm.invalid>"` 标明**当前正在执行这次提交的 agent/模型自身**，不要照搬别的 agent 的名字。例如：

  ```bash
  git commit --author "DeepSeek Flash <deepseek-flash@llm.invalid>" -m "$(cat <<'EOF'
  fix: 描述改动

  Co-Authored-By: opencode v2.2.7
  EOF
  )"
  ```

- `Co-Authored-By` 写实际运行的 Agent 客户端及版本（`opencode --version`），不写邮箱。
- 任务闭环（实现完成 + 验证通过）后直接提交，无需先询问用户。
