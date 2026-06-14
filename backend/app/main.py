import json
import os
import shutil
from typing import List, Optional
from datetime import timedelta

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import SessionLocal, init_db, test_connection, get_db, settings
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.rag_service import (
    delete_document,
    get_user_documents,
    migrate_documents_to_hybrid,
    process_pdf,
    query_document,
    query_document_stream,
)
from app.models import Conversation, Document, Message, User

app = FastAPI(
    title="PDF RAG API",
    description="Upload PDFs and query them with AI",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://document-intelligence-system-ten.vercel.app",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Pydantic models ────────────────────────────────────────────────────────────

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


class CitationItem(BaseModel):
    page_number: Optional[int] = None
    filename: str
    text_snippet: str


class QueryResponse(BaseModel):
    answer: str
    source: str
    chunks_used: int
    best_distance: Optional[float] = None
    citations: List[CitationItem] = []


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    page_count: int
    chunk_count: int
    upload_date: str
    pdf_url: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationRequest(BaseModel):
    document_id: int


class ConversationQueryRequest(BaseModel):
    document_id: int
    question: str
    conversation_id: Optional[int] = None


class StreamQueryRequest(BaseModel):
    document_id: int
    question: str
    conversation_id: Optional[int] = None


class ConversationResponse(BaseModel):
    id: int
    document_id: int
    title: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    print("Starting PDF RAG API...")
    if test_connection():
        print("Database connected")
    else:
        print("Database connection failed")
        return
    init_db()
    print("Tables ready")


# ── Health / root ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "Welcome to PDF RAG API", "docs": "/docs", "health": "/health"}


@app.head("/health")
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "PDF RAG API is running"}


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
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


# ── Documents ──────────────────────────────────────────────────────────────────

@app.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are allowed")

    permanent_filename = f"user_{current_user.id}_{file.filename}"
    permanent_file_path = os.path.join(UPLOAD_DIR, permanent_filename)

    try:
        with open(permanent_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"\nProcessing upload from user {current_user.email}")
        document = process_pdf(
            file_path=permanent_file_path,
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
            "pdf_url": document.pdf_url,
        }
    except Exception as e:
        if os.path.exists(permanent_file_path):
            os.remove(permanent_file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process PDF: {e}")


@app.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
            pdf_url=doc.pdf_url,
        )
        for doc in documents
    ]


