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
    document_id: int,
    question: str,
    user_id: int,
    n_results: int = 5
) -> Dict[str, Any]:
    print(f"QUERY DEBUG")
    print(f"Document ID: {document_id}")
    print(f"Question: {question}")
    
    doc_id = str(document_id)
    
    summary_keywords = [
        "summary", "summarize", "summarise", "overview", "about",
        "what is this", "what's this", "tell me about", "main points",
        "key points", "gist", "brief", "describe this", "content"
    ]
    
    is_summary_question = any(keyword in question.lower() for keyword in summary_keywords)
    
    identity_keywords = [
        "who is", "who's", "tell me about", "information about",
        "details about", "background of", "describe"
    ]
    
    is_identity_question = any(keyword in question.lower() for keyword in identity_keywords)
    
    try:
        doc_chunks = collection.get(
            where={"doc_id": doc_id}
        )
        total_chunks = len(doc_chunks.get("ids", []))
        print(f"\nDocument has {total_chunks} chunks in ChromaDB")
        
        if total_chunks == 0:
            return {
                "answer": "This document has no content. Please re-upload it.",
                "source": "error",
                "chunks_used": 0
            }
            
    except Exception as e:
        print(f"Error accessing ChromaDB: {e}")
        return {
            "answer": "Failed to access document storage. Please try again.",
            "source": "error",
            "chunks_used": 0
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
        results = collection.query(
            query_texts=[question],
            n_results=n_results,
            where={"doc_id": doc_id}
        )
        print(f"Query returned {len(results.get('documents', [[]])[0])} results")
    except Exception as e:
        print(f"ChromaDB query failed: {e}")
        return {
            "answer": "Search failed. Please try again.",
            "source": "error",
            "chunks_used": 0
        }
    
    docs_result = results.get("documents")
    distances_result = results.get("distances")
    
    if docs_result and isinstance(docs_result, list) and len(docs_result) > 0:
        documents = docs_result[0]
        distances = distances_result[0] if distances_result else []
    else:
        documents = []
        distances = []
    
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
                print(f"Using {len(relevant_chunks)} chunks mentioning '{extracted_name}'")
            else:
                print(f"Name '{extracted_name}' not found in document")
                relevant_chunks = []
                best_distance = None
        else:
            relevant_chunks = [doc for doc, dist in zip(documents, distances) if dist < SIMILARITY_THRESHOLD]
            best_distance = min(distances) if distances else None
    
    elif is_summary_question:
        relevant_chunks = documents[:10]
        best_distance = min(distances) if distances else None
        print(f"  → Summary mode: Using {len(relevant_chunks)} chunks")
    
    else:
        relevant_chunks: List[str] = []
        best_distance = float('inf')
        
        for doc, dist in zip(documents, distances):
            print(f"  → Chunk distance: {dist:.3f}")
            if dist < SIMILARITY_THRESHOLD:
                relevant_chunks.append(doc)
                if dist < best_distance:
                    best_distance = dist
        
        print(f"  → {len(relevant_chunks)} chunks passed threshold")
    
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
            model = "llama-3.3-70b-versatile" ,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=800 if is_summary_question else 500
        )
        
        answer = completion.choices[0].message.content
        
    except Exception as e:
        print(f"Groq API call failed: {e}")
        return {
            "answer": "Failed to generate response.",
            "source": "error",
            "chunks_used": 0
        }
    
    response: Dict[str, Any] = {
        "answer": answer,
        "source": source,
        "chunks_used": len(relevant_chunks),
        "best_distance": best_distance if relevant_chunks else None
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
