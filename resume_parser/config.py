from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    max_concurrent: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()