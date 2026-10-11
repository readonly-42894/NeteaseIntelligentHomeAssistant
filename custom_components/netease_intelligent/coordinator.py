"""家庭数据协调器与扫地机数据协调器。

- ``NeteaseIntelligentCoordinator`` 周期调用 ``GET /ai-app/family/info`` 拉取家庭列表
  （每项含房间、成员与设备），按家庭 ID 建索引后作为 ``data`` 暴露。
- ``NeteaseIntelligentSweeperCoordinator`` 缓存单台扫地机的实时数据：**轮询为基础数据源、
  官方推送通道实时增补**（推送帧经
  :meth:`NeteaseIntelligentSweeperCoordinator.apply_sweeper_push` 注入）。轮询提供推送不
  覆盖的字段与首次全量基线，频率固定不随状态变化——推送在线时降至
  ``SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE``，否则用 ``UPDATE_INTERVAL``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, NeteaseIntelligentApiClient
from .const import (
    DOMAIN,
    SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE,
    UPDATE_INTERVAL,
)
from .models import Equip, Family, SweeperDeviceData
from .push_protocol import merge_sweeper_patch

if TYPE_CHECKING:
    from .push import NeteaseIntelligentPushClient

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
    """缓存单台扫地机的实时数据（轮询为基础、推送实时增补）。

    - 轮询频率**固定，不随设备状态或控制指令变化**：推送在线
      （:meth:`set_push_connected`）时用 ``SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE`` 低频，
      否则用 ``UPDATE_INTERVAL``。状态时效由推送（:meth:`apply_sweeper_push`）承担，
      轮询只保证完整性与基线——从不给轮询提速，以免打爆设备/云。
    """

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
        # 推送通道是否在线；在线时轮询降频（推送负责时效）。
        self._push_connected = False

    @callback
    def set_push_connected(self, connected: bool) -> None:
        """同步推送通道在线状态，并据此切换轮询频率。

        推送上线时把轮询降到 ``SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE`` 并立即重排；推送
        下线时恢复 ``UPDATE_INTERVAL``（下一轮 :meth:`_async_update_data` 生效）。
        """
        self._push_connected = connected
        if self.data is not None:
            self.update_interval = (
                SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE if connected else UPDATE_INTERVAL
            )
            self.async_set_updated_data(self.data)

    @callback
    def apply_sweeper_push(self, patch: dict[str, Any]) -> None:
        """把一条推送补丁合并进缓存数据并通知实体。

        ``patch`` 由 :func:`push_protocol.sweeper_patch_from_push` 生成，仅含推送
        携带的字段；未推送字段保留最近一次全量拉取的值。
        """
        if self.data is None:
            # 尚无基准数据：等下一轮轮询或首个推送后再合并，避免丢字段。
            return
        self.async_set_updated_data(merge_sweeper_patch(self.data, patch))

    async def _async_update_data(self) -> SweeperDeviceData:
        """拉取单台扫地机的全量数据（推送不覆盖字段的唯一来源）。

        轮询频率固定：推送在线时 ``SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE``，否则
        ``UPDATE_INTERVAL``；不随设备状态或控制指令提速。
        """
        try:
            data = await self.client.get_sweeper_data(self.equip_id)
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
        self.update_interval = (
            SWEEPER_UPDATE_INTERVAL_PUSH_ONLINE
            if self._push_connected
            else UPDATE_INTERVAL
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
    # 推送通道客户端；None 表示未启用（如账号信息获取失败时退回纯轮询）。
    push_client: NeteaseIntelligentPushClient | None = None
