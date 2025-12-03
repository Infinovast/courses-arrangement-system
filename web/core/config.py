from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 数据库配置
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5433
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "1478963a"
    DATABASE_NAME: str = "paike_db"

    # API配置
    API_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "排课系统"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
