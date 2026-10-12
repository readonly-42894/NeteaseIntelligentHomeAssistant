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
    """回充中码值（Recharge 与各 *Complete_Recharge）未到座 → returning。"""
    for wm in ("5", "10", "12", "26", "32", "38", "47", "102"):
        assert c.sweeper_activity(wm, 0, 0) == "returning"


def test_sweeper_activity_returning_docked_when_on_charger() -> None:
    """回充中码值充电中/在座 → docked（充电只有在座上才可能）。"""
    for wm in ("5", "10", "12", "26", "32", "38", "47", "102"):
        assert c.sweeper_activity(wm, 0, 1) == "docked"
        assert c.sweeper_activity(wm, 0, 0, 2103) == "docked"


def test_sweeper_activity_docked_by_fault_code() -> None:
    """满电停在座上（chargeStatus=0）由 faultCode 2101/2103/2105 判定 docked。"""
    for fault_code in (2101, 2103, 2105):
        assert c.sweeper_activity("0", 0, 0, fault_code) == "docked"  # 空闲
        assert c.sweeper_activity("11", 0, 0, fault_code) == "docked"  # 断点充电中
        assert c.sweeper_activity("10", 0, 0, fault_code) == "docked"  # 停在座上
    # 其它 faultCode 不参与「在座」判定。
    assert c.sweeper_activity("0", 0, 0, 2100) == "idle"
    assert c.sweeper_activity("11", 0, 0, 2100) == "returning"


def test_sweeper_activity_idle_by_charge_status() -> None:
    """空闲码值按充电状态区分 idle / docked。"""
    for wm in ("0", "14", "29", "35", "40", "49", "104"):
        assert c.sweeper_activity(wm, 0, 0) == "idle"
        assert c.sweeper_activity(wm, 0, 1) == "docked"


def test_sweeper_activity_breakpoint() -> None:
    """断点码值（含 Auto_Breakpoint=11）：充电/在座 → docked，否则 returning。"""
    for wm in ("11", "28", "33", "39", "48", "103"):
        assert c.sweeper_activity(wm, 0, 1) == "docked"
        assert c.sweeper_activity(wm, 0, 0) == "returning"


def test_sweeper_activity_unknown_fallback() -> None:
    """未知/空码值按在座状态兜底。"""
    assert c.sweeper_activity("", 0, 0) == "idle"
    assert c.sweeper_activity("", 0, 1) == "docked"
    assert c.sweeper_activity("", 0, 0, 2103) == "docked"
    assert c.sweeper_activity("-1", 0, 1) == "docked"  # Loading


def test_sweeper_mode_sets_cover_all_known_modes() -> None:
    """分组完整覆盖 WorkModeEnum 全部码值且互不重叠（漏码会落兜底、误判状态）。"""
    known = {
        "0", "1", "2", "4", "5", "7", "9", "10", "11", "12", "14",
        "25", "26", "27", "28", "29", "30", "31", "32", "33", "35",
        "36", "37", "38", "39", "40", "45", "46", "47", "48", "49",
        "100", "101", "102", "103", "104",
    }
    groups = (
        c.SWEEPER_MODE_CLEANING,
        c.SWEEPER_MODE_PAUSED,
        c.SWEEPER_MODE_RETURNING,
        c.SWEEPER_MODE_BREAKPOINT,
        c.SWEEPER_MODE_IDLE,
    )
    covered = set().union(*groups)
    assert covered == known
    assert "-1" not in covered  # Loading 走兜底
    for index, group in enumerate(groups):
        for other in groups[index + 1 :]:
            assert not (group & other)


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


def test_sweeper_battery_charging() -> None:
    """充电状态（ChargeStatusEnum）→ battery_charging 布尔。"""
    assert c.sweeper_battery_charging(1) is True
    assert c.sweeper_battery_charging(0) is False
    assert c.sweeper_battery_charging(2) is False


def test_sweeper_poll_interval_not_faster() -> None:
    """轮询不提速：推送在线间隔更长，且任何情况下都不短于默认间隔。"""
    assert c.SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE >= c.UPDATE_INTERVAL


