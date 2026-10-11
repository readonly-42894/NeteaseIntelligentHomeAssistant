"""实时轨迹（``map_parser.parse_trajectory`` / ``apply_trajectory``）单元测试。

复刻 App ``MapHistoryParser``：仅 ``update==1`` 的点绘制，以 7×7 画笔把「未到达」
标为「已到达」（房间态同理），并在相邻点间直线填充。
"""

from __future__ import annotations

import netease_intelligent.map_parser as mp
from map_fixture import build_map


def _package(grid: list[int], size_x: int = 20, size_y: int = 20, **kwargs: object):
    return mp.parse_map(build_map(grid=grid, size_x=size_x, size_y=size_y, **kwargs))


def test_parse_trajectory_three_int_records() -> None:
    """三值记录 ``[poseX, poseY, update]``（坐标 /10000）。"""
    points = mp.parse_trajectory([100000, 200000, 1])
    assert len(points) == 1
    assert points[0].update == 1
    assert points[0].pose_x == 10.0
    assert points[0].pose_y == 20.0


def test_parse_trajectory_six_int_records() -> None:
    """六值记录 ``[mapHeadId, poseId, update, poseX, poseY, posePhi]``。"""
    points = mp.parse_trajectory([5, 9, 1, 300000, 400000, 15000])
    assert len(points) == 1
    assert points[0].map_head_id == 5
    assert points[0].pose_id == 9
    assert points[0].update == 1
    assert points[0].pose_x == 30.0
    assert points[0].pose_y == 40.0
    assert points[0].pose_phi == 1.5


def test_parse_trajectory_multiple_records() -> None:
    """多条三值记录按批次解析。"""
    points = mp.parse_trajectory([0, 0, 1, 10000, 0, 0, 20000, 0, 1])
    assert [p.update for p in points] == [1, 0, 1]
    assert [p.pose_x for p in points] == [0.0, 1.0, 2.0]


def test_parse_trajectory_invalid_width() -> None:
    """宽度既非 6 也非 3 的整数倍 → 空。"""
    assert mp.parse_trajectory([1, 2, 3, 4]) == []
    assert mp.parse_trajectory([]) == []


def test_apply_trajectory_marks_arrived() -> None:
    """画笔把「未到达」地面标为「已到达」，范围外的格子不变。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 400
    package = _package(grid)
    points = mp.parse_trajectory([100000, 100000, 1])  # 栅格 (10, 10)
    result = mp.apply_trajectory(package, points)
    assert result.map_data is not None
    assert result.map_data.cell(10, 10) == mp.MAP_VALUE_ARRIVED
    assert result.map_data.cell(7, 7) == mp.MAP_VALUE_ARRIVED
    assert result.map_data.cell(13, 13) == mp.MAP_VALUE_ARRIVED
    assert result.map_data.cell(6, 6) == mp.MAP_VALUE_NOT_ARRIVED
    assert result.map_data.cell(0, 0) == mp.MAP_VALUE_NOT_ARRIVED
    # 原包不被就地修改。
    assert package.map_data.cell(10, 10) == mp.MAP_VALUE_NOT_ARRIVED


def test_apply_trajectory_marks_arrived_room() -> None:
    """「未到达房间」标为「已到达房间」（+ARRIVED_ROOM_OFFSET）。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 400
    grid[10 * 20 + 10] = mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW  # room 10
    grid[10 * 20 + 11] = mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW + 5  # room 15
    package = _package(grid)
    result = mp.apply_trajectory(
        package, mp.parse_trajectory([100000, 100000, 1])
    )
    assert result.map_data.cell(10, 10) == mp.MAP_VALUE_ARRIVED_ROOM_LOW
    assert result.map_data.cell(11, 10) == mp.MAP_VALUE_ARRIVED_ROOM_LOW + 5


def test_apply_trajectory_skips_update_zero() -> None:
    """``update != 1`` 的点不绘制。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 400
    package = _package(grid)
    result = mp.apply_trajectory(package, mp.parse_trajectory([100000, 100000, 0]))
    assert result.map_data.cell(10, 10) == mp.MAP_VALUE_NOT_ARRIVED


def test_apply_trajectory_line_between_points() -> None:
    """相邻两点之间按直线补齐（中点超出画笔半径仍被填充）。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 400
    package = _package(grid)
    # 两条六值记录：(2,2) 与 (10,2)。
    points = mp.parse_trajectory([0, 0, 1, 20000, 20000, 0, 1, 1, 1, 100000, 20000, 0])
    result = mp.apply_trajectory(package, points)
    assert result.map_data.cell(6, 2) == mp.MAP_VALUE_ARRIVED
    assert result.map_data.cell(5, 2) == mp.MAP_VALUE_ARRIVED


def test_apply_trajectory_updates_robot_pose() -> None:
    """机器人位姿取最后一个轨迹点。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 400
    package = _package(grid)
    points = mp.parse_trajectory(
        [5, 5, 1, 50000, 50000, 0, 2, 7, 1, 120000, 80000, 0]
    )
    result = mp.apply_trajectory(package, points)
    assert result.robot is not None
    assert result.robot.pose_x == 12.0
    assert result.robot.pose_y == 8.0
    assert result.robot.pose_id == 7


def test_apply_trajectory_out_of_bounds_is_safe() -> None:
    """越界轨迹点不抛异常，栅格不变。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 16
    package = _package(grid, size_x=4, size_y=4)
    result = mp.apply_trajectory(
        package, mp.parse_trajectory([100000000, 100000000, 1])
    )
    assert result.map_data.grid == package.map_data.grid


def test_apply_trajectory_no_map_data() -> None:
    """无栅格的包原样返回。"""
    package = _package([mp.MAP_VALUE_NOT_ARRIVED] * 16, size_x=4, size_y=4)
    package.map_data = None
    assert mp.apply_trajectory(package, mp.parse_trajectory([1, 1, 1])) is package
