"""官方 Socket.IO 推送通道的帧解析与数据合并（纯 Python，不依赖 homeassistant）。

协议细节来自反编译 ``com/yy/httpproxy/socketio/SocketIOProxyClient.java`` 与官方
App 的实抓 WebSocket HAR（见 ``docs/api/集成实现.md``「官方推送通道」小节、以及
``scripts/push_probe.py``）。推送帧为 Socket.IO 文本帧，事件名 ``p``：

.. code-block:: text

    42["p", {"android": {"payload": {"msgType": "msg_operate",
        "data": {"opType": 10, "json": {"eventType": 1,
            "subtype": 1|2|3, "type": <productId>, "payload": {...}}}}}}]

``subtype``：1=设备状态（字段与 ``getDeviceData`` 一致）、2=地图、3=轨迹。
"""

from __future__ import annotations

import json
import secrets
from dataclasses import replace
from typing import Any

from .models import SweeperDeviceData

# 与官方 ``RandomPushIdGenerator``（``new BigInteger(130, SecureRandom).toString(32)``）
# 的字符集与长度一致。
PUSH_ID_ALPHABET: str = "0123456789abcdefghijklmnopqrstuv"
PUSH_ID_LENGTH: int = 26

# 扫地机推送的子类型（``SweeperPushSubType``）。
SUBTYPE_STATUS: int = 1
SUBTYPE_MAP: int = 2
SUBTYPE_HISTORY: int = 3
SUBTYPE_PENDING_MAP: int = 4

# 地图掩码（``MapMask``）。官方 ``flowMapPush`` 只让 Normal/History 帧更新实时
# 地图，过滤掉 Zone/Spot/Memory 帧（后者属于定点/区域/记忆地图流程）。
MAP_MASK_NORMAL: int = 1
MAP_MASK_ZONE: int = 2
MAP_MASK_SPOT: int = 3
MAP_MASK_HISTORY: int = 4
MAP_MASK_MEMORY: int = 5
_IGNORED_MAP_MASKS: frozenset[int] = frozenset(
    {MAP_MASK_ZONE, MAP_MASK_SPOT, MAP_MASK_MEMORY}
)

# subtype 1（设备状态）→ ``SweeperDeviceData`` 字段名（camelCase → snake_case）。
# 注意：这是 http ``getDeviceData`` 的**子集**——推送不含 ``todayCleanSize`` /
# ``todayCleanTime`` / ``isOnline`` / ``isOtaUpdating`` / ``isRoomCleaningStatus``
# 等字段，故这些字段只能靠轮询（见 docs/api/集成实现.md「为什么轮询不可省（即使推送可用）」）。
_STATUS_FIELDS: dict[str, str] = {
    "areaCleanFlag": "area_clean_flag",
    "battery": "battery",
    "chargeStatus": "charge_status",
    "cleanSchemeId": "clean_scheme_id",
    "cleanSize": "clean_size",
    "cleanTime": "clean_time",
    "faultCode": "fault_code",
    "faultType": "fault_type",
    "mapId": "map_id",
    "protocolVersion": "protocol_version",
    "repeatClean": "repeat_clean",
    "waterControl": "water_control",
    "windPower": "wind_power",
    "workMode": "work_mode",
}

# subtype 2（地图）→ ``SweeperDeviceData`` 字段名。
_MAP_FIELDS: dict[str, str] = {
    "mapId": "map_id",
    "mapUrl": "map_url",
    "mapType": "map_type",
}


def make_push_id() -> str:
    """生成本会话的推送标识（同官方随机生成器的字符集与长度）。"""
    return "".join(secrets.choice(PUSH_ID_ALPHABET) for _ in range(PUSH_ID_LENGTH))


def decode_push_frame(text: str) -> tuple[str, int, dict[str, Any]] | None:
    """解析一条 ``42["p", {...}]`` 推送帧。

    返回 ``(equip_id, subtype, payload)``；非扫地机推送或畸形帧返回 ``None``。
    ``subtype`` 取自 ``json.subtype``（1=设备状态、2=地图、3=轨迹、4=待确认地图），
    ``payload`` 为 ``json.payload``（内含 ``equipId``）。
    """
    if not text.startswith("42"):
        return None
    try:
        message = json.loads(text[2:])
    except ValueError:
        return None
    if not isinstance(message, list) or len(message) < 2 or message[0] != "p":
        return None

    push = message[1]
    if not isinstance(push, dict):
        return None
    android = push.get("android")
    if not isinstance(android, dict):
        return None
    envelope = android.get("payload")
    if not isinstance(envelope, dict):
        return None
    data = envelope.get("data")
    if not isinstance(data, dict):
        return None
    body = data.get("json")
    if not isinstance(body, dict):
        return None

    subtype = body.get("subtype")
    payload = body.get("payload")
    if not isinstance(subtype, int) or not isinstance(payload, dict):
        return None

    equip_id = payload.get("equipId") or body.get("equipId") or ""
    return str(equip_id), subtype, payload


def sweeper_patch_from_push(subtype: int, payload: dict[str, Any]) -> dict[str, Any]:
    """把一条推送载荷映射为 ``SweeperDeviceData`` 字段补丁。

    设备状态（subtype 1）里 ``workMode`` 为整数，而模型字段为字符串，这里统一转
    字符串；其余值原样传递。地图（subtype 2）补 ``map_id``/``map_url``/``map_type``，
    但 mapType ∈ {Zone, Spot, Memory} 或 mapUrl 为空的帧被忽略（复刻官方
    ``flowMapPush``）。轨迹（subtype 3）补 ``map_history``（``position`` 原始数组的
    元组），供 image 实体增量重放清扫轨迹；``position`` 为空则不产生补丁。
    """
    if subtype == SUBTYPE_STATUS:
        mapping = _STATUS_FIELDS
    elif subtype == SUBTYPE_MAP:
        if not payload.get("mapUrl") or payload.get("mapType") in _IGNORED_MAP_MASKS:
            return {}
        mapping = _MAP_FIELDS
    elif subtype == SUBTYPE_HISTORY:
        position = payload.get("position")
        if not isinstance(position, (list, tuple)) or not position:
            return {}
        try:
            return {"map_history": tuple(int(value) for value in position)}
        except (TypeError, ValueError):
            return {}
    else:
        return {}

    patch: dict[str, Any] = {}
    for source, target in mapping.items():
        if source not in payload:
            continue
        value = payload[source]
        if target == "work_mode" and isinstance(value, int):
            value = str(value)
        patch[target] = value
    return patch


def merge_sweeper_patch(
    data: SweeperDeviceData, patch: dict[str, Any]
) -> SweeperDeviceData:
    """把推送补丁合并进最近一次全量数据（保留未推送字段），返回新实例。"""
    return replace(
        data, **{key: value for key, value in patch.items() if hasattr(data, key)}
    )
