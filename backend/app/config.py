from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv("../.env")
load_dotenv(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    supabase_url: str
    supabase_anon_key: str
    database_url: str
    agent_database_url: str
    llm_model: str = "gemini-3.6-flash"
    embedding_model: str = "gemini-embedding-001"


settings = Settings()
