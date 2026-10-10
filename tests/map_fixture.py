"""构造合成地图包的测试辅助（不依赖真实设备/隐私数据）。

按 ``map_parser`` 记录的二进制布局拼装一个 zlib 压缩地图包，供解析与渲染单测使用。
"""

from __future__ import annotations

import struct
import zlib


def _i(value: int) -> bytes:
    return struct.pack("<i", value)


def _s(value: int) -> bytes:
    return struct.pack("<h", value)


def _f(value: float) -> bytes:
    return struct.pack("<f", value)


def _b(value: int) -> bytes:
    return struct.pack("<B", value)


def _area(offset: bytes, items: list[tuple[int, list[tuple[float, float]]]]) -> bytes:
    """拼装墙/区域区（每项固定写满 10 个点）。"""
    out = bytearray(offset)
    out += _i(len(items))
    for item_id, points in items:
        out += _i(item_id) + _i(0) + _i(len(points))
        padded = list(points) + [(0.0, 0.0)] * (10 - len(points))
        for x, y in padded[:10]:
            out += _f(x) + _f(y)
    return bytes(out)


def _plan(rooms: list[tuple[int, str, float, float]]) -> bytes:
    """拼装协议 V2 的 MapInfo（空）+ MapRoom（给定房间）。"""
    out = bytearray()
    out += _i(0) + _s(0) + _b(0) + _b(0)  # MapInfo：itemCount = 0
    out += _i(0) + _i(len(rooms))  # MapRoom：planId、roomCount
    for room_id, name, middle_x, middle_y in rooms:
        encoded = name.encode("utf-8")
        out += _b(room_id) + _b(len(encoded)) + encoded
        out += _b(1)  # state
        out += _f(middle_x) + _f(middle_y)
    return bytes(out)


def build_map(
    *,
    grid: list[int],
    size_x: int,
    size_y: int,
    resolution: float = 1.0,
    min_x: float = 0.0,
    min_y: float = 0.0,
    status: tuple[int, ...] | None = None,
    history: list[tuple[int, float, float]] | None = None,
    charge: tuple[float, float, float] | None = None,
    wall: list[tuple[int, list[tuple[float, float]]]] | None = None,
    area: list[tuple[int, list[tuple[float, float]]]] | None = None,
    spot: tuple[int, float, float, float] | None = None,
    robot: tuple[int, float, float, float] | None = None,
    rooms: list[tuple[int, str, float, float]] | None = None,
    plan: bool | None = None,
) -> bytes:
    """把各分区按位标志与顺序拼装为 zlib 压缩的地图包。"""
    if plan is None:
        plan = rooms is not None

    byte0 = 0x02  # withMapData 恒置位
    byte1 = 0
    if status is not None:
        byte0 |= 0x01
    if history is not None:
        byte0 |= 0x04
    if charge is not None:
        byte0 |= 0x08
    if wall is not None:
        byte0 |= 0x10
    if area is not None:
        byte0 |= 0x20
    if spot is not None:
        byte0 |= 0x40
    if robot is not None:
        byte0 |= 0x80
    if plan:
        byte1 |= 0x08

    out = bytearray([byte0, byte1, 0, 0])
    if status is not None:
        values = (list(status) + [0] * 11)[:11]
        out += struct.pack("<11i", *values)
    max_x = min_x + size_x * resolution
    max_y = min_y + size_y * resolution
    out += _i(0) + _i(1) + _i(0)  # mapHeadId / mapValid / mapType
    out += _i(size_x) + _i(size_y)
    out += _f(min_x) + _f(min_y) + _f(max_x) + _f(max_y) + _f(resolution)
    out += bytes(grid)
    if history is not None:
        out += _i(0) + _i(0) + _i(len(history))
        for update, x, y in history:
            out += _b(update) + _f(x) + _f(y)
    if charge is not None:
        x, y, phi = charge
        out += _i(0) + _f(x) + _f(y) + _f(phi)
    if wall is not None:
        out += _area(_i(0) + _i(0), wall)
    if area is not None:
        out += _area(_i(0) + _i(0), area)
    if spot is not None:
        ctrl, x, y, phi = spot
        out += _i(0) + _i(ctrl) + _f(x) + _f(y) + _f(phi)
    if robot is not None:
        pose_id, x, y, phi = robot
        out += _i(0) + _i(pose_id) + _b(0) + _f(x) + _f(y) + _f(phi)
    if plan:
        out += _plan(rooms or [])
    return zlib.compress(bytes(out))
