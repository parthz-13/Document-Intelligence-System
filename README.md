# Document Intelligence System

An AI-powered document query system that allows users to upload PDFs and ask questions about them using natural language. Built with Retrieval-Augmented Generation (RAG) to provide accurate, context-aware responses.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![PostgreSQL](https://img.shields.io/badge/postgresql-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)


## Features

- **PDF Upload**: Upload PDF documents (up to 10MB) to your personal library
- **Intelligent Q&A**: Ask questions about your documents in natural language
- **Semantic Search**: Uses vector embeddings for accurate information retrieval
- **Smart Fallback**: Distinguishes between document-grounded answers and general knowledge
- **User Authentication**: Secure JWT-based authentication system
- **Document Management**: View, query, and delete your uploaded documents
- **Real-time Processing**: Fast PDF text extraction and chunking

### Tech Stack

**Backend:**
- **FastAPI**: High-performance async web framework
- **PostgreSQL (NeonDB)**: Serverless database for user data & metadata
- **ChromaDB**: Vector database for document embeddings
- **PyPDF**: PDF text extraction
- **SQLAlchemy**: ORM for database operations
- **Groq API**: LLM integration (Llama 3.3-70b-versatile)
- **JWT**: Secure authentication

**Frontend:**
- **React**: UI library with hooks
- **Vite**: Fast build tool
- **Axios**: HTTP client
- **React Router**: Client-side routing

## How It Works

### RAG Pipeline

1. **Document Upload**
   - User uploads PDF via frontend
   - Backend extracts text using PyPDF
   - Text is split into overlapping chunks 

2. **Embedding & Storage**
   - Chunks are embedded using sentence transformers
   - Embeddings stored in ChromaDB (vector database)
   - Metadata saved in PostgreSQL

3. **Query Processing**
   - User asks a question
   - Question is embedded using the same model
   - Semantic search finds relevant chunks (cosine similarity)

4. **Response Generation**
   - Retrieved chunks are sent to Groq LLM as context
   - LLM generates answer based on document content
   - If no relevant chunks found (distance > 1.63), falls back to general knowledge

### Smart Features

- **Summary Detection**: Questions like "summarize this" retrieve more chunks
- **Threshold-Based Routing**: Similarity threshold prevents hallucination
- **Dual-Mode Prompting**: Different prompts for document vs. general queries
- **User Isolation**: ChromaDB metadata filtering ensures users only access their documents

## Use Cases

- **Research**: Quickly extract information from academic papers
- **Legal**: Search through contracts and legal documents
- **HR**: Query employee handbooks and policies
- **Education**: Ask questions about textbooks and study materials
- **Personal**: Organize and query personal documents (resumes, receipts, etc.)

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [ChromaDB](https://www.trychroma.com/) - Vector database
- [Groq](https://groq.com/) - Fast LLM inference
- [NeonDB](https://neon.tech/) - Serverless PostgreSQL
- [React](https://react.dev/) - UI library