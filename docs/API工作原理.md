# 网易智造 App API 工作原理

> 本文档说明网易智造 App（主包 `com.netease.intelligent`，versionName 5.3.5）HTTP API 的工作机制：架构、网络栈、认证、统一响应、接口组织与登录流程。
> 端点级别的完整定义见 [`openapi/`](./openapi/)（OpenAPI 3.0.3，按模块拆分，104 个 path / 106 个端点，索引见 [`openapi/README.md`](./openapi/README.md)）。

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
- **User-Agent** 由 `kernel/network/HeaderManager.getUserAgent()` 生成，经 OkHttp 拦截器 `CommonHeaderInterceptor` 全局注入。格式为：

  ```
  <http.agent> <appName>/<productName>/<version>/<buildType>/<source>[/<keyWord>]
  ```

  各段取值：

  | 段 | 取值 | 来源 |
  |----|------|------|
  | `<http.agent>` | Android 平台默认 UA（如 `Dalvik/2.1.0 (Linux; U; Android 13; Pixel 5 Build/TQ3A.230805.001)`） | `System.getProperty("http.agent")` |
  | `<appName>` | `Intelligent` | `MiscUtils.APP_NAME` |
  | `<productName>` | `ntes3c` | `MiscUtils.PRODUCT_NAME` |
  | `<version>` | `5.3.5` | `versionName` 取 `-` 前缀段（`MiscUtils`） |
  | `<buildType>` | `release` | `MiscUtils.getBuildType()`（versionName 无 `-d/-a/-b` 后缀时为 `release`） |
  | `<source>` | `Release` | `assets/source` 首段（`BaseApplication.aSource[0]`） |
  | `<keyWord>` | 无（省略） | `assets/source` 的 `\|` 第二段（`BaseApplication.aSource[1]`） |

  线上 release 包（`com.netease.intelligent` 5.3.5）完整 UA 形如：

  ```
  Dalvik/2.1.0 (Linux; U; Android 13; Pixel 5 Build/TQ3A.230805.001) Intelligent/ntes3c/5.3.5/release/Release
  ```

- 身份凭据通过 **Cookie** 传递，关键 Cookie（域均为 `3c.163.com`）：

| Cookie | 常量（`SharedPrefsManager`） | 含义 |
|--------|------------------------------|------|
| `ONE_TOKEN` | `LOGIN_TOKEN` | 登录令牌 |
| `ONE_TOKEN_ID` | `LOGIN_TOKEN_ID` | 令牌 ID |
| `UA-INFO` | — | 设备/环境信息；**每个业务请求都必须携带** |

- `UA-INFO` 由 `CookieManager.getUaInfoCookie()` 生成：`generateUAHeader()` 先构造一段
  JSON（`PRODUCT`/`SOURCE`/`KW`/`APP-VER`/`APP-BUILD`/`BUILD-TYPE`/`TERMINAL`/`OS-VER`/
  `BRAND`/`MODEL`/`DENSITY`/`DEVICE-ID`/`INFO-SIGN`，再追加 `WIDTH`/`HEIGHT`），
  最后用 Java `URLEncoder.encode` 编码。`Auth.getCookies()` 对**每个**业务请求都会
  同时写入 `ONE_TOKEN`、`ONE_TOKEN_ID`、`UA-INFO`，三者缺一不可；集成按同一规则生成
  默认 `UA-INFO`（见 `api.py` 的 `build_ua_info()`）。

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

在 `openapi/*.yaml` 中，每个端点的响应 schema 都已按 `ResponseWrapper<T>`（列表再套一层 `ResponseWrapper<ListResponse<T>>`）包装。

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

## 7. 登录流程（网易 URS 登录 SDK）

登录**不经过** `3c.163.com`，而是走**网易 URS 登录 SDK**（`com.netease.loginapi`，SDK 版本 `2.1.9`）。登录成功后 App 写入 `ONE_TOKEN` / `ONE_TOKEN_ID` / `UA-INFO` Cookie，之后的业务接口即凭这三者认证（见第 4 节）。

- 服务地址：`https://sdk.reg.163.com`（备用 `sdk2.reg.163.com`；部分老接口用 `http://reg.163.com`）。
- 产品标识 `product=ai`；URS 请求统一带请求头 `yd-version: 2.1.9`。
- 支持 **短信验证码 / 手机号+密码 / 邮箱密码 / 微信** 等方式。

### 7.1 请求格式与参数加密

URS 请求均为 `POST` + `application/x-www-form-urlencoded`。业务参数（`library/f.java` 的 `commonParams` + 接口私有参数）序列化为 `k1=v1&k2=v2...` 后，用 **AES-128/ECB/PKCS5Padding** 加密（输出**小写 hex**），作为表单字段 `params`；会话 ID（= `ONE_TOKEN_ID`）以明文字段 `id` 传输。

公共参数（按插入顺序）：`rtid、androidID、carrier、network、pdtVersion、mac、resolution、uniqueID、uniqueID_cf、imei、product、deviceType、systemName、systemVersion、isEmulator`。

### 7.2 初始化握手（`POST /services/initSdk`）

登录前先初始化一次，协商出会话 `id`/`key`：

1. 客户端生成 16 字节随机 AES 密钥（32 位小写 hex，记为 `aesKey`）。
2. 签名 `sign = URLEncode(base64(SHA256withRSA(clientPriKey, product + "2.1.9" + uniqueID + ctt)))`，`ctt` 为毫秒时间戳。
3. `pinfo = base64(RSA_encrypt(serverPubKey, 4随机字符 + aesKey))`（服务端取末 32 位作 AES 密钥）。
4. 用 `aesKey` AES 加密公共参数 + `ctt` + `sign` 得到 `params`。
5. 请求体：`product=ai&pinfo=<...>&params=<...>`。
6. 响应 JSON：`{"result":"201","msg":"<AES密文>","rk":"<base64 RSA密文>"}`。
7. `rk` 用**客户端私钥** RSA 解密 → 临时 AES 密钥；`msg` 用该密钥 AES 解密 → `{"id","key","sign"}`。
8. 用服务端公钥验签 `sign`（签名数据为 `id + key`）；`id`/`key` 即后续请求的会话凭据。

> 服务端 `result` 是**字符串**（如 `"201"`）。Java 侧通过 Gson 反序列化到 `int` 字段会自动强转，但用其他语言解析时需显式转 int，否则误判失败。

### 7.3 短信验证码登录

1. **获取验证码** `POST /interfaces/yd/login1.do`：`params` 含 `mobile`、`referer`（空串）。`result=201` 已发送；`result=411` 表示需走「上行短信解锁」流程（响应另含 `number`、`code`）。
2. **校验并登录** `POST /interfaces/yd/login2.do`：`params` 含 `smscode`、`mobile`、`loginException`、`needLeakInfo`。`result=201` 时 `msg` AES 解密为 URL query（`URSAccount`），关键字段：
   - `token` —— 登录令牌（→ `ONE_TOKEN`）
   - `ssn` —— 主账号
   - `ydAccount` —— 手机账号
   - 另有 `loginException`、`flag_pass`、`flag_secuEmail`、`isleak`、`verify_time`

### 7.4 邮箱密码登录（`POST /services/safeUserLoginForMob`）

- `params`：`username`（邮箱）、`password` = **MD5**（截断后的密码）、`isMd5=1`、`needmainaccount=1`。
- **密码截断**（`LoginOptions.fixLenOfPasswordBefore09`）：密码长度 > 16 且邮箱域名**不在** `{126.com, 188.com, vip.163.com}` 时取前 16 位，且**发生在 MD5 之前**。
- 响应为**纯文本**（非 JSON）：首个数字行为 `result` 码，其后首个非数字行为 description，**末行**为 `result=<AES密文>`；解密该 `result` 得 `token`、`username`（→ `ssn`）、`aliasuser`（→ 用户名）。

### 7.5 手机号 + 密码登录（`POST /interfaces/yd/pwdlogin.do`）

`params`：`password` = MD5(密码)、`isMd5=1`、`mobile`、`loginException`、`needLeakInfo`。协议已逆向，集成暂未接入。

### 7.6 微信登录

1. `GET /ai-app/weixin/wx_token?code=<微信授权码>` 换取微信令牌；
2. 对参数做 **AES 加密**；
3. `GET http://reg.163.com/outerLogin/oauth2/exchageMobLoginToken.do?id=<id>&params=<加密参数>` 换登录令牌；
4. 登录成功后调用 `GET /ai-app/account/info?from=1` 拉取用户信息（`UserInfo`）。

### 7.7 密码学原语

| 用途 | 算法 |
|------|------|
| 参数加密 | AES-128 / ECB / PKCS5Padding（hex 输入输出） |
| 密钥协商 | RSA-1024 / PKCS#1 v1.5（服务端公钥加密、客户端私钥解密） |
| 签名 | SHA256withRSA（客户端私钥签名、服务端公钥验签） |
| 密码哈希 | MD5（小写 hex） |

服务端公钥与客户端私钥**硬编码在 App 内**（`NEConfig`）。

### 7.8 业务错误码

响应中的 `result` 为业务码，`201` 表示成功；`msg` 为（可能加密的）错误信息。已实测：`401` 参数非法、`411` 需上行短信解锁。

### 7.9 集成实现

`custom_components/netease_intelligent/` 的登录配置流实现了**短信验证码**与**邮箱密码**两种真实登录，并保留手动录入 Cookie 的兜底方式；协议核心逻辑在 `urs.py`（`UrsClient`，含上述密码学与握手），配置流在 `config_flow.py`。端点定义见 [`openapi/login.yaml`](./openapi/login.yaml) 的 `login` tag。

## 8. 调用示例

以「拉取家庭成员列表」为例：

```
GET https://3c.163.com/ai-app/user/list
User-Agent: Dalvik/2.1.0 (Linux; U; Android 13; Pixel 5 Build/TQ3A.230805.001) Intelligent/ntes3c/5.3.5/release/Release
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

- `openapi/*.yaml` 由 [`scripts/gen_openapi.py`](../scripts/gen_openapi.py) 生成，改端点优先改脚本再重新生成。

## 10. 集成实现（家庭数据抽象）

集成 `custom_components/netease_intelligent/` 在登录（第 7.9 节）之上，用「模型 + 客户端 + 协调器」三层抽象家庭数据，作为设备/场景实体的地基：

| 文件 | 职责 |
|------|------|
| `models.py` | 家庭域 DTO（`FamilyInfo`/`Family`/`Room`/`Member`/`FamilyEquip`/`Equip`/`FamilyEnv`/`EnvInfo`）与扫地机数据 DTO（`SweeperDeviceData`）。字段为 `snake_case`，`from_dict` 按 `camelCase` 映射回 API JSON 键（如 `family_id` ← `familyId`），缺字段容错。 |
| `api.py` | `NeteaseIntelligentApiClient`：按第 4 节注入 `Cookie`（`ONE_TOKEN` / `ONE_TOKEN_ID` / `UA-INFO`），按第 5 节解包 `ResponseWrapper`（`code != 0` 抛 `ApiError`），返回模型对象。 |
| `coordinator.py` | `NeteaseIntelligentCoordinator`（`DataUpdateCoordinator`）：周期拉取 `GET /ai-app/family/info`，按家庭 ID 建索引存入 `coordinator.data`。 |
| `__init__.py` | 建客户端与协调器，`async_config_entry_first_refresh` 首次校验凭据，存入 `hass.data[DOMAIN][entry_id]`；并把家庭数据中的扫地机器人登记进 HA 设备注册表（暂不创建实体）。 |

已实现端点：`GET /ai-app/family/info`（家庭列表）、`GET /ai-app/family/query`（单家庭）、`GET /ai-app/family/env/info/homepage`（家庭环境信息）、`GET /ai-app/equip/list`（设备列表）、`GET /ai-app/sweeper/rv02/getDeviceData`（扫地机实时数据）。

### 10.1 扫地机器人设备识别与登记

扫地机器人由 `Equip.productId` 区分：`RV02 = 9`、`RV03 = 26`（Pro 款，见 `sweeper/config/SweeperConfig.java` 与 `kernel/presenter/entry/Product.java`；集成侧以 `const.SWEEPER_PRODUCT_IDS = {9, 26}` 表示）。

- 设备标识：`Equip.sn`（序列号）优先，缺失时回退到 `Equip.id`（即 `equipId`，也是调用 sweeper 端点的入参，见 `GET /ai-app/sweeper/rv02/getDeviceData?equipId=<id>`）。
- 登记位置：`__init__.py` 首次刷新后遍历 `coordinator.data` 各家庭的 `Family.equips`，过滤出扫地机并写入 `device_registry.async_get_or_create(...)`；同时 `coordinator.async_add_listener` 在每次刷新后重跑，覆盖设备的新增/移除。
- 当前**只登记设备、不创建实体**（`PLATFORMS` 仍为空）；后续实体（如电量/清扫状态/开关）可在登记的基础上按 `equipId` 拉取 `SweeperDeviceData` 实现。
