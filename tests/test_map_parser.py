"""扫地机二进制地图包解析（``map_parser.py``）单元测试。

使用 ``tests/map_fixture.py`` 合成的地图包，覆盖头部位标志、各分区字段、
坐标变换与容错；不依赖真实设备数据与 Home Assistant。
"""

from __future__ import annotations

import zlib

import pytest

import netease_intelligent.map_parser as mp
from map_fixture import build_map


def _grid(values: dict[tuple[int, int], int], size_x: int, size_y: int) -> list[int]:
    grid = [0] * (size_x * size_y)
    for (x, y), value in values.items():
        grid[y * size_x + x] = value
    return grid


def test_header_flags() -> None:
    """头部位标志按存在分区正确置位。"""
    raw = build_map(
        grid=[0] * 16,
        size_x=4,
        size_y=4,
        status=(0,) * 11,
        charge=(0.0, 0.0, 0.0),
        robot=(1, 0.0, 0.0, 0.0),
        rooms=[(10, "客厅", 0.0, 0.0)],
    )
    header = mp.parse_map(raw).header
    assert header.with_status
    assert header.with_map_data
    assert header.with_charge
    assert header.with_robot
    assert header.with_plan
    assert not header.with_history
    assert not header.with_wall
    assert not header.with_area
    assert not header.with_spot


def test_status_and_grid() -> None:
    """状态区与栅格读取正确（含障碍与地面像素）。"""
    values = {(0, 0): mp.MAP_VALUE_OBSTACLE, (1, 1): mp.MAP_VALUE_NOT_ARRIVED}
    raw = build_map(
        grid=_grid(values, 4, 4),
        size_x=4,
        size_y=4,
        resolution=0.5,
        min_x=-1.0,
        min_y=-2.0,
        status=(0, 0, 0, 195, 1, 3, 2103, 0, 0, 0, 0),
    )
    package = mp.parse_map(raw)
    assert package.status is not None
    assert package.status.battery_percent == 195
    assert package.status.charge_state == 1
    assert package.status.fault_type == 3
    assert package.status.fault_code == 2103
    map_data = package.map_data
    assert map_data is not None
    assert (map_data.size_x, map_data.size_y) == (4, 4)
    assert map_data.resolution == 0.5
    assert len(map_data.grid) == 16
    assert map_data.cell(0, 0) == 255
    assert map_data.cell(1, 1) == 1
    assert map_data.cell(2, 2) == 0


def test_physics_to_grid() -> None:
    """物理坐标 → 栅格坐标（``physicsToGrid``）。"""
    raw = build_map(
        grid=[0] * 16, size_x=4, size_y=4, resolution=0.5, min_x=-1.0, min_y=-2.0
    )
    map_data = mp.parse_map(raw).map_data
    assert map_data is not None
    assert map_data.physics_to_grid(-1.0, -2.0) == (0.0, 0.0)
    assert map_data.physics_to_grid(-0.5, -0.5) == (1.0, 3.0)


def test_rooms() -> None:
    """协议 V2 房间名与中点解析。"""
    raw = build_map(
        grid=[0] * 16,
        size_x=4,
        size_y=4,
        rooms=[(10, "客厅", 0.5, -0.5), (11, "卧室", 1.0, 1.0)],
    )
    rooms = mp.parse_map(raw).rooms
    assert [(room.room_id, room.name) for room in rooms] == [(10, "客厅"), (11, "卧室")]
    assert rooms[0].middle_x == 0.5
    assert rooms[0].middle_y == -0.5


def test_robot_charge_spot_history() -> None:
    """机器人 / 充电座 / 定点 / 历史轨迹解析。"""
    raw = build_map(
        grid=[0] * 16,
        size_x=4,
        size_y=4,
        history=[(1, 0.5, 0.5)],
        charge=(0.5, 0.5, 1.5),
        spot=(3, 0.25, 0.75, 0.0),
        robot=(1, 0.1, 0.2, 3.0),
    )
    package = mp.parse_map(raw)
    assert package.charge is not None and package.charge.pose_x == 0.5
    assert package.charge.pose_phi == 1.5
    assert package.spot is not None and package.spot.ctrl_value == 3
    assert package.robot is not None and package.robot.pose_x == pytest.approx(0.1)
    assert package.robot.pose_phi == 3.0
    assert package.history is not None and len(package.history.items) == 1
    assert package.history.items[0].pose_x == 0.5


def test_wall_and_area() -> None:
    """墙 / 区域多边形解析（每项固定 10 点，按 count 截断）。"""
    raw = build_map(
        grid=[0] * 16,
        size_x=4,
        size_y=4,
        wall=[(1, [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5)])],
        area=[(2, [(0.1, 0.1)])],
    )
    package = mp.parse_map(raw)
    assert package.wall is not None and len(package.wall.items) == 1
    assert package.wall.items[0].count == 3
    assert len(package.wall.items[0].points) == 3
    assert package.area is not None and len(package.area.items) == 1


def test_map_value_2_room_id() -> None:
    """像素值 → 房间 ID 的区间映射。"""
    assert mp.map_value_2_room_id(mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW) == 10
    assert mp.map_value_2_room_id(mp.MAP_VALUE_NOT_ARRIVED_ROOM_HIGH) == 59
    assert mp.map_value_2_room_id(mp.MAP_VALUE_ARRIVED_ROOM_LOW) == 10
    assert mp.map_value_2_room_id(mp.MAP_VALUE_ARRIVED_ROOM_HIGH) == 69
    assert mp.map_value_2_room_id(mp.MAP_VALUE_BACKGROUND) == -1
    assert mp.map_value_2_room_id(mp.MAP_VALUE_OBSTACLE) == -1


def test_plain_uncompressed_bytes() -> None:
    """非 zlib 输入按原始字节解析（容错）。"""
    raw = build_map(grid=[0] * 16, size_x=4, size_y=4)
    package = mp.parse_map(zlib.decompress(raw))
    assert package.map_data is not None and package.map_data.size_x == 4


def test_too_short_raises() -> None:
    """输入过短抛 ``MapParseError``。"""
    with pytest.raises(mp.MapParseError):
        mp.parse_map(b"\x01")


def test_truncated_status_raises() -> None:
    """状态区被截断抛 ``MapParseError``。"""
    raw = zlib.decompress(build_map(grid=[0] * 16, size_x=4, size_y=4, status=(0,) * 11))
    with pytest.raises(mp.MapParseError):
        mp.parse_map(raw[:20])
