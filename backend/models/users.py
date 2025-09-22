from sqlalchemy import Column, String, DateTime, Text, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import List, Dict, Any

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship to conversations
    conversations = relationship("Conversation", back_populates="user")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for API responses"""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
