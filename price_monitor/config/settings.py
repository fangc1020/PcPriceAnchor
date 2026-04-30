from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/price_monitor"
    jd_pt_key: str = ""
    jd_pt_pin: str = ""
    crawl_interval_minutes: int = 120


settings = Settings()
