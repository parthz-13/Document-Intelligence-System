from typing import List, Dict, Any, Generator, Optional
import os
import re
import sys
import time
import uuid

import cloudinary
import cloudinary.uploader
import httpx
from fastembed import SparseTextEmbedding
from groq import Groq
from pypdf import PdfReader
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType,
    SparseVectorParams, SparseIndexParams, SparseVector,
    Prefetch, FusionQuery, Fusion,
)

from app.database import SessionLocal, settings
from app.models import Document


# ── Constants ──────────────────────────────────────────────────────────────────

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_RERANKER_URL = "https://api.jina.ai/v1/rerank"
JINA_API_KEY = os.getenv("JINA_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "pdf_documents")
HYBRID_COLLECTION = "pdf_documents_v2"

# BM25 sparse encoder (downloads ~5 MB model on first use, then cached)
print("Loading BM25 sparse encoder...")
_bm25_encoder = SparseTextEmbedding(model_name="Qdrant/bm25")
print("BM25 encoder ready")


# ── Cloudinary ─────────────────────────────────────────────────────────────────

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


def upload_to_cloudinary(file_path: str, filename: str, user_id: int) -> tuple[Optional[str], Optional[str]]:
    """Upload PDF to Cloudinary, return (secure_url, public_id) or (None, None) on failure."""
    try:
        stem = os.path.splitext(filename)[0]
        result = cloudinary.uploader.upload(
            file_path,
            resource_type="raw",
            folder=f"doc-intelligence/{user_id}",
            public_id=f"{user_id}_{stem}.pdf",
            overwrite=True,
        )
        return result["secure_url"], result["public_id"]
    except Exception as e:
        print(f"Cloudinary upload failed: {e}")
        return None, None


# ── Qdrant ─────────────────────────────────────────────────────────────────────

qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)


def initialize_qdrant():
    try:
        qdrant_client.get_collection(COLLECTION_NAME)
        print(f"Collection '{COLLECTION_NAME}' exists")
        for field_name in ["doc_id", "user_id"]:
            try:
                qdrant_client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass
    except Exception:
        print(f"Creating collection '{COLLECTION_NAME}'...")
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        for field_name in ["doc_id", "user_id"]:
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        print("Created collection with 768-dim vectors")


initialize_qdrant()


