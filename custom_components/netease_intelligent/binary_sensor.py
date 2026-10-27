"""扫地机器人 binary_sensor 平台。

每台扫地机生成一个「充电中」二进制传感器（``device_class: battery_charging``）。
电量由 ``sensor`` 平台独立暴露，Home Assistant 前端据**同设备的** ``battery_charging``
实体决定是否给电量实体显示充电图标/动效（见前端 ``battery_icon.ts`` /
``get_states.ts``），因此该实体是电量「充电状态」得以正确显示的前提。

复刻 App ``HomeActivity`` 的 ``BatteryView.setData(battery, chargeStatus ==
ChargeStatusEnum.Charging)``：``is_on`` 即 ``chargeStatus == Charging``。
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, NAME, sweeper_battery_charging
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
    """Set up 网易智造扫地机器人充电状态实体。"""
    data: NeteaseIntelligentData = hass.data[DOMAIN][entry.entry_id]
    entities: list[NeteaseIntelligentChargingSensor] = []
    for equip in data.coordinator.sweeper_equips():
        coordinator = data.sweeper_coordinators.get(equip.id)
        if coordinator is None:
            continue
        entities.append(NeteaseIntelligentBatteryChargingSensor(equip, coordinator))
    async_add_entities(entities)


class NeteaseIntelligentBatteryChargingSensor(BinarySensorEntity):
    """网易智造扫地机器人「充电中」二进制传感器。"""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    # 实体名由 device_class 提供（core 已内置本地化，不设 translation_key）；
    # 标记为诊断实体（同 roborock/nuki 的 battery_charging 惯例）。
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        equip: Equip,
        coordinator: NeteaseIntelligentSweeperCoordinator,
    ) -> None:
        self._equip = equip
        self._coordinator = coordinator

        self._attr_unique_id = f"{equip.unique_identifier}_battery_charging"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, equip.unique_identifier)},
            manufacturer=MANUFACTURER,
            model=equip.sweeper_model,
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
    def is_on(self) -> bool | None:
        """电池是否正在充电（``chargeStatus == Charging``）。"""
        data = self._data
        if data is None:
            return None
        return sweeper_battery_charging(data.charge_status)

    async def async_added_to_hass(self) -> None:
        """订阅数据刷新，实体随协调器更新。"""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
