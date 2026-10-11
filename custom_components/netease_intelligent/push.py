"""官方 Socket.IO 推送通道客户端（实时增强数据源）。

官方 App 通过 ``com.yy.httpproxy`` 的 Socket.IO 长连接（Engine.IO v3，仅 WebSocket）
接收设备事件。本模块用 aiohttp 直接复刻该通道：连接 → 注册 ``pushId``/``setTags``/
``bindUid`` → 对每台扫地机发送 ``event/view``（开始推送）→ 监听 ``p`` 事件并把
载荷分发到对应协调器。

协议细节（握手序列、心跳、帧结构、event/view 语义）来自反编译
``SocketIOProxyClient.java``/``EventUtil.java`` 与官方 App 实抓 WebSocket HAR，见
``push_protocol.py`` 与 ``docs/api/集成实现.md``「官方推送通道」小节；离线验证工具为
``scripts/push_probe.py``。

与本集成其他模块的关系：本模块不导入 ``coordinator``（避免循环导入），仅按鸭子类型
调用协调器的 ``apply_sweeper_push`` / ``set_push_connected``。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, NeteaseIntelligentApiClient
from .const import (
    PUSH_APP_NAME,
    PUSH_APP_SOURCE,
    PUSH_APP_VERSION,
    PUSH_ENV,
    PUSH_EVENT_ENTRY_PAGE,
    PUSH_EVENT_EXIT_PAGE,
    PUSH_HOST,
    PUSH_PING_INTERVAL,
    PUSH_PLATFORM,
    PUSH_RECONNECT_MAX,
    PUSH_RECONNECT_MIN,
    PUSH_TOPICS,
    push_uid,
)
from .push_protocol import decode_push_frame, make_push_id, sweeper_patch_from_push

if TYPE_CHECKING:
    from .coordinator import NeteaseIntelligentSweeperCoordinator

_LOGGER = logging.getLogger(__name__)

# Engine.IO v3：``?EIO=3&transport=websocket``；该部署由客户端主动 ping。
_PUSH_QUERY = "?EIO=3&transport=websocket"
_ENGINEIO_OPEN = "0"
_ENGINEIO_PING = "2"
_SOCKETIO_CONNECT = "40"
_SOCKETIO_EVENT = "42"

# 关闭 WebSocket 时的等待上限（秒）。
_WS_CLOSE_TIMEOUT = 30.0


class NeteaseIntelligentPushClient:
    """维护官方推送通道连接，并把扫地机推送分发到协调器。

    ``sweeper_coordinators`` 为 ``{equip_id: NeteaseIntelligentSweeperCoordinator}``；
    ``equip_products`` 为 ``{equip_id: productId}``，用于 ``event/view`` 订阅。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeteaseIntelligentApiClient,
        pid: int,
        sweeper_coordinators: dict[str, "NeteaseIntelligentSweeperCoordinator"],
        equip_products: dict[str, int],
    ) -> None:
        self._hass = hass
        self._client = client
        self._uid = push_uid(pid)
        self._sweeper_coordinators = sweeper_coordinators
        self._equip_products = equip_products
        self._push_id = make_push_id()
        self._tags = [
            PUSH_APP_VERSION,
            f"{PUSH_ENV}_{PUSH_APP_NAME}",
            f"{PUSH_ENV}_{PUSH_APP_NAME}_{PUSH_PLATFORM}",
            PUSH_APP_SOURCE,
        ]
        self._connected = False
        self._registered = False
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    @property
    def push_id(self) -> str:
        """本会话的推送标识（``event/view`` 与 ``pushId`` 注册共用）。"""
        return self._push_id

    async def async_start(self) -> None:
        """启动推送通道（后台任务，断线自动重连）。"""
        self._stopping = False
        self._task = self._hass.async_create_background_task(
            self._run(), "netease_intelligent_push"
        )

    async def async_stop(self) -> None:
        """关闭推送通道：停止连接、发送关闭推送事件（``event/view``=2）。"""
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._send_events(PUSH_EVENT_EXIT_PAGE)
        self._set_connected(False)

    async def _run(self) -> None:
        """连接主循环；异常后退避重连直至被取消。"""
        delay = PUSH_RECONNECT_MIN
        while not self._stopping:
            try:
                await self._connect_and_listen()
                delay = PUSH_RECONNECT_MIN
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001  # 任何异常都退避重连
                _LOGGER.debug("推送通道中断，%.0fs 后重连：%s", delay, err)
                self._set_connected(False)
            if self._stopping:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, PUSH_RECONNECT_MAX)

    async def _connect_and_listen(self) -> None:
        """建立一次 WebSocket 连接并处理帧，直到断开。"""
        session = async_get_clientsession(self._hass)
        ws = await session.ws_connect(
            PUSH_HOST + _PUSH_QUERY,
            heartbeat=None,
            timeout=aiohttp.ClientWSTimeout(ws_close=_WS_CLOSE_TIMEOUT),
        )
        self._registered = False
        heartbeat = asyncio.create_task(self._heartbeat(ws))
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_frame(ws, msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            heartbeat.cancel()
            await ws.close()
            self._set_connected(False)

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """每 ``PUSH_PING_INTERVAL`` 秒发送一次 Engine.IO ping（客户端主动心跳）。"""
        while True:
            await asyncio.sleep(PUSH_PING_INTERVAL)
            await ws.send_str(_ENGINEIO_PING)

    def _set_connected(self, connected: bool) -> None:
        """同步推送在线状态给所有扫地机协调器（决定轮询频率）。"""
        if connected == self._connected:
            return
        self._connected = connected
        for coordinator in self._sweeper_coordinators.values():
            coordinator.set_push_connected(connected)

    async def _handle_frame(
        self, ws: aiohttp.ClientWebSocketResponse, text: str
    ) -> None:
        """处理一条 Engine.IO/Socket.IO 文本帧。"""
        if text.startswith(_ENGINEIO_OPEN):
            await ws.send_str(_SOCKETIO_CONNECT)
        elif text.startswith(_SOCKETIO_CONNECT):
            if not self._registered:
                await self._register(ws)
        elif text.startswith(_SOCKETIO_EVENT):
            self._handle_event(text)

    async def _register(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """完成 Socket.IO 注册：pushId → setTags → unbindUid → bindUid。"""
        await self._send_json(
            ws,
            "pushId",
            {
                "id": self._push_id,
                "platform": PUSH_PLATFORM,
                "topics": list(PUSH_TOPICS),
                "lastPacketIds": {"noti": "0"},
                "tags": self._tags,
            },
        )
        await self._send_json(ws, "setTags", self._tags)
        await ws.send_str('42["unbindUid"]')
        await self._send_json(ws, "bindUid", {"uid": self._uid})
        self._registered = True
        self._set_connected(True)
        await self._send_events(PUSH_EVENT_ENTRY_PAGE)

    async def _send_json(
        self, ws: aiohttp.ClientWebSocketResponse, event: str, payload: Any
    ) -> None:
        """发送一条 Socket.IO 事件帧 ``42["event", payload]``。"""
        body = json.dumps([event, payload], separators=(",", ":"), ensure_ascii=False)
        await ws.send_str(_SOCKETIO_EVENT + body)

    async def _send_events(self, event_type: int) -> None:
        """对每台扫地机发送 ``event/view``（开始=1 / 关闭=2）。"""
        for equip_id, product_id in self._equip_products.items():
            try:
                await self._client.send_page_event(
                    self._push_id, product_id, event_type, equip_id
                )
            except ApiError as err:
                _LOGGER.debug(
                    "推送 event/view(eventType=%s) 设备 %s 失败：%s",
                    event_type,
                    equip_id,
                    err,
                )

    def _handle_event(self, text: str) -> None:
        """解析 ``p`` 事件并分发到对应扫地机协调器。"""
        decoded = decode_push_frame(text)
        if decoded is None:
            return
        equip_id, subtype, payload = decoded
        coordinator = self._sweeper_coordinators.get(equip_id)
        if coordinator is None:
            return
        coordinator.apply_sweeper_push(sweeper_patch_from_push(subtype, payload))
