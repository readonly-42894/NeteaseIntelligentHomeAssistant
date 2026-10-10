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
