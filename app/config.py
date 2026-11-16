from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./wrapper.db"

    keitaro_url: str = "https://tlgk.host"
    keitaro_api_key: str = ""
    keitaro_timeout: float = 20.0

    # Names used by the campaign creator to look up ids through the Keitaro API.
    # Empty means "use the first active domain of the account".
    domain_name: str = ""
    group_name: str = "FORTESTS"
    source_name: str = "FORTESTS"
    redirect_url: str = "https://google.com"

    # Prefilled in the creation form, the test assignment asks for test_<surname>_.
    name_prefix: str = "test_musaev_"


@lru_cache
def get_settings() -> Settings:
    return Settings()
