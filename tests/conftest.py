"""pytest 测试环境准备。

``custom_components/netease_intelligent/__init__.py`` 会导入 ``homeassistant``，这是重型
依赖，单元测试 DTO 层（``const`` / ``models``）时不应引入。这里用一个合成包名
``netease_intelligent`` 加载这两个纯 Python 模块，使 ``models.py`` 的相对导入
``from .const import ...`` 正常解析——不修改生产代码，也不打 ``sys.path`` 补丁。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_PKG = "netease_intelligent"
_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "netease_intelligent"

# 注册合成父包，使 ``import netease_intelligent.models`` 可用。
if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = []
    sys.modules[_PKG] = _pkg


def _load_module(name: str) -> None:
    """按合成包路径加载一个纯 Python 模块（幂等）。"""
    mod_name = f"{_PKG}.{name}"
    if mod_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(mod_name, _DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)


# 依赖顺序：models 相对导入 const。
_load_module("const")
_load_module("models")

# ``push_protocol`` 仅依赖 ``.models``（推送帧解析与数据合并）。
_load_module("push_protocol")

# ``api`` 依赖 ``aiohttp``（见 requirements_test.txt）与 ``.const`` / ``.models``。
_load_module("api")

# 地图解析仅依赖标准库；渲染依赖 ``PIL``（见 requirements_test.txt）与 ``.map_parser``。
_load_module("map_parser")
_load_module("map_render")
