import os
import shutil
from typing import List
from datetime import timedelta

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Body, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import init_db, test_connection, get_db, settings
from app import models
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.rag_service import (
    process_pdf,
    query_document,
    delete_document,
    get_user_documents,
)
from app.models import User, Document

app = FastAPI(
    title="PDF RAG API",
    description="Upload PDFs and query them with AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class QueryRequest(BaseModel):
    document_id: int
    question: str


class QueryResponse(BaseModel):
    answer: str
    source: str
    chunks_used: int
    best_distance: float | None


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    page_count: int
    chunk_count: int
    upload_date: str

    class Config:
        from_attributes = True


@app.on_event("startup")
async def startup_event():
    print("Starting PDF RAG API...")

    if test_connection():
        print("Database connected")
    else:
        print("Database connection failed")
        return

    print(f"\nTables to create: {list(models.Base.metadata.tables.keys())}")

    init_db()
    print("Tables created successfully")


@app.get("/")
async def root():
    return {"message": "Welcome to PDF RAG API", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "PDF RAG API is running"}


@app.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    try:
        hashed_password = hash_password(user_data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    new_user = User(email=user_data.email, hashed_password=hashed_password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(
        data={"sub": str(new_user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    print(f"New user registered: {new_user.email} (ID: {new_user.id})")

    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    print(f"User logged in: {user.email}")

    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are allowed"
        )

    temp_file_path = os.path.join(UPLOAD_DIR, f"temp_{current_user.id}_{file.filename}")

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"\nProcessing upload from user {current_user.email}")

        document = process_pdf(
            file_path=temp_file_path,
            filename=file.filename,
            user_id=current_user.id,
            db=db,
        )

        return {
            "message": "PDF uploaded and processed successfully",
            "document_id": document.id,
            "filename": document.filename,
            "pages": document.page_count,
            "chunks": document.chunk_count,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PDF: {str(e)}",
        )

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    documents = get_user_documents(current_user.id, db)

    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            file_size=doc.file_size,
            page_count=doc.page_count,
            chunk_count=doc.chunk_count,
            upload_date=doc.upload_date.isoformat(),
        )
        for doc in documents
    ]


@app.delete("/documents/{document_id}")
async def delete_document_endpoint(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    success = delete_document(document_id, current_user.id, db)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission to delete it",
        )

    return {"message": "Document deleted successfully", "document_id": document_id}


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(
    query_data: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = (
        db.query(Document)
        .filter(
            Document.id == query_data.document_id, Document.user_id == current_user.id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission to query it",
        )

    result = query_document(
        document_id=query_data.document_id,
        question=query_data.question,
        user_id=current_user.id,
    )

    return QueryResponse(**result)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