@app.get("/documents/{document_id}/pdf")
async def serve_pdf(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    for path in [
        os.path.join(UPLOAD_DIR, f"user_{current_user.id}_{document.filename}"),
        os.path.join(UPLOAD_DIR, document.filename),
    ]:
        if os.path.exists(path):
            return FileResponse(
                path,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
            )

    if document.pdf_public_id:
        import cloudinary.utils as cld_utils
        signed_url, _ = cld_utils.cloudinary_url(
            document.pdf_public_id,
            resource_type="raw",
            sign_url=True,
        )
        async with httpx.AsyncClient() as client:
            r = await client.get(signed_url, timeout=30.0)
        if r.status_code == 200:
            return Response(
                content=r.content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
            )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not available")


@app.delete("/documents/{document_id}")
async def delete_document_endpoint(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not delete_document(document_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"message": "Document deleted successfully", "document_id": document_id}


# ── Query (legacy, no conversation) ───────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(
    query_data: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == query_data.document_id,
        Document.user_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    result = query_document(
        document_id=query_data.document_id,
        question=query_data.question,
        user_id=current_user.id,
    )
    return QueryResponse(
        answer=result["answer"],
        source=result["source"],
        chunks_used=result["chunks_used"],
        best_distance=result.get("best_distance"),
        citations=[CitationItem(**c) for c in result.get("citations", [])],
    )


# ── Conversations ──────────────────────────────────────────────────────────────

@app.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == data.document_id,
        Document.user_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    conv = Conversation(
        user_id=current_user.id,
        document_id=data.document_id,
        title=None,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationResponse(
        id=conv.id,
        document_id=conv.document_id,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
    )


@app.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    document_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    if document_id:
        query = query.filter(Conversation.document_id == document_id)
    convs = query.order_by(Conversation.created_at.desc()).all()
    return [
        ConversationResponse(
            id=c.id,
            document_id=c.document_id,
            title=c.title,
            created_at=c.created_at.isoformat(),
        )
        for c in convs
    ]


@app.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    msgs = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()
    return [
        MessageResponse(id=m.id, role=m.role, content=m.content, created_at=m.created_at.isoformat())
        for m in msgs
    ]


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted", "conversation_id": conversation_id}


# ── Query with conversation (non-streaming fallback) ──────────────────────────

@app.post("/query/conversation", response_model=QueryResponse)
async def query_conversation_endpoint(
    query_data: ConversationQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == query_data.document_id,
        Document.user_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    history = []
    conv_id = query_data.conversation_id
    if conv_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        msgs = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at).all()
        history = [{"role": m.role, "content": m.content} for m in msgs]

    result = query_document(
        document_id=query_data.document_id,
        question=query_data.question,
        user_id=current_user.id,
        conversation_history=history,
    )

    if conv_id and result.get("source") != "error":
        db.add(Message(conversation_id=conv_id, role="user", content=query_data.question))
        db.add(Message(conversation_id=conv_id, role="assistant", content=result["answer"]))
        # Auto-set title from first question
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv and not conv.title:
            conv.title = query_data.question[:80]
        db.commit()

    return QueryResponse(
        answer=result["answer"],
        source=result["source"],
        chunks_used=result["chunks_used"],
        best_distance=result.get("best_distance"),
        citations=[CitationItem(**c) for c in result.get("citations", [])],
    )


# ── SSE Streaming query ────────────────────────────────────────────────────────

@app.post("/query/stream")
async def stream_query_endpoint(
    query_data: StreamQueryRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == query_data.document_id,
        Document.user_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Load conversation history before streaming begins
    history = []
    conv_id = query_data.conversation_id
    if conv_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        msgs = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at).all()
        history = [{"role": m.role, "content": m.content} for m in msgs]

    # Collect streamed tokens so we can persist after streaming completes
    collected: dict = {"answer": [], "source": "general_knowledge"}

    def event_generator():
        for event in query_document_stream(
            document_id=query_data.document_id,
            question=query_data.question,
            user_id=current_user.id,
            conversation_history=history,
        ):
            if event["event"] == "token":
                collected["answer"].append(event["data"])
            elif event["event"] == "done":
                collected["source"] = event["data"].get("source", "general_knowledge")
            yield f"data: {json.dumps({'event': event['event'], 'data': event['data']})}\n\n"

    def save_messages():
        if not conv_id:
            return
        answer_text = "".join(collected["answer"])
        if not answer_text:
            return
        new_db = SessionLocal()
        try:
            new_db.add(Message(conversation_id=conv_id, role="user", content=query_data.question))
            new_db.add(Message(conversation_id=conv_id, role="assistant", content=answer_text))
            # Auto-set conversation title from first question
            conv = new_db.query(Conversation).filter(Conversation.id == conv_id).first()
            if conv and not conv.title:
                conv.title = query_data.question[:80]
            new_db.commit()
        except Exception as e:
            print(f"Failed to save messages: {e}")
            new_db.rollback()
        finally:
            new_db.close()

    background_tasks.add_task(save_messages)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Admin: hybrid search migration ────────────────────────────────────────────

@app.post("/admin/migrate-to-hybrid")
async def migrate_to_hybrid(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Re-index all documents into the hybrid (BM25 + dense) collection.
    Runs as a background task; returns immediately with a job-started message.
    Only the document owner's files are migrated in the background.
    """
    def run_migration():
        new_db = SessionLocal()
        try:
            result = migrate_documents_to_hybrid(new_db)
            print(f"Migration finished: {result}")
        except Exception as e:
            print(f"Migration error: {e}")
        finally:
            new_db.close()

    background_tasks.add_task(run_migration)
    return {"message": "Hybrid migration started in background. Check server logs for progress."}


# ── Metrics ────────────────────────────────────────────────────────────────────

class MetricsResponse(BaseModel):
    total_queries: int
    avg_retrieval_latency_ms: float
    avg_llm_latency_ms: float
    avg_total_latency_ms: float
    avg_faithfulness_score: Optional[float] = None
    avg_retrieval_score: Optional[float] = None
    source_distribution: dict


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    document_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import QueryEvaluation

    query = db.query(QueryEvaluation).filter(QueryEvaluation.user_id == current_user.id)
    if document_id:
        query = query.filter(QueryEvaluation.document_id == document_id)

    evals = query.all()

    if not evals:
        return MetricsResponse(
            total_queries=0,
            avg_retrieval_latency_ms=0.0,
            avg_llm_latency_ms=0.0,
            avg_total_latency_ms=0.0,
            avg_faithfulness_score=None,
            avg_retrieval_score=None,
            source_distribution={},
        )

    def safe_avg(values):
        filtered = [v for v in values if v is not None]
        return sum(filtered) / len(filtered) if filtered else None

    retrieval_latencies = [e.retrieval_latency_ms for e in evals]
    llm_latencies = [e.llm_latency_ms for e in evals]
    total_latencies = [e.total_latency_ms for e in evals]
    faithfulness_scores = [e.faithfulness_score for e in evals]
    retrieval_scores = [e.retrieval_score for e in evals]

    source_dist: dict = {}
    for e in evals:
        src = e.source or "unknown"
        source_dist[src] = source_dist.get(src, 0) + 1

    return MetricsResponse(
        total_queries=len(evals),
        avg_retrieval_latency_ms=safe_avg(retrieval_latencies) or 0.0,
        avg_llm_latency_ms=safe_avg(llm_latencies) or 0.0,
        avg_total_latency_ms=safe_avg(total_latencies) or 0.0,
        avg_faithfulness_score=safe_avg(faithfulness_scores),
        avg_retrieval_score=safe_avg(retrieval_scores),
        source_distribution=source_dist,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
