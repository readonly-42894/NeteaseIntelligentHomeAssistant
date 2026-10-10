"""Config flow for the 网易智造 integration.

支持三种登录方式：短信验证码、邮箱密码，以及手动录入 Cookie 凭据
（ONE_TOKEN / ONE_TOKEN_ID）。前两者通过逆向得到的网易 URS 登录协议
（见 urs.py）真实换取登录令牌。
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_SMS_CODE,
    CONF_TOKEN,
    CONF_TOKEN_ID,
    DOMAIN,
)
from .urs import UrsClient, UrsError


class NeteaseIntelligentConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 网易智造."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._urs: UrsClient | None = None
        self._phone: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step：选择登录方式。"""
        return self.async_show_menu(
            step_id="user",
            menu_options=["phone", "email", "manual"],
        )

    async def _client(self) -> UrsClient:
        """惰性创建（并复用）URS 客户端。"""
        if self._urs is None:
            self._urs = UrsClient(async_get_clientsession(self.hass))
        return self._urs

    async def _init_sdk(self) -> None:
        """确保 SDK 已初始化（复用已有 id/key）。"""
        client = await self._client()
        if not client.is_inited:
            await client.init()

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """输入手机号并发送短信验证码。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._init_sdk()
                await (await self._client()).acquire_sms_code(user_input[CONF_PHONE])
            except Exception as err:  # noqa: BLE001 - 统一转为表单错误
                errors["base"] = self._error_key(err)
            else:
                self._phone = user_input[CONF_PHONE]
                return await self.async_step_sms_code()

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({vol.Required(CONF_PHONE): str}),
            errors=errors,
        )

    async def async_step_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """输入短信验证码并完成登录。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token, ssn = await (await self._client()).verify_sms_code(
                    self._phone, user_input[CONF_SMS_CODE]
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = self._error_key(err)
            else:
                return await self._create_entry(token, ssn or self._phone)

        return self.async_show_form(
            step_id="sms_code",
            data_schema=vol.Schema({vol.Required(CONF_SMS_CODE): str}),
            errors=errors,
            description_placeholders={"phone": self._phone},
        )

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """邮箱密码登录。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._init_sdk()
                token, ssn, username = await (
                    await self._client()
                ).email_login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except Exception as err:  # noqa: BLE001
                errors["base"] = self._error_key(err)
            else:
                return await self._create_entry(
                    token, username or ssn or user_input[CONF_EMAIL]
                )

        return self.async_show_form(
            step_id="email",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """手动录入 Cookie 凭据。"""
        if user_input is not None:
            return await self._create_entry(
                user_input[CONF_TOKEN],
                user_input[CONF_TOKEN_ID],
                token_id=user_input[CONF_TOKEN_ID],
            )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Required(CONF_TOKEN_ID): str,
                }
            ),
        )

    async def _create_entry(
        self, token: str, title: str, *, token_id: str | None = None
    ) -> ConfigFlowResult:
        """创建配置项。token_id 来自 URS 初始化（或手动录入）。"""
        if token_id is None:
            token_id = self._urs.token_id if self._urs is not None else ""
        await self.async_set_unique_id(token_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=title,
            data={CONF_TOKEN: token, CONF_TOKEN_ID: token_id},
        )

    @staticmethod
    def _error_key(err: Exception) -> str:
        """把异常映射为 strings.json 中的错误键。"""
        if isinstance(err, UrsError):
            code = err.code
            if code == 415:
                return "invalid_code"
            if code in (413, 460):
                return "invalid_auth"
            if code in (412, 414, 416, 417, 418, 419):
                return "too_frequent"
            if code in (422, 602):
                return "account_locked"
            if code == 420:
                return "user_not_found"
            if code in (500, 503):
                return "server_error"
            if code == 427:
                return "id_invalid"
            return "unknown"
        return "cannot_connect"
