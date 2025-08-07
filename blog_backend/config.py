"""
Configuration management using Pydantic settings
"""
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from functools import lru_cache

class BlogSettings(BaseSettings):
    """Blog backend configuration"""
    
    # Application settings
    app_name: str = Field(default="Blog Backend API", env="APP_NAME")
    app_version: str = Field(default="2.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    
    # API settings
    api_prefix: str = Field(default="", env="API_PREFIX")
    cors_origins: List[str] = Field(default=["*"], env="CORS_ORIGINS")
    
    # Content settings
    posts_directory: Path = Field(default=Path("posts"), env="POSTS_DIRECTORY")
    max_upload_size: int = Field(default=10 * 1024 * 1024, env="MAX_UPLOAD_SIZE")  # 10MB
    allowed_extensions: List[str] = Field(
        default=[".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".webp"],
        env="ALLOWED_EXTENSIONS"
    )
    
    # Performance settings
    max_workers: int = Field(default=4, env="MAX_WORKERS")
    cache_ttl: int = Field(default=300, env="CACHE_TTL")  # 5 minutes
    stats_cache_ttl: int = Field(default=300, env="STATS_CACHE_TTL")
    
    # Search settings
    search_min_length: int = Field(default=2, env="SEARCH_MIN_LENGTH")
    search_max_results: int = Field(default=100, env="SEARCH_MAX_RESULTS")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="RATE_LIMIT_PERIOD")  # seconds
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")  # json or text
    
    # Health check
    health_check_posts_threshold: int = Field(default=0, env="HEALTH_CHECK_POSTS_THRESHOLD")
    
    # Tenant settings
    default_tenant: str = Field(default="shared", env="DEFAULT_TENANT")
    tenant_names: Dict[str, str] = Field(
        default={
            "infosec": "Information Security",
            "quant": "Quantitative Finance",
            "shared": "Shared Content"
        },
        env="TENANT_NAMES"
    )
    
    @validator("posts_directory")
    def validate_posts_directory(cls, v):
        """Ensure posts directory is absolute path"""
        if not isinstance(v, Path):
            v = Path(v)
        return v.absolute()
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()
    
    @validator("rate_limit_period")
    def validate_rate_limit_period(cls, v):
        """Ensure rate limit period is positive"""
        if v <= 0:
            raise ValueError("Rate limit period must be positive")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Allow custom types
        arbitrary_types_allowed = True
        json_encoders = {
            Path: lambda p: str(p),
        }

class DatabaseSettings(BaseSettings):
    """Optional database configuration for future enhancements"""
    
    use_database: bool = Field(default=False, env="USE_DATABASE")
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

class SecuritySettings(BaseSettings):
    """Security configuration"""
    
    # Content Security
    max_content_length: int = Field(default=1024 * 1024, env="MAX_CONTENT_LENGTH")  # 1MB
    sanitize_html: bool = Field(default=True, env="SANITIZE_HTML")
    
    # Path traversal protection
    restrict_file_access: bool = Field(default=True, env="RESTRICT_FILE_ACCESS")
    
    # Input validation
    max_query_length: int = Field(default=200, env="MAX_QUERY_LENGTH")
    max_tag_length: int = Field(default=50, env="MAX_TAG_LENGTH")
    max_tags_per_post: int = Field(default=10, env="MAX_TAGS_PER_POST")
    
    # API Security
    require_api_key: bool = Field(default=False, env="REQUIRE_API_KEY")
    api_key_header: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    valid_api_keys: List[str] = Field(default=[], env="VALID_API_KEYS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> BlogSettings:
    """Get cached settings instance"""
    return BlogSettings()

@lru_cache()
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings"""
    return DatabaseSettings()

@lru_cache()
def get_security_settings() -> SecuritySettings:
    """Get cached security settings"""
    return SecuritySettings()

# Convenience function to reload settings (useful for testing)
def reload_settings():
    """Clear settings cache to reload from environment"""
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    get_security_settings.cache_clear()