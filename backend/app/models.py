from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    documents = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan"  
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class Document(Base):

    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  
    chunk_count = Column(Integer, default=0) 
    page_count = Column(Integer, default=0)  
    
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    owner = relationship("User", back_populates="documents")
    queries = relationship(
        "Query",
        back_populates="document",
        cascade="all, delete-orphan"  
    )
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, user_id={self.user_id})>"


class Query(Base):

    __tablename__ = "queries"
    
    id = Column(Integer, primary_key=True, index=True)
    
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    
    source = Column(String(50), default="document") 
    chunks_used = Column(Integer, default=0)       
    best_distance = Column(Float, nullable=True)   
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    document = relationship("Document", back_populates="queries")
    
    def __repr__(self):
        return f"<Query(id={self.id}, document_id={self.document_id}, question={self.question[:50]}...)>"