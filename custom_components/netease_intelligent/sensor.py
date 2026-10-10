"""扫地机器人 sensor 平台。

每台扫地机生成 3 个传感器：电量（%）、今日清扫面积（㎡）、今日清扫时长（分钟）。
数据来源为扫地机实时数据协调器 ``NeteaseIntelligentSweeperCoordinator``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, NAME, sweeper_battery_percent
from .coordinator import (
    NeteaseIntelligentData,
    NeteaseIntelligentSweeperCoordinator,
)
from .models import Equip, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SweeperSensorDescription(SensorEntityDescription):
    """扫地机传感器描述：``key`` 为 ``SweeperDeviceData`` 字段名，``scale`` 为缩放。"""

    key: str
    scale: float = 1.0


SENSOR_DESCRIPTIONS: tuple[SweeperSensorDescription, ...] = (
    SweeperSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        translation_key="battery",
    ),
    SweeperSensorDescription(
        key="today_clean_size",
        scale=0.01,  # 接口返回面积 ×100，除以 100 得平方米
        device_class=SensorDeviceClass.AREA,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        translation_key="today_clean_size",
    ),
    SweeperSensorDescription(
        key="today_clean_time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        translation_key="today_clean_time",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 网易智造扫地机器人传感器。"""
    data: NeteaseIntelligentData = hass.data[DOMAIN][entry.entry_id]
    entities: list[NeteaseIntelligentSensor] = []
    for equip in data.coordinator.sweeper_equips():
        coordinator = data.sweeper_coordinators.get(equip.id)
        if coordinator is None:
            continue
        entities.extend(
            NeteaseIntelligentSensor(equip, coordinator, description)
            for description in SENSOR_DESCRIPTIONS
        )
    async_add_entities(entities)


class NeteaseIntelligentSensor(SensorEntity):
    """网易智造扫地机器人传感器实体。"""

    _attr_has_entity_name = True

    entity_description: SweeperSensorDescription

    def __init__(
        self,
        equip: Equip,
        coordinator: NeteaseIntelligentSweeperCoordinator,
        description: SweeperSensorDescription,
    ) -> None:
        self._equip = equip
        self._coordinator = coordinator
        self.entity_description = description

        self._attr_unique_id = f"{equip.unique_identifier}_{description.key}"
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
    def native_value(self) -> int | float | None:
        """传感器读数（按描述缩放）。"""
        data = self._data
        if data is None:
            return None
        raw = getattr(data, self.entity_description.key, None)
        if raw is None:
            return None
        if self.entity_description.key == "battery":
            # 接口 battery 为 100=空电/200=满电，减 100 得 0-100 百分比。
            return sweeper_battery_percent(raw)
        value = raw * self.entity_description.scale
        if self.entity_description.scale == 1.0:
            return int(value)
        return value

    async def async_added_to_hass(self) -> None:
        """订阅数据刷新，实体随协调器更新。"""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )