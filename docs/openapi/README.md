# 网易智造 App API — OpenAPI 规范（按模块拆分）

> 单一 `openapi.yaml` 过长，已按 App 模块（Retrofit `Action.java`）拆分为多个**自包含**的 OpenAPI 3.0.3 文档。
> 每个文件只含该模块的端点（`paths`）及其传递引用的数据模型（`components.schemas`，含 `ResponseWrapper` 包装），可独立阅读、校验。

## 文件索引

| 文件 | 模块 | 说明 |
|------|------|------|
| [`kernel.yaml`](./kernel.yaml) | `kernel` | 核心业务（账号/家庭/用户/场景/设备/产品/WiFi/OTA 通知） |
| [`sweeper.yaml`](./sweeper.yaml) | `sweeper` | 扫地机器人（清扫方案/地图/耗材/定时/固件/日志） |
| [`firmware.yaml`](./firmware.yaml) | `firmware` | 固件 OTA 检查 |
| [`host.yaml`](./host.yaml) | `host` | 设备分享/账号/全局信息 |
| [`tuya.yaml`](./tuya.yaml) | `hybrid`（涂鸦） | 涂鸦（Tuya）生态用户信息 |
| [`login.yaml`](./login.yaml) | URS 登录 SDK | 网易 URS 登录（短信/密码/邮箱/OAuth） |
| [`misc.yaml`](./misc.yaml) | 其他 | 头像等非 Retrofit 硬编码端点 |

模块职责与接口组织说明见 [`../API工作原理.md`](../API工作原理.md)。

## 重新生成

端点定义优先改生成器 [`scripts/gen_openapi.py`](../../scripts/gen_openapi.py) 再重新生成：

```bash
python3 scripts/gen_openapi.py
```