"""扫地机器人 vacuum 平台。

每台扫地机生成一个 :class:`NeteaseIntelligentVacuum` 实体（``StateVacuumEntity``），
暴露清扫状态与开始/暂停/停止/回充/吸力/寻找设备等控制能力。电量由 ``sensor`` 平台
独立暴露（HA 2025.8 起 vacuum 实体的 ``battery_level`` 已废弃）。

控制指令下发后采用**乐观更新**：立即把实体状态改为预期值（设备往往需要数秒才回报
新状态），同时触发一次立即刷新，待设备数据（通常由推送带来）确认或超时后回退到真实
状态（见 :data:`ASSUMED_STATE_TTL`）。刷新不改动协调器的轮询频率。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import NeteaseIntelligentApiClient
from .const import (
    DOMAIN,
    MANUFACTURER,
    NAME,
    SWEEPER_ACTION_PAUSE,
    SWEEPER_ACTION_START,
    SWEEPER_ACTION_STOP,
    SWEEPER_CTRL_LOCATE,
    SWEEPER_FAN_SPEEDS,
    SWEEPER_FAN_SPEED_TO_WIND_POWER,
    SWEEPER_MODE_AUTO_CLEAN,
    SWEEPER_MODE_CHARGE,
    SWEEPER_PREFERENCE_POWER,
    SWEEPER_WIND_POWER_TO_FAN_SPEED,
    sweeper_activity,
)
from .coordinator import (
    NeteaseIntelligentData,
    NeteaseIntelligentSweeperCoordinator,
)
from .models import Equip, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)

# 乐观状态的有效期：设备迟迟未回报新状态（或指令未生效）时据此回退到协调器数据。
ASSUMED_STATE_TTL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 网易智造扫地机器人实体。"""
    data: NeteaseIntelligentData = hass.data[DOMAIN][entry.entry_id]
    entities: list[NeteaseIntelligentVacuum] = []
    for equip in data.coordinator.sweeper_equips():
        coordinator = data.sweeper_coordinators.get(equip.id)
        if coordinator is None:
            continue
        entities.append(NeteaseIntelligentVacuum(data.client, equip, coordinator))
    async_add_entities(entities)


