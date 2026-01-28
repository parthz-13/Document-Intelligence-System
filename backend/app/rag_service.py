from typing import List, Dict, Any
import os
from pypdf import PdfReader
from groq import Groq
from sqlalchemy.orm import Session
import sys
from app.database import settings
from app.models import Document


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
import httpx

import uuid
import os


JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_API_KEY = os.getenv("JINA_API_KEY")


COLLECTION_NAME = "pdf_documents"


def generate_embedding(text: str) -> List[float]:
    try:
        response = httpx.post(
            JINA_API_URL,
            headers={
                "Authorization": f"Bearer {JINA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"input": [text], "model": "jina-embeddings-v2-base-en"},
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        embedding = data["data"][0]["embedding"]

        return embedding

    except Exception as e:
        print(f"Error generating embedding: {e}")
        raise Exception(f"Failed to generate embedding: {str(e)}")



qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

COLLECTION_NAME = "pdf_documents"


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
                print(f"Created index on '{field_name}'")
            except Exception:
                print(f"Index '{field_name}' may already exist")

    except Exception:
        print(f"Creating collection '{COLLECTION_NAME}'...")

        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=768,  
                distance=Distance.COSINE,
            ),
        )

        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="doc_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

        print("Created collection with 768-dim vectors")


initialize_qdrant()


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
    print(f"\nProcessing PDF: {filename}")

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
    db.flush()  

    doc_id = str(document.id)
    print(f"Created document record (ID: {doc_id})")

    print("Generating embeddings with Jina AI...")

    points = []
    for i, chunk in enumerate(chunks):
        try:
            embedding = generate_embedding(chunk)

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "doc_id": doc_id,
                        "user_id": str(user_id),
                        "chunk_index": i,
                        "filename": filename,
                        "text": chunk,
                    },
                )
            )

            if (i + 1) % 5 == 0:
                print(f"Processed {i + 1}/{len(chunks)} chunks...")

        except Exception as e:
            print(f"Failed to embed chunk {i}: {e}")

    if not points:
        db.rollback()
        raise RuntimeError("All embeddings failed. Document was NOT indexed.")

    try:
        print(f"DEBUG: points length before upsert = {len(points)}")
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Uploaded {len(points)} chunks to Qdrant")

        db.commit()
        db.refresh(document)
        print(f"Committed document record to database")

    except Exception as e:
        db.rollback()
        print(f"Failed to upload to Qdrant: {e}")
        raise RuntimeError(f"Qdrant indexing failed: {str(e)}")

    print(f"PDF processed successfully: {filename}")
    print(f"Document ID: {document.id}")
    print(f"Chunks: {len(chunks)}")
    print(f"Pages: {page_count}\n")

    return document


def query_document(
    document_id: int, question: str, user_id: int, n_results: int = 5
) -> Dict[str, Any]:
    print("QUERY DEBUG")
    print(f"Document ID: {document_id}")
    print(f"Question: {question}")

    doc_id = str(document_id)

    summary_keywords = [
        "summary",
        "summarize",
        "summarise",
        "overview",
        "about",
        "what is this",
        "what's this",
        "tell me about",
        "main points",
        "key points",
        "gist",
        "brief",
        "describe this",
        "content",
    ]

    is_summary_question = any(
        keyword in question.lower() for keyword in summary_keywords
    )

    identity_keywords = [
        "who is",
        "who's",
        "tell me about",
        "information about",
        "details about",
        "background of",
        "describe",
    ]

    is_identity_question = any(
        keyword in question.lower() for keyword in identity_keywords
    )

    try:
        count_result = qdrant_client.count(
            collection_name=COLLECTION_NAME,
            count_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
        )

        total_chunks = count_result.count
        print(f"\nDocument has {total_chunks} chunks in Qdrant")

        if total_chunks == 0:
            return {
                "answer": "This document has no content. Please re-upload it.",
                "source": "error",
                "chunks_used": 0,
                "best_distance": None,
            }

    except Exception as e:
        print(f"Error accessing Qdrant: {e}")
        import traceback

        traceback.print_exc()
        return {
            "answer": "Failed to access document storage. Please try again.",
            "source": "error",
            "chunks_used": 0,
            "best_distance": None,
        }

    if is_summary_question:
        print("Detected SUMMARY question")
        n_results = min(10, total_chunks)
        SIMILARITY_THRESHOLD = 2.0

    elif is_identity_question:
        print("Detected IDENTITY question")
        n_results = min(10, total_chunks)
        SIMILARITY_THRESHOLD = 2.0

    else:
        print("Specific question")
        SIMILARITY_THRESHOLD = 1.63

    try:
        question_embedding = generate_embedding(question)

        search_results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=question_embedding,
            query_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
            limit=n_results,
            with_payload=True,
            with_vectors=False,
        )

        print(f"Query returned {len(search_results.points)} results")

        documents = []
        distances = []

        for hit in search_results.points:
            documents.append(hit.payload["text"])
            distances.append(1 - hit.score)

    except Exception as e:
        print(f"Qdrant query failed: {e}")
        import traceback

        traceback.print_exc()
        return {
            "answer": "Search failed. Please try again.",
            "source": "error",
            "chunks_used": 0,
            "best_distance": None,
        }

    if is_identity_question:
        import re

        patterns = [
            r"who (?:is|'s) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
            r"about ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
            r"tell me about ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        ]

        extracted_name = None
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                extracted_name = match.group(1)
                print(f"Extracted name from question: '{extracted_name}'")
                break

        if extracted_name:
            print(f"Searching for mentions of '{extracted_name}' in document...")

            name_chunks = []
            for doc in documents:
                if extracted_name.lower() in doc.lower():
                    name_chunks.append(doc)
                    print(f"Found in chunk: {doc[:80]}...")

            if name_chunks:
                relevant_chunks = name_chunks
                best_distance = 0.0
                print(
                    f"Using {len(relevant_chunks)} chunks mentioning '{extracted_name}'"
                )
            else:
                print(f"Name '{extracted_name}' not found in document")
                relevant_chunks = []
                best_distance = None
        else:
            relevant_chunks = [
                doc
                for doc, dist in zip(documents, distances)
                if dist < SIMILARITY_THRESHOLD
            ]
            best_distance = min(distances) if distances else None

    elif is_summary_question:
        relevant_chunks = documents[:10]
        best_distance = min(distances) if distances else None
        print(f"Summary mode: Using {len(relevant_chunks)} chunks")

    else:
        relevant_chunks: List[str] = []
        best_distance = float("inf")

        for doc, dist in zip(documents, distances):
            print(f"Chunk distance: {dist:.3f}")
            if dist < SIMILARITY_THRESHOLD:
                relevant_chunks.append(doc)
                if dist < best_distance:
                    best_distance = dist

        print(f"{len(relevant_chunks)} chunks passed threshold")

    if relevant_chunks:
        context = "\n\n---\n\n".join(relevant_chunks)

        if is_summary_question:
            system_prompt = """You are a document summarization assistant.

Your task:
- Provide a concise summary of the document based on the provided text
- Highlight the main points and key information
- Organize the summary in a clear, structured way
- Keep it to 3-5 sentences unless asked for more detail

DO NOT make up information not in the text."""

            user_prompt = f"""DOCUMENT CONTENT:
{context}

USER QUESTION: {question}

Provide a clear summary based on the content above."""

        elif is_identity_question:
            system_prompt = """You are a helpful assistant answering questions about people mentioned in documents.

Your task:
- Answer the question based ONLY on the information provided in the document content
- Be specific and cite relevant details (education, position, achievements, etc.)
- If the person is mentioned but no details are given, say so
- Do NOT make up biographical information"""

            user_prompt = f"""DOCUMENT CONTENT:
{context}

QUESTION: {question}

Answer based only on what's mentioned in the document above."""

        else:
            system_prompt = """You are a PDF document assistant. Answer questions based ONLY on the provided context.

RULES:
- Use ONLY information from the CONTEXT below
- If the answer isn't in the context, say "I cannot find this information in the document"
- Be concise and direct
- Quote relevant parts when helpful"""

            user_prompt = f"""CONTEXT FROM DOCUMENT:
{context}

QUESTION: {question}

Answer based only on the context above."""

        source = "document"

    else:
        system_prompt = """You are a helpful AI assistant. The user asked about their document, but no relevant information was found.

Your response should:
1. Briefly acknowledge the information isn't in their document
2. Provide helpful general knowledge if applicable
3. Be friendly and conversational"""

        user_prompt = f"""Question: {question}

This information wasn't found in the user's document. Provide a helpful response."""

        source = "general_knowledge"

    print(f"Calling Groq LLM (source: {source})...")

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=800 if is_summary_question else 500,
        )

        answer = completion.choices[0].message.content

    except Exception as e:
        print(f"Groq API call failed: {e}")
        return {
            "answer": "Failed to generate response.",
            "source": "error",
            "chunks_used": 0,
        }

    response: Dict[str, Any] = {
        "answer": answer,
        "source": source,
        "chunks_used": len(relevant_chunks),
        "best_distance": best_distance if relevant_chunks else None,
    }

    print(f"Query completed - Source: {source}, Chunks: {len(relevant_chunks)}\n")

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

        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector={
                "filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}
            },
        )

        print("Deleted chunks from Qdrant")

        file_path = os.path.join("uploads", f"user_{user_id}_{document.filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted file: {file_path}")
        else:
            file_path = os.path.join("uploads", document.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleted file: {file_path}")

    except Exception as e:
        print(f"Warning: Failed to delete resources: {e}")

    db.delete(document)
    db.commit()

    print(f"Document {document_id} deleted successfully")
    return True


def get_user_documents(user_id: int, db: Session) -> List[Document]:
    documents = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.upload_date.desc())
        .all()
    )

    return documents
