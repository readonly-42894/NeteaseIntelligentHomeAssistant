"""地图渲染（``map_render.py``）单元测试。

用合成地图包验证 PNG 输出、房间棋盘调色板、障碍上色与退化输入容错。
需要 Pillow（见 requirements_test.txt）。
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

import netease_intelligent.map_parser as mp
import netease_intelligent.map_render as mr
from map_fixture import build_map


def _render(
    *,
    grid: list[int],
    size_x: int = 4,
    size_y: int = 4,
    **kwargs: object,
) -> bytes:
    raw = build_map(grid=grid, size_x=size_x, size_y=size_y, **kwargs)
    return mr.render_map(mp.parse_map(raw))


def _colors(png: bytes) -> set[tuple[int, int, int]]:
    raw = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
    return {tuple(raw[i : i + 3]) for i in range(0, len(raw), 3)}


def test_render_returns_png() -> None:
    """渲染输出为合法 PNG。"""
    grid = [0] * 16
    grid[0] = mp.MAP_VALUE_OBSTACLE
    grid[1] = mp.MAP_VALUE_NOT_ARRIVED
    grid[2] = mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW
    png = _render(grid=grid, resolution=1.0, robot=(1, 0.5, 0.5, 0.0))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    image = Image.open(io.BytesIO(png))
    assert image.width > 0 and image.height > 0


def test_render_requires_map_data() -> None:
    """缺少栅格数据时抛 ``ValueError``。"""
    package = mp.MapPackage(header=mp.MapHeader.from_bytes(0x01, 0))
    with pytest.raises(ValueError):
        mr.render_map(package)


def test_room_checkerboard_colors_present() -> None:
    """房间格使用 6 组双色调色板（棋盘交替两色均出现）。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW] * 16
    colors = _colors(_render(grid=grid, resolution=1.0))
    assert (0xA9, 0x9B, 0xDB) in colors
    assert (0xCB, 0xC3, 0xE9) in colors


def test_obstacle_color_present() -> None:
    """障碍格上色为 ``#717AE4``。"""
    grid = [mp.MAP_VALUE_OBSTACLE] + [0] * 15
    assert (0x71, 0x7A, 0xE4) in _colors(_render(grid=grid, resolution=1.0))


def test_cell_color_room_checkerboard_parity() -> None:
    """相邻 2×2 块奇偶不同 → 颜色不同。"""
    c00 = mr._cell_color(mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW, 0, 0)
    c20 = mr._cell_color(mp.MAP_VALUE_NOT_ARRIVED_ROOM_LOW, 2, 0)
    assert c00 is not None and c20 is not None and c00 != c20