def initialize_hybrid_collection():
    """Create pdf_documents_v2 with dense + sparse vector configs if it doesn't exist."""
    try:
        qdrant_client.get_collection(HYBRID_COLLECTION)
        print(f"Hybrid collection '{HYBRID_COLLECTION}' exists")
    except Exception:
        print(f"Creating hybrid collection '{HYBRID_COLLECTION}'...")
        qdrant_client.create_collection(
            collection_name=HYBRID_COLLECTION,
            vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
            },
        )
        for field_name in ["doc_id", "user_id"]:
            qdrant_client.create_payload_index(
                collection_name=HYBRID_COLLECTION,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        print(f"Hybrid collection '{HYBRID_COLLECTION}' created")


initialize_hybrid_collection()


def generate_sparse_vector(text: str) -> SparseVector:
    """BM25 sparse encoding via fastembed (runs locally, no API call)."""
    result = list(_bm25_encoder.embed([text]))[0]
    return SparseVector(
        indices=result.indices.tolist(),
        values=result.values.tolist(),
    )


groq_client = Groq(api_key=settings.groq_api_key)


# ── Embeddings ─────────────────────────────────────────────────────────────────

def generate_embeddings_batch(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """Batch embed texts via Jina API. Returns embeddings in the same order as input."""
    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            response = httpx.post(
                JINA_API_URL,
                headers={
                    "Authorization": f"Bearer {JINA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"input": batch, "model": "jina-embeddings-v2-base-en"},
                timeout=60.0,
            )
            response.raise_for_status()
            items = sorted(response.json()["data"], key=lambda x: x["index"])
            all_embeddings.extend(item["embedding"] for item in items)
        except Exception as e:
            raise Exception(f"Embedding batch {i // batch_size} failed: {e}")
    return all_embeddings


def generate_embedding(text: str) -> List[float]:
    return generate_embeddings_batch([text])[0]


# ── Reranker ───────────────────────────────────────────────────────────────────

def rerank_chunks(query: str, chunks: List[Dict], top_n: int = 5) -> List[Dict]:
    """Re-rank chunks with Jina cross-encoder. Falls back to original order on failure."""
    if not chunks:
        return chunks
    try:
        response = httpx.post(
            JINA_RERANKER_URL,
            headers={
                "Authorization": f"Bearer {JINA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "jina-reranker-v2-base-multilingual",
                "query": query,
                "documents": [c["text"] for c in chunks],
                "top_n": min(top_n, len(chunks)),
            },
            timeout=15.0,
        )
        response.raise_for_status()
        results = sorted(response.json()["results"], key=lambda r: r["relevance_score"], reverse=True)
        return [chunks[r["index"]] for r in results]
    except Exception as e:
        print(f"Reranker failed, using original order: {e}")
        return chunks[:top_n]


# ── Chunking ───────────────────────────────────────────────────────────────────

def extract_pages_from_pdf(file_path: str) -> tuple:
    """Returns (total_page_count, [(page_num, page_text), ...]) for non-empty pages."""
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append((page_num, page_text))
        if not pages:
            raise ValueError("No text could be extracted from the PDF")
        return total_pages, pages
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {e}")


def chunk_document(pages: List[tuple], chunk_size: int = 800, overlap: int = 150) -> List[Dict]:
    """
    Sentence-boundary-aware chunker that tracks the page number for each chunk.
    Returns list of {"text", "page_number", "chunk_index"} dicts.
    """
    # Build flat (text, page_num) representation
    full_text = ""
    page_at_pos: List[int] = []
    for page_num, page_text in pages:
        start = len(full_text)
        full_text += page_text
        page_at_pos.extend([page_num] * (len(full_text) - start))

    total = len(full_text)
    chunks: List[Dict] = []
    start = 0
    chunk_index = 0

    while start < total:
        end = min(start + chunk_size, total)

        # Scan back for a sentence boundary so we don't cut mid-word/sentence
        if end < total:
            search_from = max(start, end - 200)
            best_break = -1
            for i in range(end - 1, search_from - 1, -1):
                ch = full_text[i]
                next_ch = full_text[i + 1] if i + 1 < total else ""
                if ch in ".!?" and next_ch in (" ", "\n"):
                    best_break = i + 2
                    break
                if ch == "\n" and next_ch == "\n":
                    best_break = i + 2
                    break
            if best_break > start:
                end = best_break

        chunk_text = full_text[start:end].strip()
        chunk_page = page_at_pos[start] if start < len(page_at_pos) else pages[0][0]

        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "page_number": chunk_page,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks


# ── Process PDF ────────────────────────────────────────────────────────────────

def process_pdf(file_path: str, filename: str, user_id: int, db: Session) -> Document:
    print(f"\nProcessing PDF: {filename}")

    total_pages, pages = extract_pages_from_pdf(file_path)
    file_size = os.path.getsize(file_path)
    print(f"Extracted text from {len(pages)} of {total_pages} pages")

    chunk_dicts = chunk_document(pages, chunk_size=800, overlap=150)
    print(f"Created {len(chunk_dicts)} chunks")

    document = Document(
        user_id=user_id,
        filename=filename,
        original_filename=filename,
        file_size=file_size,
        page_count=total_pages,
        chunk_count=len(chunk_dicts),
        has_page_numbers=True,
    )
    db.add(document)
    db.flush()
    doc_id = str(document.id)
    print(f"Created document record (ID: {doc_id})")

    texts = [c["text"] for c in chunk_dicts]
    print(f"Generating {len(texts)} embeddings (batched)...")
    embeddings = generate_embeddings_batch(texts)

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "doc_id": doc_id,
                "user_id": str(user_id),
                "chunk_index": c["chunk_index"],
                "page_number": c["page_number"],
                "filename": filename,
                "text": c["text"],
            },
        )
        for c, embedding in zip(chunk_dicts, embeddings)
    ]

    try:
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Uploaded {len(points)} chunks to Qdrant (dense)")
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Qdrant indexing failed: {e}")

    # Also index into hybrid collection with sparse vectors
    try:
        print("Generating sparse (BM25) vectors and indexing into hybrid collection...")
        hybrid_points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": embedding,
                    "sparse": generate_sparse_vector(c["text"]),
                },
                payload={
                    "doc_id": doc_id,
                    "user_id": str(user_id),
                    "chunk_index": c["chunk_index"],
                    "page_number": c["page_number"],
                    "filename": filename,
                    "text": c["text"],
                },
            )
            for c, embedding in zip(chunk_dicts, embeddings)
        ]
        qdrant_client.upsert(collection_name=HYBRID_COLLECTION, points=hybrid_points)
        print(f"Uploaded {len(hybrid_points)} chunks to hybrid collection")
    except Exception as e:
        print(f"Hybrid indexing failed (non-fatal): {e}")

    print("Uploading to Cloudinary...")
    pdf_url, pdf_public_id = upload_to_cloudinary(file_path, filename, user_id)
    document.pdf_url = pdf_url
    document.pdf_public_id = pdf_public_id
    if pdf_url:
        print(f"Cloudinary URL: {pdf_url} (public_id: {pdf_public_id})")
    else:
        print("Cloudinary upload skipped (credentials missing or error)")

    db.commit()
    db.refresh(document)
    print(f"PDF processed successfully: {filename} ({len(chunk_dicts)} chunks, {total_pages} pages)\n")
    return document


