from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://tracker:tracker@localhost:5432/tracker"
    app_version: str = "dev"

settings = Settings()
