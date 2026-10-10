# 网易智造 App API 工作原理

> 本文档说明网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）HTTP API 的工作机制：架构、网络栈、认证、统一响应、接口组织与登录流程。
> 端点级别的完整定义见 [`openapi.yaml`](./openapi.yaml)（OpenAPI 3.0.3，99 个 path / 128 个 schema / 约 103 个端点）。

## 1. 架构总览

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

## 2. 网络栈

- **Retrofit 2** + **OkHttp 3** + **RxJava 2** + **Gson**（含 `GsonEnumConverterFactory` 枚举反序列化）。
- 接口以 Retrofit 注解（`@GET` / `@POST` / `@DELETE`）声明，返回类型为 RxJava 的 `Observable`/`Single`。
- 连接超时 / 读取超时各 **30 秒**。

## 3. 基础地址（Base URL）

定义在 `kernel/network/API.java` 的 `API.HELPER`：

| 环境 | Base URL |
|------|----------|
| 线上 / Release | `https://3c.163.com` |
| Alpha / Beta | `https://t2.3c.163.com` |
| Develop | `https://t.3c.163.com` |

H5 对应域名：`m.3c.163.com` / `t2m.3c.163.com` / `tm.3c.163.com`。

## 4. 认证机制（Cookie，非 Authorization 头）

- 接口层**不携带 `Authorization` 头**，全局只注入 `User-Agent`。
- 身份凭据通过 **Cookie** 传递，关键 Cookie（域均为 `3c.163.com`）：

| Cookie | 常量（`SharedPrefsManager`） | 含义 |
|--------|------------------------------|------|
| `ONE_TOKEN` | `LOGIN_TOKEN` | 登录令牌 |
| `ONE_TOKEN_ID` | `LOGIN_TOKEN_ID` | 令牌 ID |
| `UA-INFO` | — | 设备/环境信息 |

- 登录走**网易 URS SDK**（不在 `/ai-app` 命名空间下），详见第 7 节。

## 5. 统一响应结构

所有接口返回 `ResponseWrapper<T>`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | **0 表示成功**，非 0 为错误 |
| `errorMsg` | string | 错误信息 |
| `result` | T | 业务数据 |
| `showType` | int | 展示类型 |
| `alertInfo` | FlyAlertItem | 弹窗信息 |
| `rawResult` | object | 原始结果 |

列表接口返回 `ListResponse<T>`：

```
{ "list": [T...], "page": PageInfo{ pageCnt, pageIndex, pageSize, totalCnt } }
```

在 `openapi.yaml` 中，每个端点的响应 schema 都已按 `ResponseWrapper<T>`（列表再套一层 `ResponseWrapper<ListResponse<T>>`）包装。

## 6. 接口组织（模块 → 业务域）

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

## 7. 登录流程

登录走网易 URS SDK，支持 **短信 / 邮箱 / 微信** 三种方式。以微信登录为例：

1. `GET /ai-app/weixin/wx_token?code=<微信授权码>` 换取微信令牌；
2. 对参数做 **AES 加密**；
3. `GET http://reg.163.com/outerLogin/oauth2/exchageMobLoginToken.do?id=<id>&params=<加密参数>` 换登录令牌；
4. 登录成功后调用 `GET /ai-app/account/info?from=1` 拉取用户信息（`UserInfo`）。

## 8. 调用示例

以「拉取家庭成员列表」为例：

```
GET https://3c.163.com/ai-app/user/list
User-Agent: <App 的 UA>
Cookie: ONE_TOKEN=<token>; ONE_TOKEN_ID=<id>; UA-INFO=<info>
```

响应（`ResponseWrapper<ListResponse<UserProfile>>`）：

```json
{
  "code": 0,
  "errorMsg": null,
  "result": {
    "list": [
      { "id": 1, "rid": "u1", "name": "张三", "userType": 1, "gender": 1, "avatar": "..." }
    ],
    "page": { "pageCnt": 1, "pageIndex": 1, "pageSize": 10, "totalCnt": 1 }
  }
}
```

## 9. 如何从源码定位 API

- 各模块的 HTTP 接口集中定义在 `Action.java`（见第 6 节表格），配合 `kernel/network/API.java` 的 Base URL 与 `ResponseWrapper`/`ListResponse` 的 DTO。
- 反编译源码**不纳入本仓库**（体积大、且第三方库是 Maven 可复现噪声）。需要时用 jadx 重新反编译 APK：

```bash
jadx --no-res -d decompiled 网易智造_5.3.5.apk
```

- `openapi.yaml` 由 [`scripts/gen_openapi.py`](./scripts/gen_openapi.py) 生成，改端点优先改脚本再重新生成。