# ── Query helpers ──────────────────────────────────────────────────────────────

def _classify_question(question: str, total_chunks: int) -> tuple:
    """Returns (is_summary, is_identity, n_results, similarity_threshold)."""
    summary_keywords = [
        "summary", "summarize", "summarise", "overview", "about",
        "what is this", "what's this", "tell me about", "main points",
        "key points", "gist", "brief", "describe this", "content",
    ]
    identity_keywords = [
        "who is", "who's", "tell me about", "information about",
        "details about", "background of", "describe",
    ]
    q = question.lower()
    is_summary = any(kw in q for kw in summary_keywords)
    is_identity = any(kw in q for kw in identity_keywords)
    if is_summary or is_identity:
        return is_summary, is_identity, min(10, total_chunks), 2.0
    return False, False, 5, 1.63


def _build_prompt(question: str, context: str, is_summary: bool, is_identity: bool) -> tuple:
    """Returns (system_prompt, user_prompt) for the LLM call."""
    if is_summary:
        return (
            "You are a document summarization assistant. Provide a concise summary highlighting the main points in 3-5 sentences. DO NOT make up information not present in the text.",
            f"DOCUMENT CONTENT:\n{context}\n\nUSER QUESTION: {question}\n\nProvide a clear summary.",
        )
    if is_identity:
        return (
            "You are a helpful assistant answering questions about people mentioned in documents. Answer based ONLY on the document content. Do NOT invent biographical information.",
            f"DOCUMENT CONTENT:\n{context}\n\nQUESTION: {question}\n\nAnswer based only on what's mentioned in the document.",
        )
    return (
        'You are a PDF document assistant. Answer questions based ONLY on the provided context.\nRULES:\n- Use ONLY information from the CONTEXT below\n- If the answer isn\'t in the context, say "I cannot find this information in the document"\n- Be concise and direct\n- Quote relevant parts when helpful',
        f"CONTEXT FROM DOCUMENT:\n{context}\n\nQUESTION: {question}\n\nAnswer based only on the context above.",
    )


