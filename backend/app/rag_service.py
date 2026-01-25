from typing import List, Dict, Any
import os
from pypdf import PdfReader
import chromadb
from groq import Groq
from sqlalchemy.orm import Session
import sys
from app.database import settings
from app.models import Document

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

chroma_client = chromadb.PersistentClient(path=settings.chroma_db_path)
collection = chroma_client.get_or_create_collection(
    name="pdf_documents",
    metadata={"description": "PDF document chunks with embeddings"},
)


groq_client = Groq(api_key=settings.groq_api_key)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def extract_text_from_pdf(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        text = ""

        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"

        if not text.strip():
            raise ValueError("No text could be extracted from the PDF")

        return text.strip()

    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {str(e)}")


def process_pdf(file_path: str, filename: str, user_id: int, db: Session) -> Document:
    print(f"Processing PDF: {filename}")

    print("Extracting text from PDF...")
    text = extract_text_from_pdf(file_path)

    reader = PdfReader(file_path)
    page_count = len(reader.pages)

    file_size = os.path.getsize(file_path)

    print(f"Extracted {len(text)} characters from {page_count} pages")

    print("Chunking text...")
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    print(f"Created {len(chunks)} chunks")

    document = Document(
        user_id=user_id,
        filename=filename,
        original_filename=filename,
        file_size=file_size,
        page_count=page_count,
        chunk_count=len(chunks),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    doc_id = str(document.id)
    print(f"Created document record (ID: {doc_id})")

    print("Storing embeddings in ChromaDB...")

    chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]

    metadatas: List[Dict[str, Any]] = [
        {
            "doc_id": doc_id,
            "user_id": str(user_id),
            "chunk_index": i,
            "filename": filename,
        }
        for i in range(len(chunks))
    ]

    collection.add(documents=chunks, ids=chunk_ids, metadatas=metadatas)

    print(f"PDF processed successfully: {filename}")
    print(f"Document ID: {doc_id}")
    print(f"Chunks: {len(chunks)}")
    print(f"Pages: {page_count}\n")

    return document


def query_document(
    document_id: int, question: str, user_id: int, n_results: int = 3
) -> Dict[str, Any]:
    print(f"\nQuerying document {document_id}: {question}")

    doc_id = str(document_id)

    try:
        results = collection.query(
            query_texts=[question], n_results=n_results, where={"doc_id": doc_id}
        )
    except Exception as e:
        print(f"ChromaDB query failed: {e}")
        return {
            "answer": "Failed to search the document. Please try again.",
            "source": "error",
            "chunks_used": 0,
        }

    docs_result = results.get("documents")
    distances_result = results.get("distances")

    if docs_result and isinstance(docs_result, list) and len(docs_result) > 0:
        documents = docs_result[0]
    else:
        documents = []

    if (
        distances_result
        and isinstance(distances_result, list)
        and len(distances_result) > 0
    ):
        distances = distances_result[0]
    else:
        distances = []

    print(f"Found {len(documents)} potential chunks")

    SIMILARITY_THRESHOLD = 1.0

    relevant_chunks: List[str] = []
    best_distance = float("inf")

    for doc, dist in zip(documents, distances):
        print(f"  → Chunk distance: {dist:.3f}")
        if dist < SIMILARITY_THRESHOLD:
            relevant_chunks.append(doc)
            if dist < best_distance:
                best_distance = dist

    print(f"  → {len(relevant_chunks)} chunks passed threshold")

    if relevant_chunks:
        context = "\n\n---\n\n".join(relevant_chunks)

        system_prompt = """You are a PDF document assistant. Your job is to answer questions based ONLY on the provided context from the document.

RULES:
- Answer questions using ONLY the information in the CONTEXT below
- If the answer is not in the context, say "I cannot find this information in the document"
- Be concise and direct
- Quote relevant parts when helpful
- Do not make up information"""

        user_prompt = f"""CONTEXT FROM DOCUMENT:
{context}

QUESTION: {question}

Answer the question based only on the context above."""

        source = "document"

    else:
        system_prompt = """You are a helpful assistant. The user asked about a document, but no relevant information was found in that document.

RULES:
- First, clearly state that you couldn't find this information in the user's document
- Then, if you have general knowledge about the topic, provide a brief, helpful response
- If you don't know, say so clearly"""

        user_prompt = f"""The user asked about their document: "{question}"

However, no relevant information was found in their document. Please respond appropriately."""

        source = "general_knowledge"

    print(f"Calling Groq LLM (source: {source})...")

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=500,
        )

        answer = completion.choices[0].message.content

    except Exception as e:
        print(f"Groq API call failed: {e}")
        return {
            "answer": "Failed to generate response. Please check your API key and try again.",
            "source": "error",
            "chunks_used": 0,
        }

    response: Dict[str, Any] = {
        "answer": answer,
        "source": source,
        "chunks_used": len(relevant_chunks),
        "best_distance": best_distance if relevant_chunks else None,
    }

    print("Query completed")
    print(f"Source: {source}")
    print(f"Chunks used: {len(relevant_chunks)}\n")

    return response


def delete_document(document_id: int, user_id: int, db: Session) -> bool:
    print(f"\nDeleting document {document_id}")

    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )

    if not document:
        print(f"Document {document_id} not found or unauthorized")
        return False

    try:
        doc_id = str(document_id)
        collection.delete(where={"doc_id": doc_id})
        print(f"Deleted {document.chunk_count} chunks from ChromaDB")
    except Exception as e:
        print(f"Warning: Failed to delete from ChromaDB: {e}")

    db.delete(document)
    db.commit()
    print("Deleted document record from database")

    print(f"Document {document_id} deleted successfully\n")
    return True


def get_user_documents(user_id: int, db: Session) -> List[Document]:
    documents = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.upload_date.desc())
        .all()
    )

    return documents
