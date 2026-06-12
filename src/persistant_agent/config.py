from functools import lru_cache
from pathlib import Path
import shlex

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    target_repo: Path = Field(default=Path("/workspace/repo"), alias="TARGET_REPO")
    codex_command: str = Field(default="codex", alias="CODEX_COMMAND")
    codex_args: str = Field(default="", alias="CODEX_ARGS")
    model_command_template: str = Field(default="/model {model}", alias="CODEX_MODEL_COMMAND_TEMPLATE")
    effort_command_template: str = Field(default="/reasoning {effort}", alias="CODEX_EFFORT_COMMAND_TEMPLATE")
    clear_command: str = Field(default="/clear", alias="CODEX_CLEAR_COMMAND")
    compact_command: str = Field(default="/compact", alias="CODEX_COMPACT_COMMAND")
    api_token: str = Field(default="", alias="API_TOKEN")

    @property
    def codex_argv(self) -> list[str]:
        return [self.codex_command, *shlex.split(self.codex_args)]


@lru_cache
def get_settings() -> Settings:
    return Settings()
