from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, test_connection
from app import models
app = FastAPI(
    title="PDF RAG API",
    description="Upload PDFs and query them with AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    print("Starting PDF RAG API...")
    
    if test_connection():
        print("Database connected")
    else:
        print("Database connection failed - check your .env file")
        return
    

    init_db()
    print("Application started successfully")



@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "PDF RAG API is running"
    }


@app.get("/")
async def root():
    return {
        "message": "Welcome to PDF RAG API",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)