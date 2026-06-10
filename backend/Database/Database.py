from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Database URL ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./retailpulse.db"
)

# ── Engine ────────────────────────────────────────────────────────────────────
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        echo=True,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=True,          # Set False in production (stops SQL logs)
        pool_pre_ping=True  # Checks connection health before using it
    )

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ── Base class for all models ─────────────────────────────────────────────────
Base = declarative_base()


# ── Dependency: get DB session, auto-close when done ─────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
