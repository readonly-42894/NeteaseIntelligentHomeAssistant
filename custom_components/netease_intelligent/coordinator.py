"""家庭数据协调器与扫地机数据协调器。

- ``NeteaseIntelligentCoordinator`` 周期调用 ``GET /ai-app/family/info`` 拉取家庭列表
  （每项含房间、成员与设备），按家庭 ID 建索引后作为 ``data`` 暴露。
- ``NeteaseIntelligentSweeperCoordinator`` 周期调用
  ``GET /ai-app/sweeper/rv02/getDeviceData`` 拉取单台扫地机的实时数据。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, NeteaseIntelligentApiClient
from .const import DOMAIN, UPDATE_INTERVAL
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
    """拉取并缓存单台扫地机的实时数据。"""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeteaseIntelligentApiClient,
        equip_id: str,
        *,
        update_interval: timedelta = UPDATE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_sweeper_{equip_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.equip_id = equip_id

    async def _async_update_data(self) -> SweeperDeviceData:
        """拉取单台扫地机的实时数据。"""
        try:
            return await self.client.get_sweeper_data(self.equip_id)
        except ApiError as err:
            raise UpdateFailed(str(err)) from err


@dataclass
class NeteaseIntelligentData:
    """集成在 ``hass.data[DOMAIN][entry_id]`` 中保存的运行时数据。"""

    client: NeteaseIntelligentApiClient
    coordinator: NeteaseIntelligentCoordinator
    sweeper_coordinators: dict[str, NeteaseIntelligentSweeperCoordinator] = field(
        default_factory=dict
    )