def _extract_name(question: str) -> Optional[str]:
    patterns = [
        r"who (?:is|'s) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"about ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"tell me about ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return match.group(1)
    return None


def _filter_chunks(
    candidate_chunks: List[Dict],
    is_summary: bool,
    is_identity: bool,
    effective_question: str,
    similarity_threshold: float,
) -> List[Dict]:
    if is_summary:
        return candidate_chunks[:10]
    if is_identity:
        name = _extract_name(effective_question)
        if name:
            name_chunks = [c for c in candidate_chunks if name.lower() in c["text"].lower()]
            return name_chunks if name_chunks else []
    return [c for c in candidate_chunks if c["distance"] < similarity_threshold]


def _search_qdrant_with_query(doc_id: str, query_text: str, embedding: List[float], n_results: int) -> List[Dict]:
    """Full hybrid search using both dense and sparse (BM25) vectors with RRF fusion."""
    doc_filter = {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}

    try:
        count_in_v2 = qdrant_client.count(
            collection_name=HYBRID_COLLECTION,
            count_filter=doc_filter,
        ).count
    except Exception:
        count_in_v2 = 0

    if count_in_v2 > 0:
        try:
            sparse_vec = generate_sparse_vector(query_text)
            results = qdrant_client.query_points(
                collection_name=HYBRID_COLLECTION,
                prefetch=[
                    Prefetch(query=embedding, using="dense", limit=n_results * 3, filter=doc_filter),
                    Prefetch(query=sparse_vec, using="sparse", limit=n_results * 3, filter=doc_filter),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=n_results,
                with_payload=True,
                with_vectors=False,
            )
            hits = results.points
            print(f"Hybrid RRF search returned {len(hits)} results")
        except Exception as e:
            print(f"Hybrid search failed, falling back to dense: {e}")
            hits = _dense_search(COLLECTION_NAME, embedding, doc_filter, n_results)
    else:
        hits = _dense_search(COLLECTION_NAME, embedding, doc_filter, n_results)

    return [
        {
            "text": hit.payload["text"],
            "page_number": hit.payload.get("page_number"),
            "filename": hit.payload.get("filename", ""),
            "score": hit.score,
            "distance": 1 - hit.score,
        }
        for hit in hits
    ]


def _dense_search(collection: str, embedding: List[float], doc_filter: dict, n_results: int):
    results = qdrant_client.query_points(
        collection_name=collection,
        query=embedding,
        query_filter=doc_filter,
        limit=n_results,
        with_payload=True,
        with_vectors=False,
    )
    return results.points


# ── Query rewriting ────────────────────────────────────────────────────────────

def rewrite_query(original_question: str, conversation_history: List[Dict]) -> str:
    """Resolve coreferences using conversation history to produce a standalone question."""
    if not conversation_history:
        return original_question
    try:
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in conversation_history[-6:]
        )
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a query rewriting assistant. Rewrite the follow-up question as a complete standalone question that resolves all pronouns and references to the conversation. Output ONLY the rewritten question, nothing else.",
                },
                {
                    "role": "user",
                    "content": f"Conversation:\n{history_text}\n\nFollow-up: {original_question}\n\nRewrite as standalone question:",
                },
            ],
            temperature=0.0,
            max_tokens=150,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return original_question


# ── Main query function ────────────────────────────────────────────────────────

def query_document(
    document_id: int,
    question: str,
    user_id: int,
    conversation_history: Optional[List[Dict]] = None,
    n_results: int = 5,
) -> Dict[str, Any]:
    print(f"Query — doc:{document_id} q:{question[:60]}")
    doc_id = str(document_id)
    history = conversation_history or []

    effective_question = rewrite_query(question, history)
    if effective_question != question:
        print(f"Rewritten query: {effective_question}")

    # Verify document has chunks
    try:
        total_chunks = qdrant_client.count(
            collection_name=COLLECTION_NAME,
            count_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
        ).count
        if total_chunks == 0:
            return {"answer": "This document has no content. Please re-upload it.", "source": "error", "chunks_used": 0, "best_distance": None, "citations": []}
    except Exception:
        return {"answer": "Failed to access document storage. Please try again.", "source": "error", "chunks_used": 0, "best_distance": None, "citations": []}

    is_summary, is_identity, n_results, threshold = _classify_question(effective_question, total_chunks)

    t_retrieval = time.perf_counter()
    try:
        embedding = generate_embedding(effective_question)
        candidate_chunks = _search_qdrant_with_query(doc_id, effective_question, embedding, n_results)
    except Exception:
        return {"answer": "Search failed. Please try again.", "source": "error", "chunks_used": 0, "best_distance": None, "citations": []}
    retrieval_ms = int((time.perf_counter() - t_retrieval) * 1000)

    filtered = _filter_chunks(candidate_chunks, is_summary, is_identity, effective_question, threshold)

    if not filtered:
        system_prompt = "You are a helpful AI assistant. The user asked about their document, but no relevant information was found. Acknowledge this briefly and provide helpful general knowledge if applicable."
        user_prompt = f"Question: {question}\n\nThis information wasn't found in the user's document. Provide a helpful response."
        t_llm = time.perf_counter()
        try:
            msgs = [{"role": "system", "content": system_prompt}]
            msgs += [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
            msgs.append({"role": "user", "content": user_prompt})
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=msgs, temperature=0.0, max_tokens=500,
            )
            answer = completion.choices[0].message.content
        except Exception:
            answer = "Failed to generate response."
        return {
            "answer": answer,
            "source": "general_knowledge",
            "chunks_used": 0,
            "best_distance": None,
            "citations": [],
            "retrieval_latency_ms": retrieval_ms,
            "llm_latency_ms": int((time.perf_counter() - t_llm) * 1000),
        }

    reranked = rerank_chunks(effective_question, filtered, top_n=5)
    best_distance = min(c["distance"] for c in reranked)
    context = "\n\n---\n\n".join(c["text"] for c in reranked)
    system_prompt, user_prompt = _build_prompt(effective_question, context, is_summary, is_identity)

    citations = [
        {
            "page_number": c.get("page_number"),
            "filename": c.get("filename", ""),
            "text_snippet": c["text"][:150],
        }
        for c in reranked
    ]

    t_llm = time.perf_counter()
    try:
        msgs = [{"role": "system", "content": system_prompt}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        msgs.append({"role": "user", "content": user_prompt})
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=msgs,
            temperature=0.0,
            max_tokens=800 if is_summary else 500,
        )
        answer = completion.choices[0].message.content
        llm_ms = int((time.perf_counter() - t_llm) * 1000)
    except Exception as e:
        return {"answer": "Failed to generate response.", "source": "error", "chunks_used": 0, "best_distance": None, "citations": []}

    print(f"Done — chunks:{len(reranked)} retrieval:{retrieval_ms}ms llm:{llm_ms}ms")

    # Persist evaluation metrics asynchronously (doesn't block the response)
    import threading
    threading.Thread(
        target=save_query_evaluation,
        args=(
            document_id, user_id, "document", len(reranked),
            reranked[0]["score"] if reranked else None,
            retrieval_ms, llm_ms, answer, question,
            [c["text"] for c in reranked],
        ),
        daemon=True,
    ).start()

    return {
        "answer": answer,
        "source": "document",
        "chunks_used": len(reranked),
        "best_distance": best_distance,
        "citations": citations,
        "retrieval_latency_ms": retrieval_ms,
        "llm_latency_ms": llm_ms,
    }


# ── Streaming query ────────────────────────────────────────────────────────────

