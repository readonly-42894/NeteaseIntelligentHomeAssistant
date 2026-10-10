"""Config flow for the 网易智造 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_TOKEN, CONF_TOKEN_ID, DOMAIN


class NeteaseIntelligentConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 网易智造.

    认证走 Cookie（ONE_TOKEN / ONE_TOKEN_ID），此处先以手动录入凭据的方式
    建立配置项；后续可替换为短信/邮箱/微信登录流程（见 docs/API工作原理.md 第 7 节）。
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TOKEN_ID])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_TOKEN_ID], data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_TOKEN_ID): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
