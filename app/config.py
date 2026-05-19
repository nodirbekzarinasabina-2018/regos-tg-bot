from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_placeholder(value: str) -> bool:
    stripped = (value or "").strip()
    return (
        not stripped
        or stripped.startswith("YOUR_")
        or stripped == "123456:ABCDEF"
        or stripped == "-1001234567890"
        or stripped == "very_secret_path_token"
    )


@dataclass(frozen=True)
class TelegramBotConfig:
    key: str
    label: str
    bot_token: str
    group_chat_id: str
    webhook_secret: str

    @property
    def enabled(self) -> bool:
        return not _is_placeholder(self.bot_token)

    @property
    def group_configured(self) -> bool:
        return not _is_placeholder(self.group_chat_id)

    @property
    def webhook_configured(self) -> bool:
        return not _is_placeholder(self.webhook_secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_timezone: str = Field(default="Asia/Tashkent", alias="APP_TIMEZONE")
    app_brand_name: str = Field(default="Chust optom No 1", alias="APP_BRAND_NAME")

    regos_integration_key: str = Field(alias="REGOS_INTEGRATION_KEY")
    regos_connected_integration_id: str = Field(default="", alias="REGOS_CONNECTED_INTEGRATION_ID")
    regos_base_url: str = Field(
        default="https://integration.regos.uz/gateway/out",
        alias="REGOS_BASE_URL",
    )
    regos_timeout_seconds: int = Field(default=20, alias="REGOS_TIMEOUT_SECONDS")

    regos_use_oauth: bool = Field(default=False, alias="REGOS_USE_OAUTH")
    regos_token_url: str = Field(
        default="https://auth.regos.uz/oauth/token",
        alias="REGOS_TOKEN_URL",
    )
    regos_client_id: str = Field(default="", alias="REGOS_CLIENT_ID")
    regos_client_secret: str = Field(default="", alias="REGOS_CLIENT_SECRET")
    regos_oauth_scope: str = Field(default="", alias="REGOS_OAUTH_SCOPE")

    telegram_bot_token: str = Field(default="123456:ABCDEF", alias="TELEGRAM_BOT_TOKEN")
    telegram_group_chat_id: str = Field(default="-1001234567890", alias="TELEGRAM_GROUP_CHAT_ID")
    telegram_webhook_secret: str = Field(default="very_secret_path_token", alias="TELEGRAM_WEBHOOK_SECRET")

    wholesale_bot_token: str = Field(default="123456:ABCDEF", alias="WHOLESALE_BOT_TOKEN")
    wholesale_group_chat_id: str = Field(default="-1001234567890", alias="WHOLESALE_GROUP_CHAT_ID")
    wholesale_webhook_secret: str = Field(default="very_secret_path_token", alias="WHOLESALE_WEBHOOK_SECRET")
    wholesale_admin_phone: str = Field(default="", alias="WHOLESALE_ADMIN_PHONE")
    wholesale_payment_group_enabled: bool = Field(default=False, alias="WHOLESALE_PAYMENT_GROUP_ENABLED")

    retail_bot_token: str = Field(default="123456:ABCDEF", alias="RETAIL_BOT_TOKEN")
    retail_group_chat_id: str = Field(default="-1001234567890", alias="RETAIL_GROUP_CHAT_ID")
    retail_webhook_secret: str = Field(default="very_secret_path_token", alias="RETAIL_WEBHOOK_SECRET")

    warehouse_bot_token: str = Field(default="123456:ABCDEF", alias="WAREHOUSE_BOT_TOKEN")
    warehouse_group_chat_id: str = Field(default="-1001234567890", alias="WAREHOUSE_GROUP_CHAT_ID")
    warehouse_webhook_secret: str = Field(default="very_secret_path_token", alias="WAREHOUSE_WEBHOOK_SECRET")

    reminder_bot_token: str = Field(default="123456:ABCDEF", alias="REMINDER_BOT_TOKEN")
    reminder_group_chat_id: str = Field(default="-1001234567890", alias="REMINDER_GROUP_CHAT_ID")
    reminder_webhook_secret: str = Field(default="very_secret_path_token", alias="REMINDER_WEBHOOK_SECRET")

    storage_path: Path = Field(default=Path("./data/bot.db"), alias="STORAGE_PATH")
    temp_dir: Path = Field(default=Path("./data/tmp"), alias="TEMP_DIR")

    def shared_bot_config(self) -> TelegramBotConfig:
        return TelegramBotConfig(
            key="shared",
            label="Shared",
            bot_token=self.telegram_bot_token,
            group_chat_id=self.telegram_group_chat_id,
            webhook_secret=self.telegram_webhook_secret,
        )

    def bot_config(self, key: str) -> TelegramBotConfig:
        if key == "wholesale":
            return TelegramBotConfig(
                key="wholesale",
                label="Wholesale",
                bot_token=self.wholesale_bot_token,
                group_chat_id=self.wholesale_group_chat_id,
                webhook_secret=self.wholesale_webhook_secret,
            )
        if key == "retail":
            return TelegramBotConfig(
                key="retail",
                label="Retail",
                bot_token=self.retail_bot_token,
                group_chat_id=self.retail_group_chat_id,
                webhook_secret=self.retail_webhook_secret,
            )
        if key == "warehouse":
            return TelegramBotConfig(
                key="warehouse",
                label="Warehouse",
                bot_token=self.warehouse_bot_token,
                group_chat_id=self.warehouse_group_chat_id,
                webhook_secret=self.warehouse_webhook_secret,
            )
        if key == "reminder":
            return TelegramBotConfig(
                key="reminder",
                label="Reminder",
                bot_token=self.reminder_bot_token,
                group_chat_id=self.reminder_group_chat_id,
                webhook_secret=self.reminder_webhook_secret,
            )
        if key == "shared":
            return self.shared_bot_config()
        raise KeyError(f"Unknown bot key: {key}")

    def actual_bot_config(self, preferred_key: str) -> TelegramBotConfig:
        config = self.bot_config(preferred_key)
        if config.enabled:
            return config

        shared = self.shared_bot_config()
        if shared.enabled:
            return shared

        return config

    def enabled_bot_configs(self) -> dict[str, TelegramBotConfig]:
        configs: dict[str, TelegramBotConfig] = {}
        shared = self.shared_bot_config()
        if shared.enabled:
            configs[shared.key] = shared

        for key in ("wholesale", "retail", "warehouse", "reminder"):
            config = self.bot_config(key)
            if config.enabled:
                configs[key] = config
        return configs


@lru_cache
def get_settings() -> Settings:
    return Settings()
