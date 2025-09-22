from sqlalchemy import Column, String, DateTime, Text, Integer, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import List, Dict, Any

Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    messages = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship to user
    user = relationship("User", back_populates="conversations")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation to dictionary for API responses"""
        return {
            "id": self.id,
            "title": self.title,
            "messages": self.messages,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @property
    def last_message(self) -> str:
        """Get the last message text from the conversation"""
        if self.messages and len(self.messages) > 0:
            last_msg = self.messages[-1]
            return last_msg.get("text", "") if isinstance(last_msg, dict) else str(last_msg)
        return ""
