"""pytest 基座：让测试跑在真实 Home Assistant 内核里。

``pytest-homeassistant-custom-component`` 提供 ``hass`` 夹具（进程内的真实 HA
实例）与 ``enable_custom_integrations``（允许 HA 加载 ``custom_components/`` 下的
自定义集成）。本文件只做两件事：

1. 把仓库根目录加入 ``sys.path``，使 ``custom_components.netease_intelligent``
   成为可导入包（PEP 420 命名空间包，无需额外 ``__init__.py``）；
2. 对所有测试自动启用自定义集成，避免逐个测试声明。

纯逻辑测试（DTO / 地图解析 / 推送协议）同样经 ``custom_components.netease_intelligent.*``
导入，与 HA 加载集成时使用的是同一份模块对象，不会出现两套类定义。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """为所有测试启用 ``custom_components/`` 下的自定义集成。"""
