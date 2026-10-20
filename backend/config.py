"""Configuration management for Sahayak Dispatch backend."""
import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App
    app_name: str = "Sahayak Dispatch"
    debug: bool = True
    demo_mode: bool = True
    
    # Database
    database_path: str = "./data/sahayak.db"
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    # LLM
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"
    llm_timeout: float = 6.0
    llm_max_retries: int = 1
    
    # Routing
    routing_base_url: str = "http://router.project-osrm.org"
    routing_timeout: float = 2.5
    route_cache_path: str = "./data/route_cache.json"
    route_cache_ttl_seconds: int = 300
    
    # Demo
    demo_tools_enabled: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()