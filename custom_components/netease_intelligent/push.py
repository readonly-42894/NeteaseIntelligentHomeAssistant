"""官方 Socket.IO 推送通道客户端（实时增强数据源）。

官方 App 通过 ``com.yy.httpproxy`` 的 Socket.IO 长连接（Engine.IO v3，仅 WebSocket）
接收设备事件与通知。本模块用 aiohttp 直接复刻该通道：连接 → 注册 ``pushId``/
``setTags``/``bindUid`` → 对每台扫地机发送 ``event/view``（开始推送）→ 监听 ``p``
事件并把载荷分发到对应协调器；同时监听 ``noti``/``n`` 事件，回执后把通知交给
``set_notification_callback`` 注册的回调（见 ``_handle_notification``）。

协议细节（握手序列、心跳、帧结构、event/view 语义、通知回执）来自反编译
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
from typing import TYPE_CHECKING, Any, Callable

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

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
from .push_protocol import (
    OPTYPE_EVENT,
    NotificationPacket,
    decode_notification_frame,
    decode_push_frame,
    make_push_id,
    sweeper_patch_from_push,
)

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

# ``lastNotiId`` 的持久化（每个 config entry 一份），使重启后注册回传已收位置，
# 避免服务端按 TTL 重放旧通知（协议见 docs/api/集成实现.md「通知（noti 主题）」）。
_STORAGE_VERSION = 1
_STORAGE_KEY = "netease_intelligent.push"
_STORAGE_LAST_NOTI_ID = "last_noti_id"


class NeteaseIntelligentPushClient:
    """维护官方推送通道连接，并把扫地机推送分发到协调器。

    ``sweeper_coordinators`` 为 ``{equip_id: NeteaseIntelligentSweeperCoordinator}``；
    ``equip_products`` 为 ``{equip_id: productId}``，用于 ``event/view`` 订阅（可为空：
    即使无扫地机，通知（``noti``）订阅仍照常工作）。

    通知通过 ``set_notification_callback`` 注册的回调抛出（见 ``_handle_notification``）。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeteaseIntelligentApiClient,
        pid: int,
        entry_id: str,
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
        # 通知（noti 主题）：回调、去重集合、已回执位置（持久化）。
        self._notification_callback: Callable[[NotificationPacket], None] | None = None
        self._seen_noti_ids: set[str] = set()
        self._last_noti_id = "0"
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{_STORAGE_KEY}.{entry_id}"
        )

    @property
    def push_id(self) -> str:
        """本会话的推送标识（``event/view`` 与 ``pushId`` 注册共用）。"""
        return self._push_id

    def set_notification_callback(
        self, callback: Callable[[NotificationPacket], None]
    ) -> None:
        """注册通知回调（收到可展示的 ``noti`` 通知时调用）。"""
        self._notification_callback = callback

    async def async_start(self) -> None:
        """启动推送通道（后台任务，断线自动重连）。"""
        await self._async_load_state()
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

    async def _async_load_state(self) -> None:
        """从存储恢复 ``lastNotiId``（重启后于 ``pushId`` 注册回传）。"""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            last = stored.get(_STORAGE_LAST_NOTI_ID)
            if isinstance(last, str) and last:
                self._last_noti_id = last

    def _persist_noti_id(self) -> None:
        """延迟保存 ``lastNotiId``（避免每条通知都立即落盘）。"""
        self._store.async_delay_save(
            lambda: {_STORAGE_LAST_NOTI_ID: self._last_noti_id}, 5
        )

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
            await self._handle_event(ws, text)

    async def _register(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """完成 Socket.IO 注册：pushId → setTags → unbindUid → bindUid。

        ``pushId`` 的 ``lastPacketIds.noti`` 回传已回执位置（官方 ``lastNotiId``，
        默认 ``"0"``），服务端据此不再重放更早的通知。
        """
        await self._send_json(
            ws,
            "pushId",
            {
                "id": self._push_id,
                "platform": PUSH_PLATFORM,
                "topics": list(PUSH_TOPICS),
                "lastPacketIds": {"noti": self._last_noti_id},
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

    async def _handle_event(
        self, ws: aiohttp.ClientWebSocketResponse, text: str
    ) -> None:
        """按事件名路由 ``42`` 帧：通知（``noti``/``n``）与设备事件（``p``）。"""
        packet = decode_notification_frame(text)
        if packet is not None:
            await self._handle_notification(ws, packet)
            return
        self._handle_push(text)

    async def _handle_notification(
        self, ws: aiohttp.ClientWebSocketResponse, packet: NotificationPacket
    ) -> None:
        """处理一条 ``noti`` 通知：回执、记录位置、去重、按需抛给上层。

        回执（官方 ``notificationReply {id,timestamp}``）无论是否展示都必须发，
        否则服务端会按 TTL 重发；``id`` 去重防止重连重放导致重复抛事件；官方对
        ``android.title`` 为空与设备事件（opType==10）不展示，这里同样不抛。
        """
        if packet.timestamp > 0:
            await self._send_json(
                ws,
                "notificationReply",
                {"id": packet.id, "timestamp": packet.timestamp},
            )
        # 官方 updateLastPacketId：仅「带 ttl 且非 unicast」的通知才记 lastNotiId。
        if packet.ttl is not None and packet.unicast is None:
            self._last_noti_id = packet.id
            self._persist_noti_id()

        if packet.id in self._seen_noti_ids:
            _LOGGER.debug("通知 %s 重复，忽略", packet.id)
            return
        self._seen_noti_ids.add(packet.id)
        if len(self._seen_noti_ids) > 1024:
            # 通知为低频事件；仅在极端情况下清空，避免集合无限增长。
            self._seen_noti_ids.clear()
        if not packet.title:
            _LOGGER.debug("通知 %s 无标题，忽略", packet.id)
            return
        if packet.op_type == OPTYPE_EVENT:
            _LOGGER.debug("通知 %s 为设备事件(opType=10)，忽略", packet.id)
            return
        _LOGGER.debug(
            "收到通知 %s opType=%s viewType=%s title=%s",
            packet.id,
            packet.op_type,
            packet.view_type,
            packet.title,
        )
        if self._notification_callback is not None:
            self._notification_callback(packet)

    def _handle_push(self, text: str) -> None:
        """解析 ``p`` 事件并分发到对应扫地机协调器。"""
        decoded = decode_push_frame(text)
        if decoded is None:
            return
        equip_id, subtype, payload = decoded
        coordinator = self._sweeper_coordinators.get(equip_id)
        if coordinator is None:
            _LOGGER.debug("推送 subtype=%s 设备 %s 无对应协调器，忽略", subtype, equip_id)
            return
        patch = sweeper_patch_from_push(subtype, payload)
        _LOGGER.debug(
            "推送 subtype=%s 设备 %s 补丁字段=%s",
            subtype,
            equip_id,
            sorted(patch),
        )
        if subtype == 2:
            _LOGGER.debug(
                "推送地图 设备 %s map_id=%s map_type=%s map_url=%s",
                equip_id,
                payload.get("mapId"),
                payload.get("mapType"),
                payload.get("mapUrl"),
            )
        if subtype == 3:
            position = payload.get("position")
            sample = list(position[:12]) if isinstance(position, (list, tuple)) else position
            _LOGGER.debug(
                "推送轨迹 设备 %s position 长度=%s 前几个=%s",
                equip_id,
                len(position) if isinstance(position, (list, tuple)) else None,
                sample,
            )
        coordinator.apply_sweeper_push(patch)
