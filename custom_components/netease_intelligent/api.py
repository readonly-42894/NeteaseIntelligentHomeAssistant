"""网易智造业务 API 客户端。

在线上环境 ``https://3c.163.com`` 上以 Cookie 认证
（``ONE_TOKEN`` / ``ONE_TOKEN_ID`` / ``UA-INFO``，见 docs/API工作原理.md 第 4 节）
调用 ``/ai-app`` 业务接口，并按统一响应结构 ``ResponseWrapper`` 解包
（``code=0`` 成功，``result`` 为业务数据，见第 5 节）。

当前实现家庭域端点（``docs/openapi.yaml``）：

- ``GET /ai-app/family/info`` —— 家庭列表信息（含房间/成员/设备）；
- ``GET /ai-app/family/query`` —— 查询单个家庭；
- ``GET /ai-app/family/env/info/homepage`` —— 家庭环境信息；
- ``GET /ai-app/equip/list`` —— 账号下设备列表。
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import BASE_URL
from .models import Equip, Family, FamilyEnv, FamilyInfo

_LOGGER = logging.getLogger(__name__)

# 全局注入的 User-Agent（docs/API工作原理.md 第 4 节）。App 的真实 UA 未在
# 反编译资料中记录，此处使用占位值，可经构造参数覆盖。
USER_AGENT: str = "NeteaseIntelligent/5.3.5"

# 端点在 kernel/config/Action.java（见 docs/openapi.yaml 的 kernel tag）。
PATH_FAMILY_INFO: str = "/ai-app/family/info"
PATH_FAMILY_QUERY: str = "/ai-app/family/query"
PATH_FAMILY_ENV_INFO: str = "/ai-app/family/env/info/homepage"
PATH_EQUIP_LIST: str = "/ai-app/equip/list"


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