def test_map_rotation_degrees_normalizes() -> None:
    """地图朝向规整为 0/90/180/270（字符串/数字兼容，按最近 90° 吸附）。"""
    assert c.map_rotation_degrees("0") == 0
    assert c.map_rotation_degrees("90") == 90
    assert c.map_rotation_degrees("180") == 180
    assert c.map_rotation_degrees("270") == 270
    assert c.map_rotation_degrees(90) == 90
    assert c.map_rotation_degrees(360) == 0
    assert c.map_rotation_degrees(-90) == 270
    assert c.map_rotation_degrees(450) == 90
    assert c.map_rotation_degrees(44) == 0
    assert c.map_rotation_degrees(46) == 90


def test_map_rotation_degrees_invalid_fallback() -> None:
    """缺失/非法朝向值回退 0（默认不旋转）。"""
    assert c.map_rotation_degrees(None) == 0
    assert c.map_rotation_degrees("") == 0
    assert c.map_rotation_degrees("abc") == 0


def test_sweeper_clean_mode_mapping() -> None:
    """workMode 码值 → 清扫模式（复刻 App getCurrentModeControlType）。"""
    # 自动清扫：自动/手动/定点/区域/计划/回充等，均归入「自动清扫」。
    for wm in ("0", "1", "2", "4", "7", "10", "11", "30", "100", "104"):
        assert c.sweeper_clean_mode(wm) == c.SWEEPER_CLEAN_MODE_AUTO
    assert c.sweeper_clean_mode("-1") == c.SWEEPER_CLEAN_MODE_AUTO  # Loading
    # 拖地/沿边/探索为独立分组。
    for wm in ("36", "37", "38", "39", "40"):
        assert c.sweeper_clean_mode(wm) == c.SWEEPER_CLEAN_MODE_MOP
    for wm in ("25", "26", "27", "28", "29"):
        assert c.sweeper_clean_mode(wm) == c.SWEEPER_CLEAN_MODE_SIDE
    for wm in ("45", "46", "47", "48", "49"):
        assert c.sweeper_clean_mode(wm) == c.SWEEPER_CLEAN_MODE_PATROL
    # 未知码值不猜测。
    assert c.sweeper_clean_mode("999") is None
    assert c.sweeper_clean_mode("") is None


def test_sweeper_clean_mode_covers_all_known_modes() -> None:
    """全部已知 workMode 码值都能映射到某个清扫模式（漏码会让 select 选项缺失）。"""
    known = {
        "0", "1", "2", "4", "5", "7", "9", "10", "11", "12", "14",
        "25", "26", "27", "28", "29", "30", "31", "32", "33", "35",
        "36", "37", "38", "39", "40", "45", "46", "47", "48", "49",
        "100", "101", "102", "103", "104", "-1",
    }
    for code in known:
        assert c.sweeper_clean_mode(code) is not None, code


def test_sweeper_clean_modes_by_product() -> None:
    """清扫模式选项按机型区分：Pro（RV03=26）用探索建图，非 Pro（RV02=9）用沿边清扫。"""
    assert c.sweeper_is_pro(26) is True
    assert c.sweeper_is_pro(9) is False
    assert c.sweeper_clean_modes(9) == c.SWEEPER_CLEAN_MODES
    assert c.sweeper_clean_modes(26) == c.SWEEPER_CLEAN_MODES_PRO
    assert c.SWEEPER_CLEAN_MODE_SIDE in c.sweeper_clean_modes(9)
    assert c.SWEEPER_CLEAN_MODE_SIDE not in c.sweeper_clean_modes(26)
    assert c.SWEEPER_CLEAN_MODE_PATROL in c.sweeper_clean_modes(26)
    assert c.SWEEPER_CLEAN_MODE_PATROL not in c.sweeper_clean_modes(9)


def test_sweeper_clean_mode_ctrltype_mapping() -> None:
    """选项标签 → setWorkMode ctrltype（ModeControlTypeEnum 码值），且覆盖全部选项。"""
    assert c.SWEEPER_CLEAN_MODE_TO_CTRLTYPE[c.SWEEPER_CLEAN_MODE_AUTO] == 0
    assert c.SWEEPER_CLEAN_MODE_TO_CTRLTYPE[c.SWEEPER_CLEAN_MODE_SIDE] == 1
    assert c.SWEEPER_CLEAN_MODE_TO_CTRLTYPE[c.SWEEPER_CLEAN_MODE_MOP] == 2
    assert c.SWEEPER_CLEAN_MODE_TO_CTRLTYPE[c.SWEEPER_CLEAN_MODE_PATROL] == 6
    for option in c.SWEEPER_CLEAN_MODES_PRO:
        assert option in c.SWEEPER_CLEAN_MODE_TO_CTRLTYPE
