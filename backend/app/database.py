from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    secret_key: str = os.getenv("SECRET_KEY", "")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    chroma_db_path: str = os.getenv("CHROMA_DB_PATH", "./chroma_db")

settings = Settings()

if not settings.secret_key:
    raise ValueError("SECRET_KEY not set in .env")
if not settings.groq_api_key:
    raise ValueError("GROQ_API_KEY not set in .env")
if not settings.database_url:
    raise ValueError("DATABASE_URL not set in .env")

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


def test_connection():
    try:
        with engine.connect() as connection:
            print("Database connection successful")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False