class NeteaseIntelligentVacuum(StateVacuumEntity):
    """网易智造扫地机器人实体。"""

    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.LOCATE
    )
    _attr_fan_speed_list = SWEEPER_FAN_SPEEDS

    def __init__(
        self,
        client: NeteaseIntelligentApiClient,
        equip: Equip,
        coordinator: NeteaseIntelligentSweeperCoordinator,
    ) -> None:
        self._client = client
        self._equip = equip
        self._coordinator = coordinator

        self._attr_name = equip.alias or equip.name or NAME
        self._attr_unique_id = equip.unique_identifier
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, equip.unique_identifier)},
            manufacturer=MANUFACTURER,
            model=equip.model or None,
            name=equip.alias or equip.name or NAME,
            suggested_area=equip.room_name or None,
        )

        # 乐观更新状态（控制指令后立即生效，待设备数据确认或超时后清除）。
        self._assumed_activity: VacuumActivity | None = None
        self._assumed_activity_until: datetime | None = None
        self._activity_before_assumed: VacuumActivity | None = None
        self._assumed_fan_speed: str | None = None
        self._assumed_fan_speed_until: datetime | None = None
        self._fan_speed_before_assumed: str | None = None

    @property
    def _data(self) -> SweeperDeviceData | None:
        """最近一次刷新的扫地机数据（失败时为 None）。"""
        if not self._coordinator.last_update_success:
            return None
        return self._coordinator.data

    @property
    def available(self) -> bool:
        """数据刷新失败时视为不可用。"""
        return self._coordinator.last_update_success

    @staticmethod
    def _activity_from(data: SweeperDeviceData) -> VacuumActivity:
        """把一次扫地机数据映射为 vacuum activity。"""
        return VacuumActivity(
            sweeper_activity(
                data.work_mode,
                data.fault_type,
                data.charge_status,
                data.fault_code,
            )
        )

    @staticmethod
    def _fan_speed_from(data: SweeperDeviceData) -> str | None:
        """把一次扫地机数据映射为吸力档位（中文名）。"""
        return SWEEPER_WIND_POWER_TO_FAN_SPEED.get(data.wind_power)

    @property
    def activity(self) -> VacuumActivity:
        """当前清扫状态；存在乐观状态时优先返回预期值。"""
        if self._assumed_activity is not None:
            return self._assumed_activity
        data = self._data
        if data is None:
            return VacuumActivity.ERROR
        return self._activity_from(data)

    @property
    def fan_speed(self) -> str | None:
        """当前吸力档位（中文名）；存在乐观状态时优先返回预期值。"""
        if self._assumed_fan_speed is not None:
            return self._assumed_fan_speed
        data = self._data
        if data is None:
            return None
        return self._fan_speed_from(data)

    def _assume_activity(self, activity: VacuumActivity) -> None:
        """记录乐观状态；命令前的实际值用于后续判定「设备是否已回报新状态」。"""
        data = self._data
        self._activity_before_assumed = (
            self._activity_from(data) if data is not None else None
        )
        self._assumed_activity = activity
        self._assumed_activity_until = dt_util.utcnow() + ASSUMED_STATE_TTL

    def _assume_fan_speed(self, fan_speed: str) -> None:
        """记录乐观吸力档位；命令前的实际值用于后续判定设备是否已回报。"""
        data = self._data
        self._fan_speed_before_assumed = (
            self._fan_speed_from(data) if data is not None else None
        )
        self._assumed_fan_speed = fan_speed
        self._assumed_fan_speed_until = dt_util.utcnow() + ASSUMED_STATE_TTL

    @callback
    def _handle_coordinator_update(self) -> None:
        """协调器更新：清除已被设备确认（或已超时）的乐观状态后写回实体。"""
        self._resolve_assumed_state()
        self.async_write_ha_state()

    def _resolve_assumed_state(self) -> None:
        """乐观状态在设备回报新值（与命令前不同）或超过有效期后清除。"""
        now = dt_util.utcnow()
        data = self._data
        if self._assumed_activity is not None:
            changed = (
                data is not None
                and self._activity_from(data) != self._activity_before_assumed
            )
            expired = (
                self._assumed_activity_until is not None
                and now >= self._assumed_activity_until
            )
            if changed or expired:
                self._assumed_activity = None
                self._assumed_activity_until = None
                self._activity_before_assumed = None
        if self._assumed_fan_speed is not None:
            changed = (
                data is not None
                and self._fan_speed_from(data) != self._fan_speed_before_assumed
            )
            expired = (
                self._assumed_fan_speed_until is not None
                and now >= self._assumed_fan_speed_until
            )
            if changed or expired:
                self._assumed_fan_speed = None
                self._assumed_fan_speed_until = None
                self._fan_speed_before_assumed = None

    async def _refresh(self) -> None:
        """控制命令发出后立即拉取一次最新数据（不改动轮询频率）。"""
        await self._coordinator.async_request_refresh()

    async def async_start(self, **kwargs: object) -> None:
        """开始自动清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_START
        )
        self._assume_activity(VacuumActivity.CLEANING)
        self.async_write_ha_state()
        await self._refresh()

    async def async_pause(self, **kwargs: object) -> None:
        """暂停清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_PAUSE
        )
        self._assume_activity(VacuumActivity.PAUSED)
        self.async_write_ha_state()
        await self._refresh()

    async def async_stop(self, **kwargs: object) -> None:
        """停止清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_STOP
        )
        self._assume_activity(VacuumActivity.IDLE)
        self.async_write_ha_state()
        await self._refresh()

    async def async_return_to_base(self, **kwargs: object) -> None:
        """回充。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_CHARGE, SWEEPER_ACTION_START
        )
        self._assume_activity(VacuumActivity.RETURNING)
        self.async_write_ha_state()
        await self._refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: object) -> None:
        """设置吸力档位。"""
        wind_power = SWEEPER_FAN_SPEED_TO_WIND_POWER.get(fan_speed)
        if wind_power is None:
            return
        await self._client.set_preference(
            self._equip.id, SWEEPER_PREFERENCE_POWER, wind_power
        )
        self._assume_fan_speed(fan_speed)
        self.async_write_ha_state()
        await self._refresh()

    async def async_locate(self, **kwargs: object) -> None:
        """寻找设备。"""
        await self._client.device_ctrl(self._equip.id, SWEEPER_CTRL_LOCATE, 1)

    async def async_added_to_hass(self) -> None:
        """订阅数据刷新，实体随协调器更新（并解析乐观状态）。"""
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )
