"""扫地机器人 vacuum 平台。

每台扫地机生成一个 :class:`NeteaseIntelligentVacuum` 实体（``StateVacuumEntity``），
暴露清扫状态与开始/暂停/停止/回充/吸力/寻找设备等控制能力。电量由 ``sensor`` 平台
独立暴露（HA 2025.8 起 vacuum 实体的 ``battery_level`` 已废弃）。
"""

from __future__ import annotations

import logging

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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

    @property
    def activity(self) -> VacuumActivity:
        """当前清扫状态（映射 workMode/faultCode/chargeStatus）。"""
        data = self._data
        if data is None:
            return VacuumActivity.ERROR
        return VacuumActivity(
            sweeper_activity(data.work_mode, data.fault_code, data.charge_status)
        )

    @property
    def fan_speed(self) -> str | None:
        """当前吸力档位（中文名，见 ``SWEEPER_FAN_SPEEDS``）。"""
        data = self._data
        if data is None:
            return None
        return SWEEPER_WIND_POWER_TO_FAN_SPEED.get(data.wind_power)

    async def _refresh(self) -> None:
        """控制命令发出后立即拉取最新数据。"""
        await self._coordinator.async_request_refresh()

    async def async_start(self, **kwargs: object) -> None:
        """开始自动清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_START
        )
        await self._refresh()

    async def async_pause(self, **kwargs: object) -> None:
        """暂停清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_PAUSE
        )
        await self._refresh()

    async def async_stop(self, **kwargs: object) -> None:
        """停止清扫。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_AUTO_CLEAN, SWEEPER_ACTION_STOP
        )
        await self._refresh()

    async def async_return_to_base(self, **kwargs: object) -> None:
        """回充。"""
        await self._client.set_work_mode(
            self._equip.id, SWEEPER_MODE_CHARGE, SWEEPER_ACTION_START
        )
        await self._refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: object) -> None:
        """设置吸力档位。"""
        wind_power = SWEEPER_FAN_SPEED_TO_WIND_POWER.get(fan_speed)
        if wind_power is None:
            return
        await self._client.set_preference(
            self._equip.id, SWEEPER_PREFERENCE_POWER, wind_power
        )
        await self._refresh()

    async def async_locate(self, **kwargs: object) -> None:
        """寻找设备。"""
        await self._client.device_ctrl(self._equip.id, SWEEPER_CTRL_LOCATE, 1)

    async def async_added_to_hass(self) -> None:
        """订阅数据刷新，实体随协调器更新。"""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
