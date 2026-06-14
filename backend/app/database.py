from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    secret_key: str = os.getenv("SECRET_KEY", "")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")


settings = Settings()

if not settings.secret_key:
    raise ValueError("SECRET_KEY not set in .env")
if not settings.groq_api_key:
    raise ValueError("GROQ_API_KEY not set in .env")
if not settings.database_url:
    raise ValueError("DATABASE_URL not set in .env")
if not settings.qdrant_url:
    raise ValueError("QDRANT_URL not set in .env")
if not settings.qdrant_api_key:
    raise ValueError("QDRANT_API_KEY not set in .env")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
    _migrate_columns()


def _migrate_columns():
    """Add new columns/tables to existing schema without alembic."""
    migrations = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pdf_url TEXT",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pdf_public_id TEXT",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS has_page_numbers BOOLEAN NOT NULL DEFAULT FALSE",
        # conversations and messages tables are handled by create_all()
        # query_evaluations is also handled by create_all(), but keep an explicit guard
        """
        CREATE TABLE IF NOT EXISTS query_evaluations (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source VARCHAR(30),
            chunks_retrieved INTEGER,
            retrieval_score FLOAT,
            reranker_top_score FLOAT,
            faithfulness_score FLOAT,
            faithfulness_label VARCHAR(20),
            retrieval_latency_ms INTEGER,
            llm_latency_ms INTEGER,
            total_latency_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt.strip()))
            except Exception as e:
                print(f"Migration skipped: {e}")
        conn.commit()
    print("Column migrations applied")


def test_connection():
    try:
        with engine.connect() as connection:
            print("Database connection successful")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
