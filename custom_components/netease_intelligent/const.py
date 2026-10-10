"""Constants for the 网易智造 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "netease_intelligent"
NAME: Final = "网易智造"
MANUFACTURER: Final = "Netease"

# 线上环境的 API Base URL，见 docs/API工作原理.md 第 3 节。
BASE_URL: Final = "https://3c.163.com"

# 配置项：认证走 Cookie，见 docs/API工作原理.md 第 4 节。
CONF_TOKEN: Final = "token"  # Cookie: ONE_TOKEN
CONF_TOKEN_ID: Final = "token_id"  # Cookie: ONE_TOKEN_ID
CONF_UA_INFO: Final = "ua_info"  # Cookie: UA-INFO

DEFAULT_NAME: Final = NAME
