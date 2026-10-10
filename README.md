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
| `docs/API工作原理.md` | API 工作机制总览（架构/网络栈/Base URL/接口组织/源码定位） |
| `docs/api/` | API 专题文档（认证机制/统一响应结构/登录流程/调用示例/集成实现） |
| `source/` | 原始安装包（Git LFS 跟踪） |
| `scripts/` | 生成器 `gen_openapi.py` 与辅助脚本 `extract_fields.sh` |
| `tests/` | 单元测试（`pytest`，见「测试」一节） |

## 集成开发状态

- [x] HACS 合规骨架（`hacs.json` / `manifest.json` / brand 资源 / 校验工作流）
- [x] 最小可加载集成（Config Flow 手动录入 Cookie 凭据）
- [x] 登录流程：短信验证码 / 邮箱密码（网易 URS SDK），另保留手动录入 Cookie 兜底
- [x] 家庭数据抽象（`models.py` / `api.py` / `coordinator.py`，装配进 `hass.data`）
- [x] 扫地机器人：设备登记 + `vacuum` 实体（清扫/暂停/回充/吸力/寻找）+ 电量/今日清扫统计 `sensor`
- [x] 扫地机器人：实时地图 `image` 实体（下载 `mapUrl` 二进制地图包，解析并渲染为 PNG；复用 App drawable 图标/纹理，默认按清扫结果显示已清扫地面/房间与轨迹，叠加虚拟墙、清扫区域与带朝向的机器人/充电座标记；支持浅色/深色/跟随界面三种配色）
- [ ] 登录流程：手机号 + 密码 / 微信
- [ ] 设备 / 家庭 / 场景实体

## 集成结构

| 文件 | 说明 |
|------|------|
| `config_flow.py` / `urs.py` | 登录配置流与网易 URS 登录 SDK 协议实现；选项流提供地图配色设置（`map_theme`） |
| `api.py` | 业务 API 客户端（Cookie 认证 + `ResponseWrapper` 解包），实现家庭域与扫地机端点 |
| `models.py` | 家庭域数据模型（`Family`/`Room`/`Member`/`FamilyEquip`/`Equip`/`FamilyEnv` 等 DTO）与扫地机数据 DTO（`SweeperDeviceData`） |
| `coordinator.py` | `DataUpdateCoordinator`，周期拉取家庭列表并缓存于 `coordinator.data`；另含 `NeteaseIntelligentSweeperCoordinator` 按 `equipId` 拉取单台扫地机实时数据 |
| `vacuum.py` | 扫地机器人 `vacuum` 实体（`StateVacuumEntity` + `VacuumActivity`：清扫/暂停/回充/吸力/寻找设备） |
| `sensor.py` | 扫地机器人 `sensor`：电量、今日清扫面积、今日清扫时长 |
| `image.py` | 扫地机器人 `image` 实体：把 `mapUrl` 地图包渲染为 PNG 展示（配色由选项 `map_theme` 决定） |
| `map_parser.py` | 扫地机二进制地图包解析（复刻 App `MapDataParser`，纯标准库） |
| `map_render.py` | 用 Pillow 把解析结果渲染为 PNG（复刻 App spirit 上色与坐标变换，直接贴 App drawable 图标/纹理；支持深色调色板；`history` 模式显示清扫结果与轨迹，叠加墙/区域/朝向标记） |
| `map_assets/` | 取自 App `res/drawable*` 的地图图标/纹理（机器人/充电座/定点透明 PNG，虚拟墙/区域/背景平铺纹理） |
| `__init__.py` | 装配：建 API 客户端与协调器，存入 `hass.data[DOMAIN][entry_id]`，登记扫地机器人设备并装配 vacuum/sensor/image 实体 |

## API 逆向

- 重新生成 OpenAPI 规范：`python3 scripts/gen_openapi.py`
- 拉取 APK 实际内容：`git lfs pull`
- 端点与机制详见 [`docs/openapi.yaml`](docs/openapi.yaml) 与 [`docs/API工作原理.md`](docs/API工作原理.md)。

## 测试

```bash
pip install -r requirements_test.txt
pytest
```

`tests/` 覆盖家庭域数据模型（`models.py`）的反序列化与容错、API 客户端（`api.py`）的认证/UA 生成、扫地机器人状态映射（`sweeper_activity`），以及地图包解析（`map_parser.py`）与渲染（`map_render.py`）。测试环境通过 `tests/conftest.py` 用合成包名加载 `const` / `models` / `api` / `map_parser` / `map_render` 这些模块，避免引入 `homeassistant` 依赖；地图测试用 `tests/map_fixture.py` 合成的地图包（不含真实户型数据），渲染测试需要 Pillow（Home Assistant 核心自带，测试环境由 `requirements_test.txt` 安装）。

## 许可

本项目代码以 [AGPL-3.0](LICENSE) 许可发布。网易智造 App 及其商标归网易所有，本项目与网易无关联。
