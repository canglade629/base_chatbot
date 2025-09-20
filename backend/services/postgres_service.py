"""
PostgreSQL Database Service for base-chatbot
Provides database connection and admin role management
"""
import os
import asyncio
import asyncpg
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class PostgreSQLService:
    """PostgreSQL database service with admin role support"""
    
    def __init__(self):
        self.host = os.getenv('POSTGRES_HOST', 'localhost')
        self.port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.database = os.getenv('POSTGRES_DB', 'base_chatbot')
        self.user = os.getenv('POSTGRES_USER', 'base_chatbot_admin_user')
        self.password = os.getenv('POSTGRES_PASSWORD', 'base_chatbot_admin_2024!')
        self.schema = os.getenv('POSTGRES_SCHEMA', 'base_chatbot')
        self.admin_role = os.getenv('POSTGRES_ADMIN_ROLE', 'base_chatbot_admin')
        
        # Connection pool
        self.pool: Optional[asyncpg.Pool] = None
        
        # Connection string
        self.connection_string = (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
        )
        
        logger.info(f"PostgreSQL service initialized for database: {self.database}")
        logger.info(f"Using schema: {self.schema}")
        logger.info(f"Admin role: {self.admin_role}")
    
    async def initialize(self) -> bool:
        """Initialize the database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=1,
                max_size=10,
                command_timeout=60,
                server_settings={
                    'search_path': f'{self.schema}, public'
                }
            )
            logger.info("✅ PostgreSQL connection pool initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize PostgreSQL connection pool: {e}")
            return False
    
    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")
        
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise
    
    async def execute_command(self, command: str, *args) -> str:
        """Execute a command (INSERT, UPDATE, DELETE) and return status"""
        try:
            async with self.get_connection() as conn:
                result = await conn.execute(command, *args)
                return result
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            raise
    
    async def execute_scalar(self, query: str, *args) -> Any:
        """Execute a query and return a single scalar value"""
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchval(query, *args)
                return result
        except Exception as e:
            logger.error(f"Error executing scalar query: {e}")
            raise
    
    async def check_connection(self) -> bool:
        """Check if the database connection is working"""
        try:
            result = await self.execute_scalar("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    async def check_admin_permissions(self) -> Dict[str, Any]:
        """Check if the current user has admin permissions"""
        try:
            # Check if user has admin role
            admin_check = await self.execute_scalar(
                "SELECT pg_has_role($1, 'MEMBER')",
                self.admin_role
            )
            
            # Check database privileges
            db_privileges = await self.execute_query("""
                SELECT 
                    has_database_privilege(current_user, current_database(), 'CONNECT') as can_connect,
                    has_database_privilege(current_user, current_database(), 'CREATE') as can_create,
                    has_database_privilege(current_user, current_database(), 'TEMPORARY') as can_create_temp
            """)
            
            # Check schema privileges
            schema_privileges = await self.execute_query("""
                SELECT 
                    has_schema_privilege(current_user, $1, 'USAGE') as can_use,
                    has_schema_privilege(current_user, $1, 'CREATE') as can_create
            """, self.schema)
            
            # Check table privileges
            table_privileges = await self.execute_query("""
                SELECT 
                    table_name,
                    has_table_privilege(current_user, $1||'.'||table_name, 'SELECT') as can_select,
                    has_table_privilege(current_user, $1||'.'||table_name, 'INSERT') as can_insert,
                    has_table_privilege(current_user, $1||'.'||table_name, 'UPDATE') as can_update,
                    has_table_privilege(current_user, $1||'.'||table_name, 'DELETE') as can_delete
                FROM information_schema.tables 
                WHERE table_schema = $1
                ORDER BY table_name
            """, self.schema)
            
            return {
                "has_admin_role": admin_check,
                "database_privileges": db_privileges[0] if db_privileges else {},
                "schema_privileges": schema_privileges[0] if schema_privileges else {},
                "table_privileges": table_privileges,
                "current_user": await self.execute_scalar("SELECT current_user"),
                "current_database": await self.execute_scalar("SELECT current_database()"),
                "current_schema": await self.execute_scalar("SELECT current_schema()")
            }
        except Exception as e:
            logger.error(f"Error checking admin permissions: {e}")
            return {"error": str(e)}
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information"""
        try:
            # Database version and info
            version_info = await self.execute_scalar("SELECT version()")
            
            # Database size
            db_size = await self.execute_scalar("SELECT pg_size_pretty(pg_database_size(current_database()))")
            
            # Table information
            tables_info = await self.execute_query("""
                SELECT 
                    table_name,
                    table_type,
                    (SELECT COUNT(*) FROM information_schema.columns 
                     WHERE table_schema = $1 AND table_name = t.table_name) as column_count
                FROM information_schema.tables t
                WHERE table_schema = $1
                ORDER BY table_name
            """, self.schema)
            
            # User and role information
            user_info = await self.execute_query("""
                SELECT 
                    rolname as role_name,
                    rolsuper as is_superuser,
                    rolcreaterole as can_create_roles,
                    rolcreatedb as can_create_databases,
                    rolcanlogin as can_login
                FROM pg_roles 
                WHERE rolname LIKE '%base_chatbot%'
                ORDER BY rolname
            """)
            
            return {
                "version": version_info,
                "database_size": db_size,
                "current_database": await self.execute_scalar("SELECT current_database()"),
                "current_schema": await self.execute_scalar("SELECT current_schema()"),
                "tables": tables_info,
                "roles": user_info,
                "connection_string": f"postgresql://{self.user}:***@{self.host}:{self.port}/{self.database}"
            }
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {"error": str(e)}
    
    async def create_user(self, email: str, password_hash: str, display_name: str = None) -> str:
        """Create a new user"""
        try:
            user_id = await self.execute_scalar("""
                INSERT INTO users (uid, email, display_name, password_hash, is_active)
                VALUES (gen_random_uuid()::text, $1, $2, $3, true)
                RETURNING uid
            """, email, display_name, password_hash)
            return user_id
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            users = await self.execute_query(
                "SELECT * FROM users WHERE email = $1 AND deleted_at IS NULL",
                email
            )
            return users[0] if users else None
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            raise
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            users = await self.execute_query(
                "SELECT * FROM users WHERE uid = $1 AND deleted_at IS NULL",
                user_id
            )
            return users[0] if users else None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            raise
    
    async def create_conversation(self, user_id: str, title: str) -> str:
        """Create a new conversation"""
        try:
            conversation_id = await self.execute_scalar("""
                INSERT INTO conversations (id, uid, title, message_count)
                VALUES (gen_random_uuid()::text, $1, $2, 0)
                RETURNING id
            """, user_id, title)
            return conversation_id
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise
    
    async def add_message(self, conversation_id: str, user_id: str, role: str, content: str, 
                         token_count: int = None, model_used: str = None) -> str:
        """Add a message to a conversation"""
        try:
            message_id = await self.execute_scalar("""
                INSERT INTO messages (id, conversation_id, uid, role, content, token_count, model_used)
                VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6)
                RETURNING id
            """, conversation_id, user_id, role, content, token_count, model_used)
            
            # Update conversation message count and last message time
            await self.execute_command("""
                UPDATE conversations 
                SET 
                    message_count = message_count + 1,
                    last_message_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """, conversation_id)
            
            return message_id
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            raise
    
    async def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        try:
            return await self.execute_query("""
                SELECT * FROM messages 
                WHERE conversation_id = $1 
                ORDER BY created_at ASC
            """, conversation_id)
        except Exception as e:
            logger.error(f"Error getting conversation messages: {e}")
            raise
    
    async def get_user_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all conversations for a user"""
        try:
            return await self.execute_query("""
                SELECT * FROM conversations 
                WHERE uid = $1 
                ORDER BY updated_at DESC
            """, user_id)
        except Exception as e:
            logger.error(f"Error getting user conversations: {e}")
            raise

# Global instance
postgres_service = PostgreSQLService()
