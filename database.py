from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.logger import logger

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # Verify connections before use
    pool_size=10,             # Number of connections in pool
    max_overflow=20,          # Extra connections beyond pool_size
    pool_timeout=30,          # Seconds to wait for a connection
    pool_recycle=1800,        # Recycle connections after 30 minutes
    echo=settings.DEBUG,      # Log SQL queries in debug mode
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models
Base = declarative_base()


def get_db():
    """
    Dependency that provides a database session.
    Automatically closes the session when done.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize the database, creating all tables."""
    try:
        # Import all models so they are registered with Base
        from app.models import user, book, borrow_record  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def check_db_connection() -> bool:
    """Check if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
