"""
PostgreSQL-based authentication service for base-chatbot
Uses PostgreSQL to store user data and passwords with bcrypt hashing
Compatible with the existing Firestore auth interface
"""
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Password hashing
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
except Exception as e:
    print(f"Warning: bcrypt context creation failed: {e}")
    # Fallback to a simpler configuration
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class PostgreSQLAuthService:
    """PostgreSQL-based authentication service"""
    
    def __init__(self):
        self.pwd_context = pwd_context
        self.db_service = None
        self.use_mock = True  # Will be set to False when DB is initialized
        self._mock_users = {}  # Store mock users for testing
        
        # Initialize database service based on environment
        self._initialize_database_service()
    
    def _initialize_database_service(self):
        """Initialize the appropriate database service"""
        database_type = os.getenv('DATABASE_TYPE', 'lakebase_postgres')
        
        try:
            if database_type == 'lakebase_postgres':
                from .lakebase_postgres_service import lakebase_postgres_service
                self.db_service = lakebase_postgres_service
                logger.info("✅ Using Lakebase PostgreSQL service")
            elif database_type == 'postgresql':
                from .postgres_service import PostgreSQLService
                self.db_service = PostgreSQLService()
                logger.info("✅ Using local PostgreSQL service")
            else:
                logger.warning(f"Unknown database type: {database_type}, falling back to mock")
                self.use_mock = True
                return
                
            # Test connection will be done when first method is called
            self._connection_tested = False
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database service: {e}")
            self.use_mock = True
    
    async def _ensure_connection(self):
        """Ensure database connection is tested and ready"""
        if hasattr(self, '_connection_tested') and self._connection_tested:
            return
        
        try:
            if self.db_service:
                if hasattr(self.db_service, 'check_connection'):
                    is_connected = await self.db_service.check_connection()
                    if is_connected:
                        self.use_mock = False
                        logger.info("✅ Database connection successful")
                    else:
                        logger.warning("⚠️ Database connection failed, using mock mode")
                        self.use_mock = True
                else:
                    # For services without check_connection, try to initialize
                    if hasattr(self.db_service, 'initialize'):
                        initialized = await self.db_service.initialize()
                        if initialized:
                            self.use_mock = False
                            logger.info("✅ Database service initialized successfully")
                        else:
                            logger.warning("⚠️ Database initialization failed, using mock mode")
                            self.use_mock = True
                    else:
                        self.use_mock = False
                        logger.info("✅ Database service ready")
            self._connection_tested = True
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            self.use_mock = True
            self._connection_tested = True
    
    def _hash_password(self, password: str) -> str:
        """Hash a password"""
        return self.pwd_context.hash(password)
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    async def create_user(self, email: str, password: str, display_name: str = None):
        """Create a new user in PostgreSQL"""
        await self._ensure_connection()
        
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_create_user(email, password, display_name)
        
        try:
            # Check if user already exists
            existing_user = await self.db_service.get_user_by_email(email)
            if existing_user:
                raise Exception("User with this email already exists")
            
            # Hash password
            hashed_password = self._hash_password(password)
            
            # Create user
            user_id = await self.db_service.create_user(email, hashed_password, display_name)
            
            return {
                'uid': user_id,
                'email': email,
                'display_name': display_name
            }
        except Exception as e:
            raise Exception(f"Error creating user: {str(e)}")
    
    async def verify_user(self, email: str, password: str):
        """Verify user credentials"""
        await self._ensure_connection()
        
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_verify_user(email, password)
        
        try:
            # Get user by email
            user = await self.db_service.get_user_by_email(email)
            if not user:
                raise Exception("Invalid credentials")
            
            # Check if user is active
            if not user.get('is_active', True):
                raise Exception("Account is deactivated")
            
            # Verify password
            if not self._verify_password(password, user['password_hash']):
                raise Exception("Invalid credentials")
            
            # Update last login
            await self._update_last_login(user['uid'])
            
            return {
                'uid': user['uid'],
                'email': user['email'],
                'display_name': user.get('display_name')
            }
        except Exception as e:
            raise Exception(f"Error verifying user: {str(e)}")
    
    async def get_user_by_uid(self, uid: str):
        """Get user data by UID"""
        await self._ensure_connection()
        
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_get_user_by_uid(uid)
        
        try:
            user = await self.db_service.get_user_by_id(uid)
            if not user:
                raise Exception("User not found")
            
            return {
                'uid': user['uid'],
                'email': user['email'],
                'display_name': user.get('display_name')
            }
        except Exception as e:
            raise Exception(f"Error getting user: {str(e)}")
    
    async def update_user_profile(self, uid: str, display_name: str = None, email: str = None):
        """Update user profile"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_update_user_profile(uid, display_name, email)
        
        try:
            # Check if user exists
            user = await self.db_service.get_user_by_id(uid)
            if not user:
                raise Exception("User not found")
            
            # Check if email is already taken (if changing email)
            if email and email != user['email']:
                existing_user = await self.db_service.get_user_by_email(email)
                if existing_user and existing_user['uid'] != uid:
                    raise Exception("Email already in use")
            
            # Update user in database
            await self._update_user_in_db(uid, display_name, email)
            
            return await self.get_user_by_uid(uid)
        except Exception as e:
            raise Exception(f"Error updating user profile: {str(e)}")
    
    async def change_password(self, uid: str, old_password: str, new_password: str):
        """Change user password"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_change_password(uid, old_password, new_password)
        
        try:
            user = await self.db_service.get_user_by_id(uid)
            if not user:
                raise Exception("User not found")
            
            # Verify old password
            if not self._verify_password(old_password, user['password_hash']):
                raise Exception("Current password is incorrect")
            
            # Update password
            new_password_hash = self._hash_password(new_password)
            await self._update_password_in_db(uid, new_password_hash)
            
            return True
        except Exception as e:
            raise Exception(f"Error changing password: {str(e)}")
    
    async def delete_user(self, uid: str):
        """Delete user account (soft delete)"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_delete_user(uid)
        
        try:
            user = await self.db_service.get_user_by_id(uid)
            if not user:
                raise Exception("User not found")
            
            # Soft delete - mark as inactive
            await self._soft_delete_user_in_db(uid)
            
            return True
        except Exception as e:
            raise Exception(f"Error deleting user: {str(e)}")
    
    # Conversation management methods
    async def create_conversation(self, uid: str, title: str = "New Conversation"):
        """Create a new conversation for a user"""
        await self._ensure_connection()
        
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_create_conversation(uid, title)
        
        try:
            # Check current conversation count and clean up if needed
            await self._enforce_conversation_limit(uid)
            
            # Create conversation
            conversation_id = await self.db_service.create_conversation(uid, title)
            
            return {
                'id': conversation_id,
                'uid': uid,
                'title': title,
                'messages': [],
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise Exception(f"Error creating conversation: {str(e)}")
    
    async def get_user_conversations(self, uid: str):
        """Get all conversations for a user"""
        await self._ensure_connection()
        
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_get_user_conversations(uid)
        
        try:
            conversations = await self.db_service.get_user_conversations(uid)
            
            # Format conversations to match expected structure
            formatted_conversations = []
            for conv in conversations:
                # Get messages for this conversation
                messages = await self.db_service.get_conversation_messages(conv['id'])
                
                formatted_conversations.append({
                    'id': conv['id'],
                    'uid': conv['uid'],
                    'title': conv['title'],
                    'messages': messages,
                    'created_at': conv['created_at'].isoformat() if conv['created_at'] else datetime.utcnow().isoformat(),
                    'updated_at': conv['updated_at'].isoformat() if conv['updated_at'] else datetime.utcnow().isoformat()
                })
            
            return formatted_conversations
        except Exception as e:
            raise Exception(f"Error getting conversations: {str(e)}")
    
    async def update_conversation(self, conversation_id: str, title: str = None, messages: list = None):
        """Update a conversation"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_update_conversation(conversation_id, title, messages)
        
        try:
            # Update conversation in database
            await self._update_conversation_in_db(conversation_id, title, messages)
            
            # Get the user ID from the conversation to enforce limits
            conversation = await self._get_conversation_by_id(conversation_id)
            if conversation:
                uid = conversation.get('uid')
                if uid:
                    await self._enforce_conversation_limit(uid)
            
            return True
        except Exception as e:
            raise Exception(f"Error updating conversation: {str(e)}")
    
    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_delete_conversation(conversation_id)
        
        try:
            await self._delete_conversation_in_db(conversation_id)
            return True
        except Exception as e:
            raise Exception(f"Error deleting conversation: {str(e)}")
    
    async def _enforce_conversation_limit(self, uid: str, max_conversations: int = 20):
        """Enforce conversation limit by deleting oldest conversations"""
        if self.use_mock:
            # Mock implementation for testing
            return await self._mock_enforce_conversation_limit(uid, max_conversations)
        
        try:
            conversations = await self.db_service.get_user_conversations(uid)
            
            # If we have more than the limit, delete the oldest ones
            if len(conversations) >= max_conversations:
                # Sort by updated_at (oldest first)
                conversations.sort(key=lambda x: x['updated_at'] if x['updated_at'] else x['created_at'])
                
                # Delete the oldest conversations
                conversations_to_delete = conversations[:len(conversations) - max_conversations + 1]
                for conv in conversations_to_delete:
                    await self.delete_conversation(conv['id'])
                
                logger.info(f"Deleted {len(conversations_to_delete)} old conversations for user {uid}")
                
        except Exception as e:
            logger.error(f"Error enforcing conversation limit: {e}")
    
    # Database helper methods
    async def _update_last_login(self, uid: str):
        """Update user's last login timestamp"""
        try:
            await self.db_service._execute_sql(
                f"UPDATE {self.db_service.catalog}.{self.db_service.schema}.users SET last_login = current_timestamp() WHERE uid = '{uid}'"
            )
        except Exception as e:
            logger.error(f"Error updating last login: {e}")
    
    async def _update_user_in_db(self, uid: str, display_name: str = None, email: str = None):
        """Update user in database"""
        updates = []
        if display_name is not None:
            updates.append(f"display_name = '{display_name}'")
        if email is not None:
            updates.append(f"email = '{email}'")
        
        if updates:
            updates.append("updated_at = current_timestamp()")
            sql = f"UPDATE {self.db_service.catalog}.{self.db_service.schema}.users SET {', '.join(updates)} WHERE uid = '{uid}'"
            await self.db_service._execute_sql(sql)
    
    async def _update_password_in_db(self, uid: str, password_hash: str):
        """Update user password in database"""
        sql = f"UPDATE {self.db_service.catalog}.{self.db_service.schema}.users SET password_hash = '{password_hash}', updated_at = current_timestamp() WHERE uid = '{uid}'"
        await self.db_service._execute_sql(sql)
    
    async def _soft_delete_user_in_db(self, uid: str):
        """Soft delete user in database"""
        sql = f"UPDATE {self.db_service.catalog}.{self.db_service.schema}.users SET is_active = false, deleted_at = current_timestamp() WHERE uid = '{uid}'"
        await self.db_service._execute_sql(sql)
    
    async def _update_conversation_in_db(self, conversation_id: str, title: str = None, messages: list = None):
        """Update conversation in database"""
        updates = ["updated_at = current_timestamp()"]
        if title is not None:
            updates.append(f"title = '{title}'")
        
        if updates:
            sql = f"UPDATE {self.db_service.catalog}.{self.db_service.schema}.conversations SET {', '.join(updates)} WHERE id = '{conversation_id}'"
            await self.db_service._execute_sql(sql)
        
        # If messages are provided, update them
        if messages is not None:
            # Delete existing messages
            await self.db_service._execute_sql(f"DELETE FROM {self.db_service.catalog}.{self.db_service.schema}.messages WHERE conversation_id = '{conversation_id}'")
            
            # Insert new messages
            for i, message in enumerate(messages):
                await self.db_service.add_message(
                    conversation_id=conversation_id,
                    user_id=message.get('uid', ''),
                    role=message.get('role', 'user'),
                    content=message.get('content', ''),
                    token_count=message.get('token_count'),
                    model_used=message.get('model_used')
                )
    
    async def _get_conversation_by_id(self, conversation_id: str):
        """Get conversation by ID"""
        try:
            sql = f"SELECT id, uid, title, created_at, updated_at FROM {self.db_service.catalog}.{self.db_service.schema}.conversations WHERE id = '{conversation_id}'"
            result = await self.db_service._execute_sql(sql)
            if result["success"] and "result" in result["data"] and result["data"]["result"]["data_array"]:
                row = result["data"]["result"]["data_array"][0]
                return {
                    "id": row[0],
                    "uid": row[1],
                    "title": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return None
    
    async def _delete_conversation_in_db(self, conversation_id: str):
        """Delete conversation from database"""
        # Delete messages first
        await self.db_service._execute_sql(f"DELETE FROM {self.db_service.catalog}.{self.db_service.schema}.messages WHERE conversation_id = '{conversation_id}'")
        # Delete conversation
        await self.db_service._execute_sql(f"DELETE FROM {self.db_service.catalog}.{self.db_service.schema}.conversations WHERE id = '{conversation_id}'")
    
    # Mock implementations for testing
    async def _mock_create_user(self, email: str, password: str, display_name: str = None):
        """Mock create user for testing"""
        uid = f"mock_user_{int(datetime.now().timestamp() * 1000)}"
        user_data = {
            'uid': uid,
            'email': email,
            'display_name': display_name,
            'password_hash': self._hash_password(password)
        }
        self._mock_users[email] = user_data
        return {
            'uid': uid,
            'email': email,
            'display_name': display_name
        }
    
    async def _mock_verify_user(self, email: str, password: str):
        """Mock verify user for testing"""
        if email in self._mock_users:
            user_data = self._mock_users[email]
            if self._verify_password(password, user_data['password_hash']):
                return {
                    'uid': user_data['uid'],
                    'email': user_data['email'],
                    'display_name': user_data['display_name']
                }
        raise Exception("Invalid credentials")
    
    async def _mock_get_user_by_uid(self, uid: str):
        """Mock get user by UID for testing"""
        # Find user by UID in mock users
        for user_data in self._mock_users.values():
            if user_data['uid'] == uid:
                return {
                    'uid': user_data['uid'],
                    'email': user_data['email'],
                    'display_name': user_data['display_name']
                }
        raise Exception("User not found")
    
    async def _mock_update_user_profile(self, uid: str, display_name: str = None, email: str = None):
        """Mock update user profile for testing"""
        return {
            'uid': uid,
            'email': email or "test@example.com",
            'display_name': display_name or "Test User"
        }
    
    async def _mock_change_password(self, uid: str, old_password: str, new_password: str):
        """Mock change password for testing"""
        return True
    
    async def _mock_delete_user(self, uid: str):
        """Mock delete user for testing"""
        return True
    
    async def _mock_create_conversation(self, uid: str, title: str):
        """Mock create conversation for testing"""
        return {
            'id': f"mock_conv_{int(datetime.now().timestamp() * 1000)}",
            'uid': uid,
            'title': title,
            'messages': [],
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
    
    async def _mock_get_user_conversations(self, uid: str):
        """Mock get user conversations for testing"""
        return []
    
    async def _mock_update_conversation(self, conversation_id: str, title: str = None, messages: list = None):
        """Mock update conversation for testing"""
        return True
    
    async def _mock_delete_conversation(self, conversation_id: str):
        """Mock delete conversation for testing"""
        return True
    
    async def _mock_enforce_conversation_limit(self, uid: str, max_conversations: int = 20):
        """Mock enforce conversation limit for testing"""
        pass

# Initialize auth service
postgres_auth = PostgreSQLAuthService()
