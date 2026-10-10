"""网易智造业务 API 客户端。

在线上环境 ``https://3c.163.com`` 上以 Cookie 认证
（``ONE_TOKEN`` / ``ONE_TOKEN_ID`` / ``UA-INFO``，见 docs/API工作原理.md 第 4 节）
调用 ``/ai-app`` 业务接口，并按统一响应结构 ``ResponseWrapper`` 解包
（``code=0`` 成功，``result`` 为业务数据，见第 5 节）。

当前实现家庭域端点（``docs/openapi/kernel.yaml``）：

- ``GET /ai-app/family/info`` —— 家庭列表信息（含房间/成员/设备）；
- ``GET /ai-app/family/query`` —— 查询单个家庭；
- ``GET /ai-app/family/env/info/homepage`` —— 家庭环境信息；
- ``GET /ai-app/equip/list`` —— 账号下设备列表；
- ``GET /ai-app/sweeper/rv02/getDeviceData`` —— 扫地机实时数据。
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import BASE_URL
from .models import Equip, Family, FamilyEnv, FamilyInfo, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)

# 客户端 User-Agent，复刻 kernel/network/HeaderManager.getUserAgent()
# （docs/API工作原理.md 第 4 节），格式为：
#
#   <http.agent> <appName>/<productName>/<version>/<buildType>/<source>[/<keyWord>]
#
# 其中 <http.agent> 为 Android 平台默认 UA（System.getProperty("http.agent")），
# 其余各段取自 App 内常量与 assets/source 资源。
ANDROID_HTTP_AGENT: str = (
    "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 5 Build/TQ3A.230805.001)"
)  # 平台默认 UA；HA 非 Android，按集成统一的设备模拟（Pixel 5 / Android 13）给出等价前缀
APP_NAME: str = "Intelligent"  # MiscUtils.APP_NAME
PRODUCT_NAME: str = "ntes3c"  # MiscUtils.PRODUCT_NAME
APP_VERSION: str = "5.3.5"  # versionName（取 "-" 前的部分）
BUILD_TYPE: str = "release"  # MiscUtils.getBuildType()
SOURCE: str = "Release"  # assets/source 首段（BaseApplication.aSource[0]）
KEY_WORD: str = ""  # assets/source 的 "|" 第二段（BaseApplication.aSource[1]，此处为空）


def build_user_agent(
    *,
    http_agent: str = ANDROID_HTTP_AGENT,
    app_name: str = APP_NAME,
    product_name: str = PRODUCT_NAME,
    version: str = APP_VERSION,
    build_type: str = BUILD_TYPE,
    source: str = SOURCE,
    key_word: str = KEY_WORD,
) -> str:
    """按 ``HeaderManager.getUserAgent()`` 的规则拼装客户端 UA。"""
    ua = (
        f"{http_agent} {app_name}/{product_name}/{version}"
        f"/{build_type}/{source}"
    )
    if key_word:
        ua += f"/{key_word}"
    return ua


USER_AGENT: str = build_user_agent()

# 端点在 kernel/config/Action.java（见 docs/openapi/kernel.yaml 的 kernel tag）。
PATH_FAMILY_INFO: str = "/ai-app/family/info"
PATH_FAMILY_QUERY: str = "/ai-app/family/query"
PATH_FAMILY_ENV_INFO: str = "/ai-app/family/env/info/homepage"
PATH_EQUIP_LIST: str = "/ai-app/equip/list"

# 扫地机模块端点（见 docs/openapi/sweeper.yaml 的 sweeper tag）。
PATH_SWEEPER_DEVICE_DATA: str = "/ai-app/sweeper/rv02/getDeviceData"


class ApiError(Exception):
    """业务或网络错误。

    ``code`` 为 ``ResponseWrapper.code``；网络层错误时取 HTTP 状态码（否则为 -1）。
    """

    def __init__(self, code: int, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"Netease API error {code}: {message}")


class NeteaseIntelligentApiClient:
    """基于共享 ``aiohttp.ClientSession`` 的业务 API 客户端。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        token: str,
        token_id: str,
        ua_info: str = "",
        base_url: str = BASE_URL,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._session = session
        self._token = token
        self._token_id = token_id
        self._ua_info = ua_info
        self._base_url = base_url
        self._user_agent = user_agent

    @property
    def _cookie(self) -> str:
        """组装认证 Cookie（见 docs/API工作原理.md 第 4 节）。"""
        cookie = f"ONE_TOKEN={self._token}; ONE_TOKEN_ID={self._token_id}"
        if self._ua_info:
            cookie += f"; UA-INFO={self._ua_info}"
        return cookie

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """发起请求并解包 ``ResponseWrapper``，返回 ``result``。"""
        url = self._base_url + path
        headers = {"Cookie": self._cookie, "User-Agent": self._user_agent}
        try:
            async with self._session.request(
                method, url, params=params, data=data, json=json, headers=headers
            ) as resp:
                if resp.status != 200:
                    raise ApiError(resp.status, f"HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except ApiError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ApiError(-1, str(err)) from err

        if not isinstance(payload, dict):
            raise ApiError(-1, "invalid response payload")

        code = payload.get("code")
        if code != 0:
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = -1
            raise ApiError(code, payload.get("errorMsg") or "")
        return payload.get("result")

    async def get_family_info(self) -> FamilyInfo:
        """``GET /ai-app/family/info``：获取家庭列表信息。"""
        return FamilyInfo.from_dict(await self._request("GET", PATH_FAMILY_INFO))

    async def get_family(self, family_id: int) -> Family:
        """``GET /ai-app/family/query``：查询单个家庭。"""
        result = await self._request(
            "GET", PATH_FAMILY_QUERY, params={"familyId": family_id}
        )
        return Family.from_dict(result)

    async def get_env_info(self, family_id: int) -> FamilyEnv:
        """``GET /ai-app/family/env/info/homepage``：家庭环境信息。"""
        result = await self._request(
            "GET", PATH_FAMILY_ENV_INFO, params={"familyId": family_id}
        )
        return FamilyEnv.from_dict(result)

    async def get_equip_list(self) -> list[Equip]:
        """``GET /ai-app/equip/list``：账号下设备列表。"""
        result = await self._request("GET", PATH_EQUIP_LIST) or {}
        return [Equip.from_dict(item) for item in result.get("list", [])]

    async def get_sweeper_data(self, equip_id: str) -> SweeperDeviceData:
        """``GET /ai-app/sweeper/rv02/getDeviceData``：扫地机实时数据。"""
        result = await self._request(
            "GET", PATH_SWEEPER_DEVICE_DATA, params={"equipId": equip_id}
        )
        return SweeperDeviceData.from_dict(result)
