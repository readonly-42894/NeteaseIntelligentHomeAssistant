# CONTRIBUTING.md — NeteaseIntelligentHomeAssistant 开发约定

本文件描述本仓库的项目背景、资料与文档维护方式、测试与验证约定。提交纪律由 [`AGENTS.md`](AGENTS.md) 规定。

## 项目说明

网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）的 Home Assistant 自定义集成与 API 逆向仓库。集成代码位于 `custom_components/netease_intelligent/`，由 HACS 分发；`docs/` 交付逆向得到的 API 规范与机制说明。

原始素材与工具：

- `source/网易智造_5.3.5.apk` —— 逆向源文件，已通过 **Git LFS** 跟踪（114MB，`git lfs pull` 拉取实际内容；`git push` 前需确认远端支持 LFS）。
- `scripts/gen_openapi.py` —— 重新生成 `docs/openapi.yaml`。
- `scripts/extract_fields.sh` —— 字段提取辅助。
- `scripts/live_smoke.py` —— 在线接口冒烟。
- `scripts/push_probe.py` —— 官方推送通道探针。
- `scripts/fetch_map_font.py` —— 地图字体获取。

反编译源码**不纳入 git**（体积大、第三方库为可复现噪声）；需要时用 jadx 从 APK 重新反编译。API 层定义在各模块的 `Action.java`（`kernel`/`sweeper`/`firmware`/`host`/`hybrid`）。

## 文档维护约定

- `docs/openapi.yaml` 是端点交付文档（OpenAPI 3.0.3）。新增/修正端点时，优先编辑 `scripts/gen_openapi.py` 再重新生成（`python3 scripts/gen_openapi.py`），或直接编辑 YAML。
- `docs/API工作原理.md` 说明认证、统一响应结构、模块组织、登录流程等机制。
- `docs/api/` 存放 API 专题文档（认证机制、统一响应结构、登录流程、调用示例、集成实现）。
- `README.md` 描述对外行为、HACS 安装方式、目录结构与集成开发状态；能力或行为变化时同步更新。

## 测试与验证

测试基座为 `pytest-homeassistant-custom-component`，在进程内启动真实 Home Assistant 内核，不需要外部 HA 实例。

```bash
python -m pip install -r requirements_test.txt
pytest
```

- `requirements_test.txt` 锁定 `pytest-homeassistant-custom-component`（连带 HA、pytest、aiohttp、Pillow 等版本，当前对应 HA 2026.10.4），要求 Python 3.14，因此不单独声明 pytest。
- 改动提交前跑通 `pytest`；CI 在 `.github/workflows/validate.yml` 中执行同一命令，并附带 hassfest 与 HACS Action 校验。
- 改动 `manifest.json`、集成结构或 brand 资源后，要保证 hassfest 与 HACS 校验能通过。

## 不要做的事

- 不要提交反编译源码、`__pycache__/`、`.pytest_cache/`、APK 解包中间产物或任何测试生成的临时文件。
- 不要在文档、测试或示例中写入真实账号 Cookie、令牌、家庭/设备 ID 或个人凭据；示例一律用占位值。
- 不要在未运行对应测试的情况下声称验证通过。
