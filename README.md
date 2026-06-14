# Document Intelligence System

An AI-powered document query system that allows users to upload PDFs and ask questions about them using natural language. Built with a hybrid Retrieval-Augmented Generation (RAG) pipeline combining dense semantic search, BM25 sparse retrieval, and cross-encoder reranking.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![PostgreSQL](https://img.shields.io/badge/postgresql-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Jina AI](https://img.shields.io/badge/Jina_AI-Embeddings-brightgreen)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-blue)

## Features

- **PDF Upload**: Upload PDF documents (up to 10MB) stored durably on Cloudinary
- **Hybrid Search**: Combines dense semantic vectors (Jina embeddings) and BM25 sparse vectors with Reciprocal Rank Fusion (RRF)
- **Cross-Encoder Reranking**: Jina reranker v2 re-scores candidate chunks for higher precision
- **Multi-Turn Conversations**: Persistent conversation history with automatic query rewriting to resolve coreferences
- **Streaming Responses**: Server-Sent Events (SSE) for real-time token streaming
- **Page-Level Citations**: Answers include the source page number and a text snippet for each retrieved chunk
- **Smart Fallback**: Similarity threshold routing distinguishes document-grounded answers from general knowledge
- **User Authentication**: JWT-based authentication; users can only access their own documents
- **Evaluation Metrics**: LLM-as-judge faithfulness scoring and latency tracking per query

## Tech Stack

**Backend:**
- **FastAPI** — async web framework (Python 3.13)
- **PostgreSQL (NeonDB)** — serverless database for users, documents, conversations, and metrics
- **Qdrant** — vector database with two collections: dense-only (`pdf_documents`) and hybrid (`pdf_documents_v2`)
- **Jina AI** — embeddings (`jina-embeddings-v2-base-en`, 768-dim) and reranker (`jina-reranker-v2-base-multilingual`)
- **fastembed** — local BM25 sparse encoding (`Qdrant/bm25` model)
- **Groq API** — LLM inference (Llama 3.3-70b-versatile for answers, Llama 3.1-8b-instant for query rewriting and faithfulness scoring)
- **Cloudinary** — cloud storage for uploaded PDFs
- **PyPDF** — PDF text extraction
- **SQLAlchemy** — ORM for database operations
- **JWT** — secure authentication

**Frontend:**
- **React 18** — UI library with hooks
- **Vite** — build tool
- **Tailwind CSS** — utility-first styling
- **Axios** — HTTP client
- **React Router v6** — client-side routing

## How It Works

### RAG Pipeline

**1. Document Upload**
- User uploads a PDF (max 10MB)
- Text is extracted page-by-page using PyPDF
- Text is split into overlapping, sentence-boundary-aware chunks (800 chars, 150 char overlap)
- PDF is stored on Cloudinary for later retrieval

**2. Dual Indexing into Qdrant**
- Chunks are embedded with Jina embeddings (768-dim) and uploaded to the dense collection (`pdf_documents`)
- BM25 sparse vectors are generated locally via fastembed and uploaded alongside dense vectors to the hybrid collection (`pdf_documents_v2`), which supports both vector types natively

**3. Query Processing**
- If conversation history exists, the follow-up question is rewritten into a standalone question via LLM (Llama 3.1-8b-instant)
- The question type is classified: summary, identity, or factual — this controls retrieval depth and similarity threshold
- Dense and sparse vectors are fetched in parallel via Qdrant prefetch, then fused with RRF
- Retrieved chunks are re-ranked by a Jina cross-encoder

**4. Response Generation**
- Top-ranked chunks are assembled into a context window with page citations
- Groq streams the answer token-by-token via SSE
- The conversation turn is persisted asynchronously; faithfulness and latency metrics are saved in the background

### Hybrid Search Detail

Qdrant's `query_points` API is used with two `Prefetch` legs — one dense, one sparse — fused via `Fusion.RRF`. This collection is used when the document has been indexed in `pdf_documents_v2`; otherwise the system falls back to pure dense search on `pdf_documents`. New uploads are indexed into both collections automatically.

### Query Classification

| Question type | Chunks retrieved | Similarity threshold |
|---|---|---|
| Summary / overview | up to 10 | 2.0 (relaxed) |
| Identity ("who is X") | up to 10, name-filtered | 2.0 |
| Factual | 5 | 1.63 |

When no chunks pass the threshold, the LLM falls back to general knowledge and the response is tagged `source: general_knowledge`.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/register` | Register a new user |
| POST | `/login` | Login and receive JWT |
| POST | `/upload` | Upload a PDF |
| GET | `/documents` | List user's documents |
| DELETE | `/documents/{id}` | Delete a document |
| GET | `/documents/{id}/pdf` | Serve the PDF (local or Cloudinary) |
| POST | `/query` | One-shot query (no conversation) |
| POST | `/conversations` | Create a conversation for a document |
| GET | `/conversations` | List conversations (optionally filtered by document) |
| DELETE | `/conversations/{id}` | Delete a conversation |
| GET | `/conversations/{id}/messages` | Retrieve conversation messages |
| POST | `/query/conversation` | Query within a conversation (non-streaming) |
| POST | `/query/stream` | Query with SSE streaming |
| GET | `/metrics` | Retrieval and faithfulness metrics for the current user |
| POST | `/admin/migrate-to-hybrid` | Re-index all documents into the hybrid collection (background) |
| GET/HEAD | `/health` | Health check |

## Environment Variables

Create `backend/.env`:

```
DATABASE_URL=postgresql://...
SECRET_KEY=your-secret-key
GROQ_API_KEY=gsk_...
QDRANT_URL=https://...qdrant.io
QDRANT_API_KEY=...
JINA_API_KEY=jina_...
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...

# Optional
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
QDRANT_COLLECTION_NAME=pdf_documents
```

## Running Locally

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Use Cases

- **Research** — extract and query information from academic papers
- **Legal** — search through contracts and legal documents
- **HR** — query employee handbooks and policies
- **Education** — ask questions about textbooks and study materials
- **Personal** — organize and query personal documents (resumes, receipts, etc.)


