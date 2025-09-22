import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, User
from config.database import get_async_db

logger = logging.getLogger(__name__)

async def get_user_conversations(user_email: str) -> List[Dict[str, Any]]:
    """Get all conversations for a user by email"""
    try:
        async for db in get_async_db():
            # First get the user
            user_stmt = select(User).where(User.email == user_email)
            user_result = await db.execute(user_stmt)
            user = user_result.scalars().first()
            
            if not user:
                logger.warning(f"User not found: {user_email}")
                return []
            
            # Get conversations for the user
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
            result = await db.execute(stmt)
            conversations = result.scalars().all()
            
            return [conv.to_dict() for conv in conversations]
            
    except Exception as e:
        logger.error(f"Error getting conversations for user {user_email}: {e}")
        return []

async def create_conversation(user_email: str, title: str, messages: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Create a new conversation for a user"""
    try:
        async for db in get_async_db():
            # First get or create the user
            from services.user_service import get_or_create_user
            user = await get_or_create_user(user_email)
            
            if not user:
                logger.error(f"Could not get or create user: {user_email}")
                return None
            
            # Create conversation
            conversation_id = f"conv_{uuid.uuid4().hex[:8]}"
            now = datetime.now()
            
            conversation = Conversation(
                id=conversation_id,
                title=title,
                user_id=user.id,
                messages=messages or []
            )
            
            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)
            
            logger.info(f"Created conversation {conversation_id} for user {user_email}")
            return conversation.to_dict()
            
    except Exception as e:
        logger.error(f"Error creating conversation for user {user_email}: {e}")
        return None

async def update_conversation(conversation_id: str, user_email: str, title: str = None, messages: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Update a conversation"""
    try:
        async for db in get_async_db():
            # First get the user
            user_stmt = select(User).where(User.email == user_email)
            user_result = await db.execute(user_stmt)
            user = user_result.scalars().first()
            
            if not user:
                logger.warning(f"User not found: {user_email}")
                return None
            
            # Get the conversation
            stmt = select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id
            )
            result = await db.execute(stmt)
            conversation = result.scalars().first()
            
            if not conversation:
                logger.warning(f"Conversation not found: {conversation_id}")
                return None
            
            # Update fields
            if title is not None:
                conversation.title = title
            if messages is not None:
                conversation.messages = messages
            
            conversation.updated_at = datetime.now()
            await db.commit()
            await db.refresh(conversation)
            
            logger.info(f"Updated conversation {conversation_id}")
            return conversation.to_dict()
            
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        return None

async def delete_conversation(conversation_id: str, user_email: str) -> bool:
    """Delete a conversation"""
    try:
        async for db in get_async_db():
            # First get the user
            user_stmt = select(User).where(User.email == user_email)
            user_result = await db.execute(user_stmt)
            user = user_result.scalars().first()
            
            if not user:
                logger.warning(f"User not found: {user_email}")
                return False
            
            # Get the conversation
            stmt = select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id
            )
            result = await db.execute(stmt)
            conversation = result.scalars().first()
            
            if not conversation:
                logger.warning(f"Conversation not found: {conversation_id}")
                return False
            
            # Delete the conversation
            await db.delete(conversation)
            await db.commit()
            
            logger.info(f"Deleted conversation {conversation_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}")
        return False

async def cleanup_empty_conversations(user_email: str) -> int:
    """Clean up empty conversations for a user"""
    try:
        async for db in get_async_db():
            # First get the user
            user_stmt = select(User).where(User.email == user_email)
            user_result = await db.execute(user_stmt)
            user = user_result.scalars().first()
            
            if not user:
                logger.warning(f"User not found: {user_email}")
                return 0
            
            # Find empty conversations
            stmt = select(Conversation).where(
                Conversation.user_id == user.id,
                func.json_array_length(Conversation.messages) == 0
            )
            result = await db.execute(stmt)
            empty_conversations = result.scalars().all()
            
            # Delete empty conversations
            deleted_count = 0
            for conversation in empty_conversations:
                await db.delete(conversation)
                deleted_count += 1
            
            await db.commit()
            logger.info(f"Cleaned up {deleted_count} empty conversations for user {user_email}")
            return deleted_count
            
    except Exception as e:
        logger.error(f"Error cleaning up conversations for user {user_email}: {e}")
        return 0
