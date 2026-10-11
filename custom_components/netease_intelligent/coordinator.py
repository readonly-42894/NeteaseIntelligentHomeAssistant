"""家庭数据协调器与扫地机数据协调器。

- ``NeteaseIntelligentCoordinator`` 周期调用 ``GET /ai-app/family/info`` 拉取家庭列表
  （每项含房间、成员与设备），按家庭 ID 建索引后作为 ``data`` 暴露。
- ``NeteaseIntelligentSweeperCoordinator`` 周期调用
  ``GET /ai-app/sweeper/rv02/getDeviceData`` 拉取单台扫地机的实时数据，并按设备
  活动状态自适应轮询（活动时短间隔、空闲时长间隔；控制指令后有观察窗口）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, NeteaseIntelligentApiClient
from .const import (
    DOMAIN,
    SWEEPER_COMMAND_ACTIVE_WINDOW,
    SWEEPER_UPDATE_INTERVAL_ACTIVE,
    SWEEPER_UPDATE_INTERVAL_IDLE,
    UPDATE_INTERVAL,
    sweeper_is_active,
)
from .models import Equip, Family, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)


class NeteaseIntelligentCoordinator(DataUpdateCoordinator[dict[int, Family]]):
    """拉取并缓存家庭数据，供各平台实体消费。"""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeteaseIntelligentApiClient,
        *,
        update_interval: timedelta = UPDATE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> dict[int, Family]:
        """拉取家庭列表并按家庭 ID 建索引。"""
        try:
            info = await self.client.get_family_info()
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
        return {family.id: family for family in info.family_list}

    def sweeper_equips(self) -> list[Equip]:
        """家庭数据中的扫地机器人，按 ``unique_identifier`` 去重。"""
        seen: set[str] = set()
        result: list[Equip] = []
        for family in (self.data or {}).values():
            for equip in family.equips:
                if not equip.is_sweeper:
                    continue
                identifier = equip.unique_identifier
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                result.append(equip)
        return result


class NeteaseIntelligentSweeperCoordinator(DataUpdateCoordinator[SweeperDeviceData]):
    """拉取并缓存单台扫地机的实时数据。

    采用自适应轮询：设备处于活动状态（清扫中/回充中）时用
    ``SWEEPER_UPDATE_INTERVAL_ACTIVE`` 短间隔，空闲/充电完成时回落到
    ``SWEEPER_UPDATE_INTERVAL_IDLE`` 长间隔；控制指令下发后经
    :meth:`note_control_command` 开启观察窗口，其间强制短间隔以尽快收敛。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeteaseIntelligentApiClient,
        equip_id: str,
        *,
        update_interval: timedelta = SWEEPER_UPDATE_INTERVAL_IDLE,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_sweeper_{equip_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.equip_id = equip_id
        # 控制指令观察窗口的截止时间；窗口内强制短轮询。
        self._fast_poll_until: datetime | None = None

    def note_control_command(self) -> None:
        """控制指令下发后开启观察窗口，尽快反映设备新状态。

        立即切到短轮询间隔并记录截止时间；即使随后的拉取仍是旧数据（设备尚未
        回报），:meth:`_async_update_data` 也会在该窗口内维持短间隔。
        """
        self._fast_poll_until = dt_util.utcnow() + SWEEPER_COMMAND_ACTIVE_WINDOW
        self.update_interval = SWEEPER_UPDATE_INTERVAL_ACTIVE

    async def _async_update_data(self) -> SweeperDeviceData:
        """拉取单台扫地机的实时数据，并据状态调整下一轮轮询间隔。"""
        try:
            data = await self.client.get_sweeper_data(self.equip_id)
        except ApiError as err:
            raise UpdateFailed(str(err)) from err

        in_command_window = (
            self._fast_poll_until is not None
            and dt_util.utcnow() < self._fast_poll_until
        )
        if not in_command_window:
            self._fast_poll_until = None
        self.update_interval = (
            SWEEPER_UPDATE_INTERVAL_ACTIVE
            if in_command_window
            or sweeper_is_active(data.work_mode, data.fault_type, data.charge_status)
            else SWEEPER_UPDATE_INTERVAL_IDLE
        )
        return data


@dataclass
class NeteaseIntelligentData:
    """集成在 ``hass.data[DOMAIN][entry_id]`` 中保存的运行时数据。"""

    client: NeteaseIntelligentApiClient
    coordinator: NeteaseIntelligentCoordinator
    sweeper_coordinators: dict[str, NeteaseIntelligentSweeperCoordinator] = field(
        default_factory=dict
    )
