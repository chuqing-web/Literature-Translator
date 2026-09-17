from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LT_")

    app_name: str = "Literature Translator"
    api_host: str = "127.0.0.1"
    api_port: int = 8787
    web_port: int = 5173
    data_dir: Path = Path(__file__).resolve().parents[3] / "data"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    # Close browser → stop Vite + API after heartbeat gap (set LT_AUTO_SHUTDOWN=0 to disable)
    auto_shutdown: bool = True
    heartbeat_timeout_sec: float = 12.0
    leave_grace_sec: float = 3.0

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lit.db"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / ".secret_key"


settings = Settings()