def query_document_stream(
    document_id: int,
    question: str,
    user_id: int,
    conversation_history: Optional[List[Dict]] = None,
) -> Generator[Dict, None, None]:
    """
    Yields SSE event dicts:
      {"event": "citations", "data": [...]}
      {"event": "token",     "data": str}
      {"event": "done",      "data": {"source": str, "chunks_used": int}}
      {"event": "error",     "data": str}
    """
    doc_id = str(document_id)
    history = conversation_history or []
    effective_question = rewrite_query(question, history)

    try:
        total_chunks = qdrant_client.count(
            collection_name=COLLECTION_NAME,
            count_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
        ).count
        if total_chunks == 0:
            yield {"event": "error", "data": "Document has no content. Please re-upload it."}
            return
    except Exception:
        yield {"event": "error", "data": "Failed to access document storage."}
        return

    is_summary, is_identity, n_results, threshold = _classify_question(effective_question, total_chunks)

    try:
        embedding = generate_embedding(effective_question)
        candidate_chunks = _search_qdrant_with_query(doc_id, effective_question, embedding, n_results)
    except Exception:
        yield {"event": "error", "data": "Search failed."}
        return

    filtered = _filter_chunks(candidate_chunks, is_summary, is_identity, effective_question, threshold)

    if not filtered:
        system_prompt = "You are a helpful AI assistant. Acknowledge the information wasn't in the document and provide helpful general knowledge."
        user_prompt = f"Question: {question}\n\nThis wasn't found in the document. Be helpful."
        source = "general_knowledge"
        chunks_used = 0
    else:
        reranked = rerank_chunks(effective_question, filtered, top_n=5)
        citations = [
            {
                "page_number": c.get("page_number"),
                "filename": c.get("filename", ""),
                "text_snippet": c["text"][:150],
            }
            for c in reranked
        ]
        yield {"event": "citations", "data": citations}
        context = "\n\n---\n\n".join(c["text"] for c in reranked)
        system_prompt, user_prompt = _build_prompt(effective_question, context, is_summary, is_identity)
        source = "document"
        chunks_used = len(reranked)

    try:
        msgs = [{"role": "system", "content": system_prompt}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        msgs.append({"role": "user", "content": user_prompt})

        stream = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=msgs,
            temperature=0.0,
            max_tokens=800 if is_summary else 500,
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                yield {"event": "token", "data": token}
    except Exception as e:
        yield {"event": "error", "data": f"LLM error: {e}"}
        return

    yield {"event": "done", "data": {"source": source, "chunks_used": chunks_used}}


# ── Evaluation ─────────────────────────────────────────────────────────────────

def compute_faithfulness(question: str, answer: str, context_chunks: List[str]) -> tuple:
    """
    LLM-as-judge faithfulness scoring (non-blocking; call in background thread).
    Returns (score: float 0-1 | None, label: str).
    """
    if not context_chunks:
        return None, "unknown"
    context_text = "\n\n---\n\n".join(context_chunks[:3])  # limit context size
    prompt = f"""Given the context and a question, evaluate if the answer is faithful to the context.

CONTEXT:
{context_text}

QUESTION: {question}

ANSWER: {answer}

Rate faithfulness 0–1:
- 1.0: All claims directly supported by context
- 0.5: Mostly supported with minor additions
- 0.0: Contains significant information not in context

Respond with ONLY valid JSON: {{"score": <float>, "label": "faithful|hallucinated|unknown"}}"""

    try:
        import json
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=60,
        )
        raw = completion.choices[0].message.content.strip()
        # Extract JSON even if the model wraps it in markdown
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        result = json.loads(raw)
        return float(result.get("score", 0.5)), str(result.get("label", "unknown"))
    except Exception as e:
        print(f"Faithfulness scoring failed: {e}")
        return None, "unknown"


