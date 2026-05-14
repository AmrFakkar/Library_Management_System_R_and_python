"""
app/core/config.py  — Task 2 additions
=======================================
Add these new settings to the existing Settings class in Task 1's config.py.
They extend JWT configuration with refresh token support.
"""

# ADD these fields inside the Settings class in app/core/config.py:

"""
    # Refresh Token (Task 2 addition)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Password reset (optional extension)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
"""

# ─── Full standalone config for reference ─────────────────────────────────────
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Library Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Security — JWT
    SECRET_KEY: str = "your-super-secret-key-change-in-production-minimum-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7           # ← Task 2 addition
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15  # ← Task 2 addition

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/library_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 300

    # Borrowing rules
    MAX_BORROWED_BOOKS: int = 5
    MAX_BORROW_DAYS: int = 14

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
