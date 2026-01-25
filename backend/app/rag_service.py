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


def process_pdf(
    file_path: str,
    filename: str,
    user_id: int,
    db: Session
) -> Document:
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
    
