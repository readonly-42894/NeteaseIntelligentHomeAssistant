"""扫地机器人 select 平台：清扫模式。

复刻官方 App 的「模式选择」底部弹窗（``ModeControlDialog``，见
``sweeper/modules/widget/ModeControlDialog.java``）：每台扫地机生成一个 select
实体，选项为官方清扫模式——自动清扫、仿真拖地，Pro 款（RV03）再给「探索建图」、
非 Pro 款（RV02）给「沿边清扫」。选择即调用 ``setWorkMode(ctrltype, Start)`` 切换
模式（App 保存监听 ``HomeActivity.onCreate.9`` 同款动作）。

当前选项由 ``workMode`` 反推（``const.sweeper_clean_mode``，复刻 App 的
``HomeActivity.getCurrentModeControlType()``）。切换模式后设备需要数秒才回报新
``workMode``，因此选择后做**乐观更新**（立即把选项改为预期值并写回状态），同时
触发一次立即刷新，待设备数据确认或超时后回退到真实状态（见
:data:`ASSUMED_STATE_TTL`）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.select import SelectEntity
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
    SWEEPER_ACTION_START,
    SWEEPER_CLEAN_MODE_TO_CTRLTYPE,
    sweeper_clean_mode,
    sweeper_clean_modes,
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
    """Set up 网易智造扫地机器人清扫模式实体。"""
    data: NeteaseIntelligentData = hass.data[DOMAIN][entry.entry_id]
    entities: list[NeteaseIntelligentCleanModeSelect] = []
    for equip in data.coordinator.sweeper_equips():
        coordinator = data.sweeper_coordinators.get(equip.id)
        if coordinator is None:
            continue
        entities.append(
            NeteaseIntelligentCleanModeSelect(data.client, equip, coordinator)
        )
    async_add_entities(entities)


class NeteaseIntelligentCleanModeSelect(SelectEntity):
    """网易智造扫地机器人清扫模式实体。"""

    _attr_has_entity_name = True
    _attr_translation_key = "clean_mode"
    _attr_icon = "mdi:robot-vacuum-variant"

    def __init__(
        self,
        client: NeteaseIntelligentApiClient,
        equip: Equip,
        coordinator: NeteaseIntelligentSweeperCoordinator,
    ) -> None:
        self._client = client
        self._equip = equip
        self._coordinator = coordinator

        self._attr_unique_id = f"{equip.unique_identifier}_clean_mode"
        # 可选模式由机型决定（Pro 款用「探索建图」，非 Pro 用「沿边清扫」）。
        self._attr_options = list(sweeper_clean_modes(equip.product_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, equip.unique_identifier)},
            manufacturer=MANUFACTURER,
            model=equip.sweeper_model,
            name=equip.alias or equip.name or NAME,
            suggested_area=equip.room_name or None,
        )

        # 乐观更新状态（选择后立即生效，待设备数据确认或超时后清除）。
        self._assumed_option: str | None = None
        self._assumed_option_until: datetime | None = None
        self._option_before_assumed: str | None = None

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
    def _option_from(data: SweeperDeviceData) -> str | None:
        """把一次扫地机数据映射为清扫模式标签。"""
        return sweeper_clean_mode(data.work_mode)

    @property
    def current_option(self) -> str | None:
        """当前清扫模式；存在乐观状态时优先返回预期值。"""
        if self._assumed_option is not None:
            return self._assumed_option
        data = self._data
        if data is None:
            return None
        return self._option_from(data)

    def _assume_option(self, option: str) -> None:
        """记录乐观状态；选择前的实际值用于后续判定「设备是否已回报新状态」。"""
        data = self._data
        self._option_before_assumed = (
            self._option_from(data) if data is not None else None
        )
        self._assumed_option = option
        self._assumed_option_until = dt_util.utcnow() + ASSUMED_STATE_TTL

    @callback
    def _handle_coordinator_update(self) -> None:
        """协调器更新：清除已被设备确认（或已超时）的乐观状态后写回实体。"""
        self._resolve_assumed_state()
        self.async_write_ha_state()

    def _resolve_assumed_state(self) -> None:
        """乐观状态在设备回报新值（与选择前不同）或超过有效期后清除。"""
        if self._assumed_option is None:
            return
        now = dt_util.utcnow()
        data = self._data
        changed = (
            data is not None
            and self._option_from(data) != self._option_before_assumed
        )
        expired = (
            self._assumed_option_until is not None
            and now >= self._assumed_option_until
        )
        if changed or expired:
            self._assumed_option = None
            self._assumed_option_until = None
            self._option_before_assumed = None

    async def async_select_option(self, option: str, **kwargs: object) -> None:
        """切换到指定清扫模式（``setWorkMode(ctrltype, Start)``，同官方保存监听）。"""
        ctrltype = SWEEPER_CLEAN_MODE_TO_CTRLTYPE.get(option)
        if ctrltype is None:
            return
        await self._client.set_work_mode(self._equip.id, ctrltype, SWEEPER_ACTION_START)
        self._assume_option(option)
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """订阅数据刷新，实体随协调器更新（并解析乐观状态）。"""
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )