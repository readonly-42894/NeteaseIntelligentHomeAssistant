"""家庭数据协调器。

周期调用 ``GET /ai-app/family/info`` 拉取家庭列表（每项含房间、成员与设备），
按家庭 ID 建索引后作为 ``DataUpdateCoordinator.data`` 暴露，供各平台实体消费。
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, NeteaseIntelligentApiClient
from .const import DOMAIN, UPDATE_INTERVAL
from .models import Family

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
