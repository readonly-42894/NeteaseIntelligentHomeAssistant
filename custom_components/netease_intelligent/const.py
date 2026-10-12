"""Constants for the 网易智造 integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "netease_intelligent"
NAME: Final = "网易智造"
MANUFACTURER: Final = "Netease"

# 扫地机器人型号的 productId（App 侧常量 Product.RV02=9 / Product.RV03=26，
# 见 docs/API工作原理.md 第 6 节；RV03 为 Pro 款）。
SWEEPER_PRODUCT_IDS: Final = frozenset({9, 26})

# 扫地机工作模式（``SweeperDeviceData.workMode``，字符串编码的整数，
# 见 sweeper/model/WorkModeEnum.java 的 @SerializedName 码值），按语义分组：
SWEEPER_MODE_CLEANING: Final = frozenset(
    {"1", "2", "7", "25", "30", "36", "45", "100"}
)  # 自动/手动/定点/沿边/区域/拖地/探索/计划清扫中
SWEEPER_MODE_PAUSED: Final = frozenset(
    {"4", "9", "27", "31", "37", "46", "101"}
)  # 各模式暂停中
# 回充中：用户回充（Recharge）与清扫完成后自动回充（各 *Complete_Recharge）。
# App 的 ``WorkModeConfig`` 对这些码值统一显示「回充中」（Re_Charging），并非已到座。
SWEEPER_MODE_RETURNING: Final = frozenset(
    {"5", "10", "12", "26", "32", "38", "47", "102"}
)
# 断点（低电回充续扫）：自动断点（Auto_Breakpoint）与各 *Breakpoint。
SWEEPER_MODE_BREAKPOINT: Final = frozenset(
    {"11", "28", "33", "39", "48", "103"}
)
# 空闲：各 *Free。
SWEEPER_MODE_IDLE: Final = frozenset(
    {"0", "14", "29", "35", "40", "49", "104"}
)

# 充电状态（ChargeStatusEnum）：0=未充电，1=充电中。
SWEEPER_CHARGE_CHARGING: Final = 1

# 「在充电座」的 faultCode 判据（App ``SweeperManager.isRobotInCharger()``）：
# 2101/2103/2105 表示在充电座/充电中。满电停在座上时 ``chargeStatus`` 可能为 0，
# 需据此判定 docked（与 ``chargeStatus`` 无关）。
SWEEPER_FAULT_CODE_IN_CHARGER: Final = frozenset({2101, 2103, 2105})

# 故障类型（``SweeperDeviceData.faultType``）：仅 ``1`` 表示设备故障。App 的
# ``ErrorToast.setData(faultType, faultCode)`` 只在 ``faultType == 1`` 时显示错误
# 横幅，并由 ``faultCode`` 选择 ``sweeper_<faultCode>_error_title/content`` 文案
# （见 sweeper/modules/widget/ErrorToast.java 与 HomeActivity.java:2993 调用处）。
# 注意：``faultCode`` 单独非 0 **不代表错误**——2101/2103/2105 是「在充电座/充电中」
# 等状态（SweeperManager.isRobotInCharger / SwitchMapModeUtil），2108、518 等由
# EventToast 显示为提示/告警而非错误。
SWEEPER_FAULT_TYPE_ERROR: Final = 1

# 清扫模式（ModeControlTypeEnum，setWorkMode 的 ctrltype 参数）。
SWEEPER_MODE_AUTO_CLEAN: Final = 0  # 自动清扫
SWEEPER_MODE_SIDE_CLEAN: Final = 1  # 沿边清扫
SWEEPER_MODE_MOP_CLEAN: Final = 2  # 仿真拖地
SWEEPER_MODE_CHARGE: Final = 3  # 回充
SWEEPER_MODE_SPOT_CLEAN: Final = 4  # 定点清扫
SWEEPER_MODE_AREA_CLEAN: Final = 5  # 区域清扫
SWEEPER_MODE_PATROL_CLEAN: Final = 6  # 探索建图
# 清扫动作（ModeControlValueEnum，setWorkMode 的 value 参数）。
SWEEPER_ACTION_STOP: Final = 0
SWEEPER_ACTION_START: Final = 1
SWEEPER_ACTION_PAUSE: Final = 2

# 偏好类型（PreferenceTypeEnum，setPreference 的 ctrltype 参数）。
SWEEPER_PREFERENCE_POWER: Final = 1  # 吸力（WindPowerEnum）

# 设备控制类型（DeviceControlTypeEnum，deviceCtrl 的 ctrltype 参数）。
SWEEPER_CTRL_LOCATE: Final = 3  # 寻找设备

# 吸力（WindPowerEnum）与 HA fan_speed 的互映射（0=关闭/1=安静/2=标准/3=强劲）。
SWEEPER_FAN_SPEEDS: Final = ["关闭", "安静", "标准", "强劲"]
SWEEPER_WIND_POWER_TO_FAN_SPEED: Final = {
    0: "关闭", 1: "安静", 2: "标准", 3: "强劲",
}
SWEEPER_FAN_SPEED_TO_WIND_POWER: Final = {
    "关闭": 0, "安静": 1, "标准": 2, "强劲": 3,
}


def sweeper_activity(
    work_mode: str,
    fault_type: int,
    charge_status: int,
    fault_code: int = 0,
) -> str:
    """把扫地机数据映射到 HA vacuum 的 ``activity``（返回 ``VacuumActivity`` 成员名）。

    返回 ``cleaning`` / ``paused`` / ``returning`` / ``docked`` / ``idle`` /
    ``error`` 之一；纯函数，便于单元测试。

    错误判据为 ``faultType == 1``（App 的 ``ErrorToast`` 仅据此显示错误横幅），
    而非 ``faultCode``——``faultCode`` 中的 2101/2103/2105 等是在充电座/充电中等
    状态码，不代表错误，反而用于判定「在充电座」。

    「在充电座」（``docked``）判据：``chargeStatus == 1``（充电中）或 ``faultCode``
    ∈ :data:`SWEEPER_FAULT_CODE_IN_CHARGER`（App 的 ``SweeperManager.isRobotInCharger()``，
    覆盖满电停在座上、``chargeStatus`` 为 0 的情形）。回充中（Recharge /
    *Complete_Recharge）与断点在未到座时视为 ``returning``。
    """
    if fault_type == SWEEPER_FAULT_TYPE_ERROR:
        return "error"
    if work_mode in SWEEPER_MODE_CLEANING:
        return "cleaning"
    if work_mode in SWEEPER_MODE_PAUSED:
        return "paused"
    docked = (
        charge_status == SWEEPER_CHARGE_CHARGING
        or fault_code in SWEEPER_FAULT_CODE_IN_CHARGER
    )
    if work_mode in SWEEPER_MODE_RETURNING or work_mode in SWEEPER_MODE_BREAKPOINT:
        # 回充中 / 断点（低电回充续扫）：已到座为 docked，否则为回充中。
        return "docked" if docked else "returning"
    # 空闲 / 未知 / 空模式（含 Loading "-1"）：在座为 docked，否则 idle。
    return "docked" if docked else "idle"


def sweeper_battery_percent(battery: int) -> int:
    """把接口 ``battery``（100=空电、200=满电）换算为 0-100 百分比。

    App 侧 ``HomeActivity`` 显示的百分比为 ``getBattery() - 100``（并对 <=0
    钳制为 1），``AutoControlView`` 以 ``getBattery() == 200`` 判定充电完成；
    这里钳制到 ``[0, 100]`` 区间，不复制 App 的「<=0 显示为 1」UI 特判。
    """
    return max(0, min(100, battery - 100))


def sweeper_battery_charging(charge_status: int) -> bool:
    """电池是否正在充电（对应 HA ``battery_charging`` 二进制传感器）。

    App ``HomeActivity`` 以 ``chargeStatus == ChargeStatusEnum.Charging`` 作为
    ``BatteryView.setData(battery, ...)`` 的充电标志；前端据此给电量实体显示
    充电图标/动效。
    """
    return charge_status == SWEEPER_CHARGE_CHARGING


# RV03（Pro 款）的 ``productId``（App ``SweeperConfig``：RV02=9、RV03=26）；
# 清扫模式选项据此决定——Pro 提供「探索建图」、非 Pro 提供「沿边清扫」，复刻官方
# ``ModeControlDialog``（``SweeperConfig.isPro()`` 时把 Side 换成 Patrol）。
SWEEPER_PRO_PRODUCT_ID: Final = 26

# 清扫模式选择实体的选项标签（取自 App 官方文案：
# ``sweeper_auto_clean`` / ``sweeper_auto_mop`` / ``sweeper_side_clean`` /
# ``sweeper_patrol_clean``）。
SWEEPER_CLEAN_MODE_AUTO: Final = "自动清扫"
SWEEPER_CLEAN_MODE_MOP: Final = "仿真拖地"
SWEEPER_CLEAN_MODE_SIDE: Final = "沿边清扫"
SWEEPER_CLEAN_MODE_PATROL: Final = "探索建图"

# 各机型可选清扫模式（顺序与官方 ModeControlDialog 的 modeList 一致：Auto、Mop，
# 再按是否 Pro 追加 Patrol / Side）。
SWEEPER_CLEAN_MODES: Final = (
    SWEEPER_CLEAN_MODE_AUTO,
    SWEEPER_CLEAN_MODE_MOP,
    SWEEPER_CLEAN_MODE_SIDE,
)
SWEEPER_CLEAN_MODES_PRO: Final = (
    SWEEPER_CLEAN_MODE_AUTO,
    SWEEPER_CLEAN_MODE_MOP,
    SWEEPER_CLEAN_MODE_PATROL,
)

# 选项标签 → setWorkMode 的 ctrltype（ModeControlTypeEnum）。
SWEEPER_CLEAN_MODE_TO_CTRLTYPE: Final = {
    SWEEPER_CLEAN_MODE_AUTO: SWEEPER_MODE_AUTO_CLEAN,
    SWEEPER_CLEAN_MODE_MOP: SWEEPER_MODE_MOP_CLEAN,
    SWEEPER_CLEAN_MODE_SIDE: SWEEPER_MODE_SIDE_CLEAN,
    SWEEPER_CLEAN_MODE_PATROL: SWEEPER_MODE_PATROL_CLEAN,
}

# 各清扫模式对应的 workMode 码值（WorkModeEnum，字符串编码）。
SWEEPER_SIDE_MODE_CODES: Final = frozenset({"25", "26", "27", "28", "29"})
SWEEPER_MOP_MODE_CODES: Final = frozenset({"36", "37", "38", "39", "40"})
SWEEPER_PATROL_MODE_CODES: Final = frozenset({"45", "46", "47", "48", "49"})


def sweeper_is_pro(product_id: int) -> bool:
    """是否为 Pro 款扫地机（RV03）。"""
    return product_id == SWEEPER_PRO_PRODUCT_ID


def sweeper_clean_modes(product_id: int) -> tuple[str, ...]:
    """该机型可选的清扫模式（Pro 用「探索建图」，非 Pro 用「沿边清扫」）。"""
    return SWEEPER_CLEAN_MODES_PRO if sweeper_is_pro(product_id) else SWEEPER_CLEAN_MODES


def sweeper_clean_mode(work_mode: str) -> str | None:
    """把 ``workMode`` 映射为当前清扫模式标签（返回 :data:`SWEEPER_CLEAN_MODE_*` 之一）。

    复刻 App ``HomeActivity.getCurrentModeControlType()``：沿边/拖地/探索各有独立
    码值分组，其余（自动/定点/区域/计划/手动/回充/Loading 等）统一归入「自动清扫」。
    未知码值返回 ``None``；纯函数，便于单元测试。
    """
    if work_mode in SWEEPER_SIDE_MODE_CODES:
        return SWEEPER_CLEAN_MODE_SIDE
    if work_mode in SWEEPER_MOP_MODE_CODES:
        return SWEEPER_CLEAN_MODE_MOP
    if work_mode in SWEEPER_PATROL_MODE_CODES:
        return SWEEPER_CLEAN_MODE_PATROL
    if work_mode in (
        SWEEPER_MODE_CLEANING
        | SWEEPER_MODE_PAUSED
        | SWEEPER_MODE_RETURNING
        | SWEEPER_MODE_BREAKPOINT
        | SWEEPER_MODE_IDLE
    ) or work_mode == "-1":
        return SWEEPER_CLEAN_MODE_AUTO
    return None


# 家庭数据轮询间隔（见 coordinator.py 的 NeteaseIntelligentCoordinator）。
UPDATE_INTERVAL: Final = timedelta(minutes=5)

# 扫地机实时数据（``getDeviceData``）轮询间隔（见 coordinator.py 的
# NeteaseIntelligentSweeperCoordinator）。轮询是**基础数据源**：负责推送不覆盖的
# 字段（todayCleanSize/todayCleanTime 等）与首次全量基线。推送在线时进一步降频到
# ``SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE``，推送不可用时用 ``UPDATE_INTERVAL``。
# 注意：**任何情况下都不低于此频率**——状态时效由推送承担，给轮询提速会打爆设备/云。
SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE: Final = timedelta(minutes=10)


# 官方推送通道（Socket.IO 长连接；协议见 push_protocol.py 与 docs/api/集成实现.md
# 「官方推送通道」小节，实抓来源见 scripts/push_probe.py）。
PUSH_HOST: Final = "wss://3c.163.com/socket.io/"
PUSH_ENV: Final = "r"  # release 环境（AlcsConstant.MODE_VALUE_READ）
PUSH_APP_NAME: Final = "intelligent"  # R.string.host_push_product_name
PUSH_APP_VERSION: Final = "5.3.5"  # versionName
PUSH_APP_SOURCE: Final = "Release"  # assets/source 首段
PUSH_PLATFORM: Final = "android"
PUSH_TOPICS: Final = ("noti", "event")
PUSH_PING_INTERVAL: Final = 20  # 客户端主动心跳间隔（秒；EIO v3 客户端 ping）
PUSH_RECONNECT_MIN: Final = 5  # 重连退避下限（秒）
PUSH_RECONNECT_MAX: Final = 60  # 重连退避上限（秒）

# 设备页事件（EventUtil.EVENT_TYPE_ENTRY_PAGE/EXIT_PAGE）：
# 进入设备页=开始推送，离开设备页=关闭推送。
PUSH_EVENT_ENTRY_PAGE: Final = 1
PUSH_EVENT_EXIT_PAGE: Final = 2

# 集成抛出的 HA 事件：收到官方 ``noti`` 主题通知、且非设备事件（opType != 10）时，
# 在事件总线上触发（见 __init__.py / push.py，协议见 docs/api/集成实现.md
#「通知（noti 主题）」小节）。
EVENT_NOTIFICATION: Final = "netease_intelligent_notification"


def push_uid(pid: int) -> str:
    """推送通道的用户绑定标识 ``uid``（App 拼装：ENV_APPNAME_pid）。"""
    return f"{PUSH_ENV}_{PUSH_APP_NAME}_{pid}"


# 线上环境的 API Base URL，见 docs/API工作原理.md 第 3 节。
BASE_URL: Final = "https://3c.163.com"

# 配置项：认证走 Cookie，见 docs/API工作原理.md 第 4 节。
# UA-INFO 不在此列：登录/手动录入流程都不写入，api.py 用 build_ua_info() 自动生成。
CONF_TOKEN: Final = "token"  # Cookie: ONE_TOKEN
CONF_TOKEN_ID: Final = "token_id"  # Cookie: ONE_TOKEN_ID

# 登录表单字段（登录流程，见 config_flow.py）
CONF_LOGIN_TYPE: Final = "login_type"
CONF_PHONE: Final = "phone"
CONF_SMS_CODE: Final = "sms_code"
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"

# 地图配色选项（image 实体，见 image.py / config_flow.py）：
# light=浅色（默认）、dark=深色。
CONF_MAP_THEME: Final = "map_theme"
MAP_THEME_LIGHT: Final = "light"
MAP_THEME_DARK: Final = "dark"
MAP_THEME_OPTIONS: Final = (MAP_THEME_LIGHT, MAP_THEME_DARK)
DEFAULT_MAP_THEME: Final = MAP_THEME_LIGHT

# 地图朝向（旋转）选项（image 实体，见 image.py / config_flow.py）：
# 以 90° 为步长、逆时针为正（Pillow ``Image.rotate`` 约定），"0" 为不旋转（默认）。
# 用于把渲染出的地图整体转到与真实户型/App 视角一致的朝向。
CONF_MAP_ROTATION: Final = "map_rotation"
MAP_ROTATION_OPTIONS: Final = ("0", "90", "180", "270")
DEFAULT_MAP_ROTATION: Final = "0"


def map_rotation_degrees(value: object) -> int:
    """把配置中的地图朝向规整为 ``0``/``90``/``180``/``270``（逆时针）。

    选项以字符串存储（HA ``SelectSelector`` 只接受字符串）；本函数兼容字符串与
    数字输入，非法值回退 ``0``，并把角度吸附到最近的 90° 步长。
    """
    try:
        degrees = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    snapped = (degrees + 45) // 90 * 90 % 360
    return snapped


DEFAULT_NAME: Final = NAME
