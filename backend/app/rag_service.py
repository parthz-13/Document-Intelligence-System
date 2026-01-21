from typing import List, Dict, Any
import os
from PyPDF2 import PdfReader
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
    metadata={"description": "PDF document chunks with embeddings"}
)

