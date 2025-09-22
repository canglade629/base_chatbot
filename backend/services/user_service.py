import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from config.database import get_async_db

logger = logging.getLogger(__name__)

async def get_or_create_user(email: str, display_name: str = None, username: str = None) -> Optional[User]:
    """Get existing user or create new user in Lakebase"""
    try:
        logger.info(f"Attempting to get or create user: {email}")
        
        async for db in get_async_db():
            logger.info(f"Got database session for user: {email}")
            
            # Try to get existing user
            stmt = select(User).where(User.email == email)
            logger.info(f"Executing query to find user: {email}")
            result = await db.execute(stmt)
            user = result.scalars().first()
            
            if user:
                # Update last login time
                user.last_login = datetime.now()
                await db.commit()
                logger.info(f"User found and last login updated: {email}")
                return user
            else:
                # Create new user
                user_id = f"user_{uuid.uuid4().hex[:8]}"
                logger.info(f"Creating new user with ID: {user_id}")
                
                new_user = User(
                    id=user_id,
                    email=email,
                    display_name=display_name or email.split('@')[0],
                    username=username or email.split('@')[0],
                    last_login=datetime.now()
                )
                
                db.add(new_user)
                logger.info(f"Added user to session: {email}")
                await db.commit()
                logger.info(f"Committed user creation: {email}")
                await db.refresh(new_user)
                logger.info(f"New user created successfully: {email}")
                return new_user
                
    except Exception as e:
        logger.error(f"Error getting or creating user {email}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

async def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email"""
    try:
        async for db in get_async_db():
            stmt = select(User).where(User.email == email)
            result = await db.execute(stmt)
            return result.scalars().first()
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {e}")
        return None

async def update_user_last_login(email: str) -> bool:
    """Update user's last login time"""
    try:
        async for db in get_async_db():
            stmt = select(User).where(User.email == email)
            result = await db.execute(stmt)
            user = result.scalars().first()
            
            if user:
                user.last_login = datetime.now()
                await db.commit()
                return True
            return False
    except Exception as e:
        logger.error(f"Error updating last login for {email}: {e}")
        return False