def save_query_evaluation(
    document_id: int,
    user_id: int,
    source: str,
    chunks_retrieved: int,
    retrieval_score: Optional[float],
    retrieval_latency_ms: int,
    llm_latency_ms: int,
    answer: str,
    question: str,
    context_chunks: List[str],
) -> None:
    """Persist a QueryEvaluation row. Runs in a background thread — opens its own DB session."""
    from app.models import QueryEvaluation
    faithfulness_score, faithfulness_label = compute_faithfulness(question, answer, context_chunks)
    db = SessionLocal()
    try:
        db.add(
            QueryEvaluation(
                document_id=document_id,
                user_id=user_id,
                source=source,
                chunks_retrieved=chunks_retrieved,
                retrieval_score=retrieval_score,
                faithfulness_score=faithfulness_score,
                faithfulness_label=faithfulness_label,
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=llm_latency_ms,
                total_latency_ms=retrieval_latency_ms + llm_latency_ms,
            )
        )
        db.commit()
    except Exception as e:
        print(f"Failed to save query evaluation: {e}")
        db.rollback()
    finally:
        db.close()


# ── Migration ──────────────────────────────────────────────────────────────────

def migrate_documents_to_hybrid(db: Session) -> Dict[str, Any]:
    """
    Re-index all documents from the legacy dense collection into the hybrid
    (BM25 + dense) collection. Idempotent — already-indexed chunks are skipped
    because we check count before processing each document.
    """
    documents = get_user_documents_all(db)
    total = len(documents)
    migrated = 0
    skipped = 0
    failed = 0

    print(f"\nStarting hybrid migration for {total} documents...")

    for doc in documents:
        doc_id = str(doc.id)
        doc_filter = {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}

        # Skip if already in hybrid collection
        try:
            count_in_v2 = qdrant_client.count(
                collection_name=HYBRID_COLLECTION,
                count_filter=doc_filter,
            ).count
            if count_in_v2 > 0:
                skipped += 1
                continue
        except Exception:
            pass

        # Locate the PDF on disk
        upload_dir = "uploads"
        file_path = os.path.join(upload_dir, f"user_{doc.user_id}_{doc.filename}")
        if not os.path.exists(file_path):
            file_path = os.path.join(upload_dir, doc.filename)
        if not os.path.exists(file_path):
            print(f"File not found for document {doc.id}: {doc.filename}")
            failed += 1
            continue

        try:
            _, pages = extract_pages_from_pdf(file_path)
            chunk_dicts = chunk_document(pages, chunk_size=800, overlap=150)
            texts = [c["text"] for c in chunk_dicts]
            embeddings = generate_embeddings_batch(texts)

            hybrid_points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": emb,
                        "sparse": generate_sparse_vector(c["text"]),
                    },
                    payload={
                        "doc_id": doc_id,
                        "user_id": str(doc.user_id),
                        "chunk_index": c["chunk_index"],
                        "page_number": c.get("page_number"),
                        "filename": doc.filename,
                        "text": c["text"],
                    },
                )
                for c, emb in zip(chunk_dicts, embeddings)
            ]
            qdrant_client.upsert(collection_name=HYBRID_COLLECTION, points=hybrid_points)
            migrated += 1
            print(f"Migrated document {doc.id} ({doc.filename}): {len(hybrid_points)} chunks")
        except Exception as e:
            print(f"Failed to migrate document {doc.id}: {e}")
            failed += 1

    result = {"total": total, "migrated": migrated, "skipped": skipped, "failed": failed}
    print(f"Migration complete: {result}")
    return result


def get_user_documents_all(db: Session) -> List[Document]:
    """Return all documents across all users (for migration use only)."""
    return db.query(Document).all()


# ── Delete / list ──────────────────────────────────────────────────────────────

def delete_document(document_id: int, user_id: int, db: Session) -> bool:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )
    if not document:
        return False

    try:
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector={
                "filter": {"must": [{"key": "doc_id", "match": {"value": str(document_id)}}]}
            },
        )
        for path in [
            os.path.join("uploads", f"user_{user_id}_{document.filename}"),
            os.path.join("uploads", document.filename),
        ]:
            if os.path.exists(path):
                os.remove(path)
                break
    except Exception as e:
        print(f"Warning: cleanup failed: {e}")

    db.delete(document)
    db.commit()
    return True


def get_user_documents(user_id: int, db: Session) -> List[Document]:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.upload_date.desc())
        .all()
    )
