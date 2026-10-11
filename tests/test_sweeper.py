"""扫地机业务逻辑（``const.sweeper_activity`` 与常量映射）单元测试。

``sweeper_activity`` 是纯函数（无 homeassistant 依赖），用于把扫地机实时数据
映射为 HA vacuum 的 ``VacuumActivity`` 成员名，随 ``const.py`` 被 ``conftest.py``
以合成包名加载。
"""

from __future__ import annotations

import netease_intelligent.const as c
import netease_intelligent.models as m


def test_sweeper_activity_fault() -> None:
    """faultType == 1 时映射为 error，无论其它字段。"""
    assert c.sweeper_activity("1", 1, 0) == "error"
    assert c.sweeper_activity("", 1, 1) == "error"


def test_sweeper_activity_fault_type_not_error() -> None:
    """非 1 的 faultType 不算错误（如真机 faultType=3 配合 faultCode=2103 充电中）。"""
    # 空闲/充电中 + faultType=3 → 不应是 error
    assert c.sweeper_activity("0", 3, 1) == "docked"
    assert c.sweeper_activity("0", 3, 0) == "idle"
    assert c.sweeper_activity("1", 3, 0) == "cleaning"


def test_sweeper_activity_cleaning() -> None:
    """清扫中码值 → cleaning。"""
    for wm in ("1", "2", "7", "25", "30", "36", "45", "100"):
        assert c.sweeper_activity(wm, 0, 0) == "cleaning"


def test_sweeper_activity_paused() -> None:
    """暂停码值 → paused。"""
    for wm in ("4", "9", "27", "31", "37", "46", "101"):
        assert c.sweeper_activity(wm, 0, 0) == "paused"


def test_sweeper_activity_returning() -> None:
    """回充（5）→ returning。"""
    assert c.sweeper_activity("5", 0, 0) == "returning"


def test_sweeper_activity_docked() -> None:
    """充电完成码值 → docked。"""
    for wm in ("10", "12", "26", "32", "38", "47", "102"):
        assert c.sweeper_activity(wm, 0, 0) == "docked"


def test_sweeper_activity_idle_by_charge_status() -> None:
    """空闲码值按充电状态区分 idle / docked。"""
    for wm in ("0", "14", "29", "35", "40", "49", "104"):
        assert c.sweeper_activity(wm, 0, 0) == "idle"
        assert c.sweeper_activity(wm, 0, 1) == "docked"


def test_sweeper_activity_breakpoint() -> None:
    """断点码值：充电中 → docked，未充电 → returning。"""
    for wm in ("28", "33", "39", "48", "103"):
        assert c.sweeper_activity(wm, 0, 1) == "docked"
        assert c.sweeper_activity(wm, 0, 0) == "returning"


def test_sweeper_activity_unknown_fallback() -> None:
    """未知/空码值按充电状态兜底。"""
    assert c.sweeper_activity("", 0, 0) == "idle"
    assert c.sweeper_activity("", 0, 1) == "docked"
    assert c.sweeper_activity("-1", 0, 1) == "docked"  # Loading


def test_fan_speed_mapping_roundtrip() -> None:
    """吸力档位与 windPower 码值互映射。"""
    assert c.SWEEPER_WIND_POWER_TO_FAN_SPEED[0] == "关闭"
    assert c.SWEEPER_WIND_POWER_TO_FAN_SPEED[3] == "强劲"
    for speed in c.SWEEPER_FAN_SPEEDS:
        assert c.SWEEPER_WIND_POWER_TO_FAN_SPEED[c.SWEEPER_FAN_SPEED_TO_WIND_POWER[speed]] == speed


def test_equip_unique_identifier() -> None:
    """唯一标识：sn 优先，回退 id。"""
    assert m.Equip(sn="SN1", id="eq1").unique_identifier == "SN1"
    assert m.Equip(sn="", id="eq1").unique_identifier == "eq1"
    assert m.Equip(sn="", id="").unique_identifier == ""


def test_sweeper_battery_percent() -> None:
    """接口 battery（100=空/200=满）换算为 0-100 百分比并钳制。"""
    assert c.sweeper_battery_percent(100) == 0
    assert c.sweeper_battery_percent(200) == 100
    assert c.sweeper_battery_percent(150) == 50
    assert c.sweeper_battery_percent(99) == 0
    assert c.sweeper_battery_percent(201) == 100
    assert c.sweeper_battery_percent(0) == 0
    assert c.sweeper_battery_percent(-10) == 0


def test_sweeper_is_active() -> None:
    """自适应轮询：仅清扫中/回充中视为活动（其余状态回落到长间隔）。"""
    assert c.sweeper_is_active("1", 0, 0) is True  # 清扫中
    assert c.sweeper_is_active("5", 0, 0) is True  # 回充中
    assert c.sweeper_is_active("28", 0, 0) is True  # 断点未充电 → returning
    assert c.sweeper_is_active("4", 0, 0) is False  # 暂停
    assert c.sweeper_is_active("0", 0, 1) is False  # 空闲且充电中 → docked
    assert c.sweeper_is_active("10", 0, 0) is False  # 充电完成
    assert c.sweeper_is_active("1", 1, 0) is False  # 故障 → error


def test_sweeper_poll_intervals() -> None:
    """活动间隔短于空闲间隔；空闲间隔复用家庭数据间隔。"""
    assert c.SWEEPER_UPDATE_INTERVAL_ACTIVE < c.SWEEPER_UPDATE_INTERVAL_IDLE
    assert c.SWEEPER_UPDATE_INTERVAL_IDLE == c.UPDATE_INTERVAL
    assert c.SWEEPER_COMMAND_ACTIVE_WINDOW > c.SWEEPER_UPDATE_INTERVAL_ACTIVE
