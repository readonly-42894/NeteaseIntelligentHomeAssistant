"""家庭数据协调器与扫地机数据协调器。

- ``NeteaseIntelligentCoordinator`` 周期调用 ``GET /ai-app/family/info`` 拉取家庭列表
  （每项含房间、成员与设备），按家庭 ID 建索引后作为 ``data`` 暴露。
- ``NeteaseIntelligentSweeperCoordinator`` 缓存单台扫地机的实时数据：**以 ``getDeviceData``
  轮询为基础、官方推送通道实时增补**（推送帧经
  :meth:`NeteaseIntelligentSweeperCoordinator.apply_sweeper_push` 注入），
  轮询提供推送不覆盖的字段与首次全量基线——推送在线时降频至 ``SWEEPER_PUSH_FALLBACK_INTERVAL``，
  离线时活动状态用短间隔、空闲用长间隔；控制指令后另有强制短轮询的观察窗口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, NeteaseIntelligentApiClient
from .const import (
    DOMAIN,
    SWEEPER_COMMAND_ACTIVE_WINDOW,
    SWEEPER_PUSH_FALLBACK_INTERVAL,
    SWEEPER_UPDATE_INTERVAL_ACTIVE,
    SWEEPER_UPDATE_INTERVAL_IDLE,
    UPDATE_INTERVAL,
    sweeper_is_active,
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

    - 推送在线（:meth:`set_push_connected`）时用 ``SWEEPER_PUSH_FALLBACK_INTERVAL``
      低频轮询，仅防推送静默丢失；数据主体来自 :meth:`apply_sweeper_push`。
    - 推送离线时自适应轮询：活动状态（清扫中/回充中）用
      ``SWEEPER_UPDATE_INTERVAL_ACTIVE``，空闲/充电完成用
      ``SWEEPER_UPDATE_INTERVAL_IDLE``。
    - 控制指令下发后经 :meth:`note_control_command` 开启观察窗口，其间强制短间隔。
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
        # 推送通道是否在线；在线时轮询降频（推送负责时效）。
        self._push_connected = False

    def _push_command_window(self) -> bool:
        """是否处于控制指令后的强制短轮询观察窗口内。"""
        return (
            self._fast_poll_until is not None
            and dt_util.utcnow() < self._fast_poll_until
        )

    def note_control_command(self) -> None:
        """控制指令下发后开启观察窗口，尽快反映设备新状态。

        立即切到短轮询间隔并记录截止时间；即使随后的拉取仍是旧数据（设备尚未
        回报），:meth:`_async_update_data` 也会在该窗口内维持短间隔。
        """
        self._fast_poll_until = dt_util.utcnow() + SWEEPER_COMMAND_ACTIVE_WINDOW
        self.update_interval = SWEEPER_UPDATE_INTERVAL_ACTIVE

    @callback
    def set_push_connected(self, connected: bool) -> None:
        """同步推送通道在线状态，并据此切换轮询频率。

        推送上线且不在控制观察窗口内时，把轮询降为
        ``SWEEPER_PUSH_FALLBACK_INTERVAL`` 并立即重排下一轮；推送下线时恢复
        自适应轮询（下一轮 :meth:`_async_update_data` 生效）。
        """
        self._push_connected = connected
        if connected and not self._push_command_window() and self.data is not None:
            self.update_interval = SWEEPER_PUSH_FALLBACK_INTERVAL
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
        """拉取单台扫地机的实时数据，并据状态调整下一轮轮询间隔。

        间隔优先级：控制观察窗口 > 推送在线（降频）> 活动状态 > 空闲。
        """
        try:
            data = await self.client.get_sweeper_data(self.equip_id)
        except ApiError as err:
            raise UpdateFailed(str(err)) from err

        in_command_window = self._push_command_window()
        if not in_command_window:
            self._fast_poll_until = None
        if in_command_window:
            self.update_interval = SWEEPER_UPDATE_INTERVAL_ACTIVE
        elif self._push_connected:
            self.update_interval = SWEEPER_PUSH_FALLBACK_INTERVAL
        elif sweeper_is_active(data.work_mode, data.fault_type, data.charge_status):
            self.update_interval = SWEEPER_UPDATE_INTERVAL_ACTIVE
        else:
            self.update_interval = SWEEPER_UPDATE_INTERVAL_IDLE
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
