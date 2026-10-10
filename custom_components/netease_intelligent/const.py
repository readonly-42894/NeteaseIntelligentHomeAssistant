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
SWEEPER_MODE_RETURNING: Final = frozenset({"5"})  # 回充中
SWEEPER_MODE_BREAKPOINT: Final = frozenset(
    {"28", "33", "39", "48", "103"}
)  # 断点（低电回充续扫）
SWEEPER_MODE_DOCKED: Final = frozenset(
    {"10", "12", "26", "32", "38", "47", "102"}
)  # 各模式充电完成
SWEEPER_MODE_IDLE: Final = frozenset(
    {"0", "14", "29", "35", "40", "49", "104"}
)  # 各模式空闲

# 充电状态（ChargeStatusEnum）：0=未充电，1=充电中。
SWEEPER_CHARGE_CHARGING: Final = 1

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
SWEEPER_MODE_CHARGE: Final = 3  # 回充
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


def sweeper_activity(work_mode: str, fault_type: int, charge_status: int) -> str:
    """把扫地机数据映射到 HA vacuum 的 ``activity``（返回 ``VacuumActivity`` 成员名）。

    返回 ``cleaning`` / ``paused`` / ``returning`` / ``docked`` / ``idle`` /
    ``error`` 之一；纯函数，便于单元测试。

    错误判据为 ``faultType == 1``（App 的 ``ErrorToast`` 仅据此显示错误横幅），
    而非 ``faultCode``——``faultCode`` 中的 2101/2103/2105 等是在充电座/充电中等
    状态码，不代表错误。
    """
    if fault_type == SWEEPER_FAULT_TYPE_ERROR:
        return "error"
    if work_mode in SWEEPER_MODE_CLEANING:
        return "cleaning"
    if work_mode in SWEEPER_MODE_PAUSED:
        return "paused"
    if work_mode in SWEEPER_MODE_RETURNING:
        return "returning"
    if work_mode in SWEEPER_MODE_DOCKED:
        return "docked"
    if work_mode in SWEEPER_MODE_BREAKPOINT:
        # 断点（低电回充续扫）：充电中视为 docked，否则视为回充中。
        return "docked" if charge_status == SWEEPER_CHARGE_CHARGING else "returning"
    # 空闲 / 未知 / 空模式（含 Loading "-1"）：按充电状态兜底，
    # 充电中视为 docked（在充电座上），否则视为 idle。
    return "docked" if charge_status == SWEEPER_CHARGE_CHARGING else "idle"


def sweeper_battery_percent(battery: int) -> int:
    """把接口 ``battery``（100=空电、200=满电）换算为 0-100 百分比。

    App 侧 ``HomeActivity`` 显示的百分比为 ``getBattery() - 100``（并对 <=0
    钳制为 1），``AutoControlView`` 以 ``getBattery() == 200`` 判定充电完成；
    这里钳制到 ``[0, 100]`` 区间，不复制 App 的「<=0 显示为 1」UI 特判。
    """
    return max(0, min(100, battery - 100))

# 家庭数据轮询间隔（见 coordinator.py）。
UPDATE_INTERVAL: Final = timedelta(minutes=5)

# 线上环境的 API Base URL，见 docs/API工作原理.md 第 3 节。
BASE_URL: Final = "https://3c.163.com"

# 配置项：认证走 Cookie，见 docs/API工作原理.md 第 4 节。
CONF_TOKEN: Final = "token"  # Cookie: ONE_TOKEN
CONF_TOKEN_ID: Final = "token_id"  # Cookie: ONE_TOKEN_ID
CONF_UA_INFO: Final = "ua_info"  # Cookie: UA-INFO

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

DEFAULT_NAME: Final = NAME
