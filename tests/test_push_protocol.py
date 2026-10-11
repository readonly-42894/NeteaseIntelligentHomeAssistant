"""推送帧解析与数据合并（``push_protocol``）单元测试。

协议帧为官方 App 的 Socket.IO 推送（事件名 ``p``，``subtype`` 1=设备状态、
2=地图、3=轨迹；帧结构与字段见 ``docs/api/集成实现.md``「官方推送通道」小节）。
"""

from __future__ import annotations

import json

import netease_intelligent.models as m
import netease_intelligent.push_protocol as p


def _frame(
    subtype: int, payload: dict, product_id: int = 26, equip_id: str = "EQ1"
) -> str:
    """按官方帧结构拼一条 ``42["p", {...}]`` 文本帧。"""
    body = {
        "eventType": 1,
        "subtype": subtype,
        "type": product_id,
        "payload": {"productId": product_id, "equipId": equip_id, **payload},
    }
    message = {
        "android": {
            "payload": {
                "msgType": "msg_operate",
                "data": {"opType": 10, "json": body},
            }
        }
    }
    return "42" + json.dumps(["p", message])


def test_decode_status_frame() -> None:
    """设备状态帧 → (equip_id, subtype=1, payload)。"""
    decoded = p.decode_push_frame(
        _frame(1, {"workMode": 5, "battery": 177, "faultType": 3, "faultCode": 2104})
    )
    assert decoded is not None
    equip_id, subtype, payload = decoded
    assert equip_id == "EQ1"
    assert subtype == p.SUBTYPE_STATUS
    assert payload["workMode"] == 5


def test_decode_map_frame() -> None:
    """地图帧 → subtype=2。"""
    decoded = p.decode_push_frame(
        _frame(2, {"mapId": 0, "mapUrl": "https://x/y", "mapType": 1})
    )
    assert decoded is not None
    assert decoded[1] == p.SUBTYPE_MAP


def test_decode_history_frame() -> None:
    """轨迹帧 → subtype=3。"""
    decoded = p.decode_push_frame(_frame(3, {"position": [0, 749, 0]}))
    assert decoded is not None
    assert decoded[1] == p.SUBTYPE_HISTORY


def test_decode_rejects_non_push() -> None:
    """非 \"p\" 事件 / 畸形帧返回 None。"""
    assert p.decode_push_frame("") is None
    assert p.decode_push_frame("40") is None
    assert p.decode_push_frame('42["other",{}]') is None
    assert p.decode_push_frame("42 not json") is None
    assert p.decode_push_frame('42["p",{}]') is None
    assert p.decode_push_frame('42["p",{"android":{}}]') is None


def test_status_patch_work_mode_to_str() -> None:
    """subtype 1：workMode 整数转字符串，未知键丢弃。"""
    patch = p.sweeper_patch_from_push(
        1, {"workMode": 5, "battery": 177, "faultCode": 2104, "junk": 1}
    )
    assert patch["work_mode"] == "5"
    assert patch["battery"] == 177
    assert patch["fault_code"] == 2104
    assert "junk" not in patch


def test_map_patch() -> None:
    """subtype 2：mapId/mapUrl/mapType → snake_case。"""
    patch = p.sweeper_patch_from_push(
        2, {"mapId": 3, "mapUrl": "https://u", "mapType": 1}
    )
    assert patch == {"map_id": 3, "map_url": "https://u", "map_type": 1}


def test_map_patch_ignores_non_normal_mask() -> None:
    """subtype 2：Zone/Spot/Memory 或空 mapUrl 的帧被忽略（复刻 flowMapPush）。"""
    assert p.sweeper_patch_from_push(
        2, {"mapUrl": "u", "mapType": p.MAP_MASK_ZONE}
    ) == {}
    assert p.sweeper_patch_from_push(
        2, {"mapUrl": "u", "mapType": p.MAP_MASK_SPOT}
    ) == {}
    assert p.sweeper_patch_from_push(
        2, {"mapUrl": "u", "mapType": p.MAP_MASK_MEMORY}
    ) == {}
    assert p.sweeper_patch_from_push(2, {"mapUrl": "", "mapType": p.MAP_MASK_NORMAL}) == {}
    # Normal / History 帧照常透传。
    assert p.sweeper_patch_from_push(
        2, {"mapUrl": "u", "mapType": p.MAP_MASK_HISTORY}
    ) == {"map_url": "u", "map_type": p.MAP_MASK_HISTORY}


def test_history_patch_position() -> None:
    """subtype 3（轨迹）：position → map_history 元组；空/非法则空补丁。"""
    assert p.sweeper_patch_from_push(3, {"position": [1, 2, 3]}) == {
        "map_history": (1, 2, 3)
    }
    assert p.sweeper_patch_from_push(3, {"position": []}) == {}
    assert p.sweeper_patch_from_push(3, {}) == {}
    assert p.sweeper_patch_from_push(3, {"position": ["x"]}) == {}


def test_merge_preserves_unpatched_fields() -> None:
    """合并补丁保留未推送字段，未知键被过滤。"""
    data = m.SweeperDeviceData(
        work_mode="0", battery=150, today_clean_size=12, map_url="old"
    )
    merged = p.merge_sweeper_patch(
        data, {"battery": 140, "map_url": "new", "unknown": 9}
    )
    assert merged.battery == 140
    assert merged.map_url == "new"
    assert merged.work_mode == "0"
    assert merged.today_clean_size == 12


def test_make_push_id() -> None:
    """pushId 长度与字符集符合官方随机生成器，且不重复。"""
    push_id = p.make_push_id()
    assert len(push_id) == p.PUSH_ID_LENGTH == 26
    assert set(push_id) <= set(p.PUSH_ID_ALPHABET)
    assert p.make_push_id() != push_id