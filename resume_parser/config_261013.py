"""261013 版简历解析服务配置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings261013(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    max_concurrent: int = 5

    resume_model_io_log_enabled: bool = True
    resume_model_io_log_dir: str = "logs/resume_llm_io_261013"
    resume_model_io_log_include_sensitive: bool = False
    resume_model_io_log_max_text_chars: int = 120000
    resume_model_io_actor_hmac_secret: str = ""


settings_261013 = Settings261013()
