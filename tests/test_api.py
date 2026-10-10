"""API 客户端（``api.py``）单元测试。

覆盖：User-Agent / UA-INFO 的生成（复刻 App 的 ``HeaderManager`` 与
``CookieManager``），以及认证 Cookie 必须始终携带 ``UA-INFO``。

导入方式见 ``conftest.py``（合成包名 ``netease_intelligent``）。
"""

from __future__ import annotations

import json
from urllib.parse import unquote_plus

import netease_intelligent.api as api


def test_build_user_agent() -> None:
    """UA 拼接规则：``<http.agent> <app>/<product>/<ver>/<build>/<source>``。"""
    ua = api.build_user_agent()
    assert ua.endswith("Intelligent/ntes3c/5.3.5/release/Release")
    assert ua.startswith("Dalvik/")


def test_build_ua_info_is_java_urlencoded_json() -> None:
    """UA-INFO 为 Java ``URLEncoder.encode`` 编码的 JSON，且字段与 App 一致。"""
    raw = api.build_ua_info()
    # Java URLEncoder 将空格编成 "+"，其余非 [A-Za-z0-9.-*_] 编成 %XX。
    assert " " not in raw
    assert "Pixel+5" in raw

    payload = json.loads(unquote_plus(raw))
    assert payload == {
        "PRODUCT": "ntes3c",
        "SOURCE": "Release",
        "KW": "",
        "APP-VER": "5.3.5",
        "APP-BUILD": "4353147",
        "BUILD-TYPE": "release",
        "TERMINAL": "android",
        "OS-VER": "13",
        "BRAND": "Google",
        "MODEL": "Pixel 5",
        "DENSITY": "2.75",
        "DEVICE-ID": "",
        "INFO-SIGN": "",
        "WIDTH": "1080",
        "HEIGHT": "2340",
    }


def test_cookie_always_includes_ua_info() -> None:
    """未显式传入 ua_info 时，Cookie 也应按默认 UA-INFO 携带它。"""
    client = api.NeteaseIntelligentApiClient(None, token="TOK", token_id="ID")
    cookie = client._cookie
    assert cookie.startswith("ONE_TOKEN=TOK; ONE_TOKEN_ID=ID; UA-INFO=")
    assert cookie.endswith(api.build_ua_info())


def test_cookie_respects_explicit_ua_info() -> None:
    """显式传入的 ua_info 优先于默认生成值。"""
    client = api.NeteaseIntelligentApiClient(
        None, token="TOK", token_id="ID", ua_info="CUSTOM"
    )
    assert client._cookie == "ONE_TOKEN=TOK; ONE_TOKEN_ID=ID; UA-INFO=CUSTOM"
