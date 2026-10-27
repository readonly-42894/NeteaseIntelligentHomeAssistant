# 网易智造 App API 工作原理

> 本文档说明网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）HTTP API 的工作机制：架构、网络栈、认证、统一响应、接口组织与登录流程。
> 端点级别的完整定义见 [`openapi.yaml`](./openapi.yaml)（OpenAPI 3.0.3，104 个 path / 130 个 schema / 106 个端点）。

## 目录

本文的专题章节拆分在 `docs/api/` 下：

| 主题 | 文件 |
|------|------|
| 认证机制（UA / Cookie / UA-INFO） | [`api/认证机制.md`](./api/认证机制.md) |
| 统一响应结构（`ResponseWrapper` / `ListResponse`） | [`api/统一响应结构.md`](./api/统一响应结构.md) |
| 登录流程（网易 URS 登录 SDK） | [`api/登录流程.md`](./api/登录流程.md) |
| 调用示例 | [`api/调用示例.md`](./api/调用示例.md) |
| 蓝牙配网（BLE 下发配网参数 → 读回 SN → 云端绑定） | [`api/蓝牙配网.md`](./api/蓝牙配网.md) |
| 集成实现（家庭数据抽象） | [`api/集成实现.md`](./api/集成实现.md) |

以下为总览性章节。

## 架构总览

App 是 **Flutter（UI）+ 原生 Java/Kotlin（网络层）** 的混合架构。所有 HTTP 请求都发生在原生层，Flutter 侧通过桥接调用原生能力。

主包 `com.netease.intelligent` 按业务拆成多个模块：

| 模块 | 职责 |
|------|------|
| `kernel` | 账号、家庭、用户、场景、设备、产品、WiFi、OTA 通知等核心域 |
| `sweeper` | 扫地机（清扫方案、地图、耗材、定时、固件、日志） |
| `firmware` | 固件 OTA 检查 |
| `host` | 设备分享、账号、全局信息 |
| `hybrid` | 涂鸦（Tuya）生态的用户信息 |
| `scales` | 蓝牙秤（走蓝牙，无 HTTP 接口） |

## 网络栈

- **Retrofit 2** + **OkHttp 3** + **RxJava 2** + **Gson**（含 `GsonEnumConverterFactory` 枚举反序列化）。
- 接口以 Retrofit 注解（`@GET` / `@POST` / `@DELETE`）声明，返回类型为 RxJava 的 `Observable`/`Single`。
- 连接超时 / 读取超时各 **30 秒**。

## 基础地址（Base URL）

定义在 `kernel/network/API.java` 的 `API.HELPER`：

| 环境 | Base URL |
|------|----------|
| 线上 / Release | `https://3c.163.com` |
| Alpha / Beta | `https://t2.3c.163.com` |
| Develop | `https://t.3c.163.com` |

H5 对应域名：`m.3c.163.com` / `t2m.3c.163.com` / `tm.3c.163.com`。

## 接口组织（模块 → 业务域）

接口按模块拆分在 5 个 Retrofit 接口（均命名为 `Action.java`）：

| 接口 | 端点数 | 业务域 |
|------|--------|--------|
| `kernel/config/Action.java` | 43 | 账号/家庭/用户/场景/设备/产品/WiFi/OTA 通知 |
| `sweeper/config/Action.java` | 38 | 扫地机 |
| `firmware/config/Action.java` | 2 | 固件 OTA |
| `host/config/Action.java` | 17 | 设备分享/账号/全局信息 |
| `hybrid/tuya/Action.java` | 3 | 涂鸦生态 |

另有 2 处**非 Retrofit 的硬编码请求**：

- `POST /ai-app/account/uploadThumb` —— 上传头像
- `GET /ai-app/account/headpic?userProfileId=` —— 头像图片

## 如何从源码定位 API

- 各模块的 HTTP 接口集中定义在 `Action.java`（见「接口组织」表格），配合 `kernel/network/API.java` 的 Base URL 与 `ResponseWrapper`/`ListResponse` 的 DTO。
- 反编译源码**不纳入本仓库**（体积大、且第三方库是 Maven 可复现噪声）。需要时用 jadx 重新反编译 APK：

```bash
jadx --no-res -d decompiled 网易智造_5.3.5.apk
```

- `openapi.yaml` 由 [`scripts/gen_openapi.py`](../scripts/gen_openapi.py) 生成，改端点优先改脚本再重新生成。
