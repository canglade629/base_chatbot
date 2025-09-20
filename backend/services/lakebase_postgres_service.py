"""
Databricks Lakebase PostgreSQL Service for base-chatbot
Provides database connection and operations using Databricks managed PostgreSQL
"""
import os
import asyncio
import httpx
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class LakebasePostgreSQLService:
    """Databricks Lakebase PostgreSQL service using SQL warehouse API"""
    
    def __init__(self):
        self.host = os.getenv('DATABRICKS_HOST')
        self.token = os.getenv('DATABRICKS_TOKEN')
        self.catalog = os.getenv('LAKEBASE_CATALOG', 'base_chatbot')
        self.schema = os.getenv('LAKEBASE_SCHEMA', 'base_chatbot')
        self.database = os.getenv('LAKEBASE_DATABASE', 'base_chatbot')
        
        # SQL warehouse for executing queries
        self.warehouse_id = None
        
        logger.info(f"Lakebase PostgreSQL service initialized for catalog: {self.catalog}")
        logger.info(f"Using schema: {self.schema}")
    
    async def initialize(self) -> bool:
        """Initialize the service by getting a SQL warehouse"""
        try:
            # Get available SQL warehouses
            warehouses_result = await self._make_request("/api/2.0/sql/warehouses")
            if not warehouses_result["success"]:
                logger.error(f"Failed to get warehouses: {warehouses_result.get('error')}")
                return False
            
            warehouses = warehouses_result["data"].get("warehouses", [])
            if not warehouses:
                logger.error("No SQL warehouses found")
                return False
            
            # Find a running warehouse or start one
            for warehouse in warehouses:
                if warehouse.get("state") == "RUNNING":
                    self.warehouse_id = warehouse["id"]
                    logger.info(f"Using running warehouse: {warehouse['name']} (ID: {self.warehouse_id})")
                    return True
            
            # If no running warehouse, try to start the first one
            warehouse = warehouses[0]
            logger.info(f"Starting warehouse: {warehouse['name']} (ID: {warehouse['id']})")
            
            start_result = await self._make_request(
                f"/api/2.0/sql/warehouses/{warehouse['id']}/start",
                method="POST"
            )
            
            if start_result["success"]:
                self.warehouse_id = warehouse["id"]
                logger.info("Warehouse started successfully")
                return True
            else:
                logger.error(f"Failed to start warehouse: {start_result.get('error')}")
                return False
        except Exception as e:
            logger.error(f"Error initializing Lakebase PostgreSQL service: {e}")
            return False
    
    async def _make_request(self, endpoint: str, method: str = "GET", data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make HTTP request to Databricks API"""
        try:
            url = f"{self.host}{endpoint}"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            if method == "GET":
                response = await httpx.AsyncClient().get(url, headers=headers, params=data, timeout=30)
            elif method == "POST":
                response = await httpx.AsyncClient().post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = await httpx.AsyncClient().put(url, headers=headers, json=data, timeout=30)
            elif method == "DELETE":
                response = await httpx.AsyncClient().delete(url, headers=headers, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False, 
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_sql(self, sql: str) -> Dict[str, Any]:
        """Execute a SQL statement using the SQL warehouse"""
        if not self.warehouse_id:
            return {"success": False, "error": "No SQL warehouse available"}
        
        try:
            # Create statement
            statement_data = {
                "warehouse_id": self.warehouse_id,
                "statement": sql,
                "wait_timeout": "30s"
            }
            
            create_result = await self._make_request("/api/2.0/sql/statements", method="POST", data=statement_data)
            if not create_result["success"]:
                return create_result
            
            statement_id = create_result["data"]["statement_id"]
            
            # Wait for completion
            max_attempts = 30
            for attempt in range(max_attempts):
                await asyncio.sleep(2)
                
                status_result = await self._make_request(f"/api/2.0/sql/statements/{statement_id}")
                if not status_result["success"]:
                    return status_result
                
                status = status_result["data"]["status"]["state"]
                if status == "SUCCEEDED":
                    return {"success": True, "data": status_result["data"]}
                elif status in ["FAILED", "CANCELLED"]:
                    return {
                        "success": False,
                        "error": status_result["data"]["status"].get("error", "Statement failed")
                    }
            
            return {"success": False, "error": "Statement execution timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def check_connection(self) -> bool:
        """Check if the database connection is working"""
        try:
            result = await self._execute_sql(f"SELECT 1 as test FROM {self.catalog}.{self.schema}.system_config LIMIT 1")
            return result["success"]
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information"""
        try:
            # Get database and schema info
            db_info_result = await self._execute_sql(f"SELECT current_catalog(), current_schema()")
            if not db_info_result["success"]:
                return {"error": "Failed to get database info"}
            
            # Get table information
            tables_result = await self._execute_sql(f"""
                SELECT table_name, table_type
                FROM {self.catalog}.information_schema.tables 
                WHERE table_schema = '{self.schema}'
                ORDER BY table_name
            """)
            
            tables_info = []
            if tables_result["success"] and "result" in tables_result["data"]:
                tables_info = tables_result["data"]["result"]["data_array"]
            
            return {
                "catalog": self.catalog,
                "schema": self.schema,
                "database": self.database,
                "tables_count": len(tables_info),
                "tables": tables_info,
                "connection_type": "Databricks Lakebase PostgreSQL"
            }
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {"error": str(e)}
    
    async def create_user(self, email: str, password_hash: str, display_name: str = None) -> str:
        """Create a new user"""
        try:
            sql = f"""
                INSERT INTO {self.catalog}.{self.schema}.users (uid, email, display_name, password_hash, is_active)
                VALUES (uuid()::string, '{email}', '{display_name or ''}', '{password_hash}', true)
                RETURNING uid
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"]:
                return result["data"]["result"]["data_array"][0][0]
            else:
                raise Exception(result.get("error", "Failed to create user"))
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            sql = f"""
                SELECT uid, email, display_name, password_hash, is_active, created_at, last_login, deleted_at, updated_at
                FROM {self.catalog}.{self.schema}.users 
                WHERE email = '{email}' AND deleted_at IS NULL
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"] and result["data"]["result"]["data_array"]:
                row = result["data"]["result"]["data_array"][0]
                return {
                    "uid": row[0],
                    "email": row[1],
                    "display_name": row[2],
                    "password_hash": row[3],
                    "is_active": row[4],
                    "created_at": row[5],
                    "last_login": row[6],
                    "deleted_at": row[7],
                    "updated_at": row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            raise
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            sql = f"""
                SELECT uid, email, display_name, password_hash, is_active, created_at, last_login, deleted_at, updated_at
                FROM {self.catalog}.{self.schema}.users 
                WHERE uid = '{user_id}' AND deleted_at IS NULL
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"] and result["data"]["result"]["data_array"]:
                row = result["data"]["result"]["data_array"][0]
                return {
                    "uid": row[0],
                    "email": row[1],
                    "display_name": row[2],
                    "password_hash": row[3],
                    "is_active": row[4],
                    "created_at": row[5],
                    "last_login": row[6],
                    "deleted_at": row[7],
                    "updated_at": row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            raise
    
    async def create_conversation(self, user_id: str, title: str) -> str:
        """Create a new conversation"""
        try:
            sql = f"""
                INSERT INTO {self.catalog}.{self.schema}.conversations (id, uid, title, message_count)
                VALUES (uuid()::string, '{user_id}', '{title}', 0)
                RETURNING id
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"]:
                return result["data"]["result"]["data_array"][0][0]
            else:
                raise Exception(result.get("error", "Failed to create conversation"))
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise
    
    async def add_message(self, conversation_id: str, user_id: str, role: str, content: str, 
                         token_count: int = None, model_used: str = None) -> str:
        """Add a message to a conversation"""
        try:
            sql = f"""
                INSERT INTO {self.catalog}.{self.schema}.messages (id, conversation_id, uid, role, content, token_count, model_used)
                VALUES (uuid()::string, '{conversation_id}', '{user_id}', '{role}', '{content}', {token_count or 'NULL'}, '{model_used or ''}')
                RETURNING id
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"]:
                message_id = result["data"]["result"]["data_array"][0][0]
                
                # Update conversation message count and last message time
                update_sql = f"""
                    UPDATE {self.catalog}.{self.schema}.conversations 
                    SET 
                        message_count = message_count + 1,
                        last_message_at = current_timestamp(),
                        updated_at = current_timestamp()
                    WHERE id = '{conversation_id}'
                """
                await self._execute_sql(update_sql)
                
                return message_id
            else:
                raise Exception(result.get("error", "Failed to add message"))
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            raise
    
    async def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        try:
            sql = f"""
                SELECT id, conversation_id, uid, role, content, created_at, metadata, token_count, model_used
                FROM {self.catalog}.{self.schema}.messages 
                WHERE conversation_id = '{conversation_id}' 
                ORDER BY created_at ASC
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"]:
                messages = []
                for row in result["data"]["result"]["data_array"]:
                    messages.append({
                        "id": row[0],
                        "conversation_id": row[1],
                        "uid": row[2],
                        "role": row[3],
                        "content": row[4],
                        "created_at": row[5],
                        "metadata": row[6],
                        "token_count": row[7],
                        "model_used": row[8]
                    })
                return messages
            return []
        except Exception as e:
            logger.error(f"Error getting conversation messages: {e}")
            raise
    
    async def get_user_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all conversations for a user"""
        try:
            sql = f"""
                SELECT id, uid, title, created_at, updated_at, message_count, last_message_at
                FROM {self.catalog}.{self.schema}.conversations 
                WHERE uid = '{user_id}' 
                ORDER BY updated_at DESC
            """
            result = await self._execute_sql(sql)
            if result["success"] and "result" in result["data"]:
                conversations = []
                for row in result["data"]["result"]["data_array"]:
                    conversations.append({
                        "id": row[0],
                        "uid": row[1],
                        "title": row[2],
                        "created_at": row[3],
                        "updated_at": row[4],
                        "message_count": row[5],
                        "last_message_at": row[6]
                    })
                return conversations
            return []
        except Exception as e:
            logger.error(f"Error getting user conversations: {e}")
            raise

# Global instance
lakebase_postgres_service = LakebasePostgreSQLService()
