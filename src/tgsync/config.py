from os import environ
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra='allow')


class LogConfig(ConfigModel):
    level: str
    dir: Path | None = None


class DatabaseConfig(ConfigModel):
    url: str


class ChatConfig(ConfigModel):
    media: bool = True
    range: tuple[int, int] = (0, 0)
    sharding: Literal['month', 'week', 'day'] | None = 'day'


class TelegramConfig(ConfigModel):
    api_id: int
    api_hash: str
    session: str
    message_limit: int
    proxy: str | None = None
    chats: dict[str, ChatConfig]


class DownloadConfig(ConfigModel):
    media: Path
    incomplete: Path
    concurrent: int
    timeout: int
    summary_interval: int


class AppConfig(ConfigModel):
    log: LogConfig
    db: DatabaseConfig
    tg: TelegramConfig
    download: DownloadConfig


appdata = Path(environ.get('APPDATA', '/appdata'))

with open(appdata / 'config.yaml', 'r', encoding='utf-8') as f:
    yaml = YAML(typ='safe')
    config_dict = yaml.load(f)

config = AppConfig.model_validate(config_dict)