def test_all_background_falls_back() -> None:
    """全背景时回退居中窗口，不崩溃。"""
    png = _render(grid=[0] * 16, resolution=1.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_out_of_range_marker_ignored() -> None:
    """越界哨兵坐标（如空定点 1100.0）不扩大渲染范围也不绘制。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] + [0] * 15
    png = _render(grid=grid, resolution=1.0, spot=(0, 1100.0, 1100.0, 0.0))
    assert (0xE5, 0x39, 0x35) not in _colors(png)


def test_history_mode_cleaned_colors() -> None:
    """history 模式：已清扫地面 ``#D2D5FF``、已清扫房间实色均出现。"""
    grid = [0] * 16
    grid[0] = mp.MAP_VALUE_ARRIVED
    grid[1] = mp.MAP_VALUE_ARRIVED_ROOM_LOW  # 60 → roomId 10 → 调色板索引 0
    colors = _colors(_render(grid=grid, resolution=1.0))
    assert mr._COLOR_ARRIVED in colors
    assert mr._ROOM_COLOR_ARRIVED[0] in colors


def test_live_mode_arrived_is_white() -> None:
    """history=False：已清扫地面保持白色，不出现清扫着色。"""
    grid = [mp.MAP_VALUE_ARRIVED] * 16
    package = mp.parse_map(build_map(grid=grid, size_x=4, size_y=4, resolution=1.0))
    colors = _colors(mr.render_map(package, history=False))
    assert (0xFF, 0xFF, 0xFF) in colors
    assert mr._COLOR_ARRIVED not in colors


def test_history_path_color() -> None:
    """history 模式且轨迹点足够时绘制轨迹；关闭 history 时不绘制。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 16
    history = [(0, 0.5, 0.5), (0, 1.5, 1.5), (0, 2.5, 2.5)]
    raw = build_map(grid=grid, size_x=4, size_y=4, resolution=1.0, history=history)
    package = mp.parse_map(raw)
    assert mr._COLOR_PATH in _colors(mr.render_map(package))
    assert mr._COLOR_PATH not in _colors(mr.render_map(package, history=False))


def test_history_path_requires_two_points() -> None:
    """轨迹点不足 2 个时跳过绘制且不报错。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 16
    png = _render(grid=grid, resolution=1.0, history=[(0, 1.5, 1.5)])
    assert (0x93, 0xC2, 0xEE) not in _colors(png)


def test_wall_outline_color() -> None:
    """虚拟墙绘制为 App 边框色 ``#364866``（含斜纹纹理填充）。"""
    grid = [0] * 16
    grid[0] = mp.MAP_VALUE_NOT_ARRIVED
    wall = [(1, [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)])]
    assert mr._COLOR_WALL in _colors(_render(grid=grid, resolution=1.0, wall=wall))


def test_area_outline_color() -> None:
    """清扫区域绘制半透明填充 + 轮廓（轮廓为区域文字色）。"""
    grid = [0] * 16
    grid[0] = mp.MAP_VALUE_NOT_ARRIVED
    area = [(1, [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)])]
    assert mr._COLOR_AREA_TEXT in _colors(_render(grid=grid, resolution=1.0, area=area))


def test_empty_overlay_layers_ok() -> None:
    """空的墙/区域/轨迹不绘制也不报错。"""
    png = _render(grid=[0] * 16, resolution=1.0, wall=[], area=[], history=[])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_marker_radius_uses_physical_size() -> None:
    """标记半径按物理尺寸与分辨率换算。"""
    map_data = mp.MapData(size_x=10, size_y=10, resolution=0.05)
    # 0.35m 机器人 → 半径 3.5 格 → cell=10 时 35px
    assert mr._marker_radius(map_data, 10, 0.35) == 35
    assert mr._marker_radius(map_data, 10, 0.28) == 28
    # 分辨率缺失时按 1.0 兜底，且至少 3px
    assert mr._marker_radius(mp.MapData(size_x=1, size_y=1, resolution=0.0), 1, 0.35) == 3


def test_map_assets_available() -> None:
    """App 地图 drawable 资源可从包内加载（尺寸与 APK 一致）。"""
    assert mr._load_asset("robot.png").size == (132, 132)
    assert mr._load_asset("charge.png").size == (108, 108)
    assert mr._load_asset("spot.png").size == (72, 72)
    assert mr._load_asset("wall_cell.png").size == (80, 80)
    assert mr._load_asset("area_cell.png").size == (80, 80)
    assert mr._load_asset("bg_cell.png").size == (15, 15)


def test_robot_glyph_pasted() -> None:
    """机器人直接贴 App 图标（出现图标主体蓝 #404BCA）。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 16
    png = _render(grid=grid, resolution=1.0, robot=(1, 1.0, 1.0, 0.0))
    assert (0x40, 0x4B, 0xCA) in _colors(png)


def test_charge_glyph_pasted() -> None:
    """充电座直接贴 App 图标（出现图标橙 #FF8F00）。"""
    grid = [mp.MAP_VALUE_NOT_ARRIVED] * 16
    png = _render(grid=grid, resolution=1.0, charge=(1.0, 1.0, 0.0))
    assert (0xFF, 0x8F, 0x00) in _colors(png)
