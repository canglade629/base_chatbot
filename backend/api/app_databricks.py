from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import sys
import logging
import uuid
import requests
from datetime import datetime
from contextlib import asynccontextmanager
from .model_serving_utils import query_endpoint, is_endpoint_supported

# Add the backend directory to the Python path for Databricks Apps
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Re-enable database integration for Lakebase
from config.database import init_engine, check_database_exists, start_token_refresh, stop_token_refresh
from services.user_service import get_or_create_user
from services.conversation_service import (
    get_user_conversations, 
    create_conversation as create_conversation_service, 
    update_conversation as update_conversation_service, 
    delete_conversation as delete_conversation_service, 
    cleanup_empty_conversations
)
from utils.oauth_utils import get_user_email_from_token, get_user_info_from_token

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Read workspace info from env (Databricks Apps automatically sets these)
DATABRICKS_WORKSPACE_URL = os.getenv("DATABRICKS_WORKSPACE_URL")  # e.g. https://adb-1234567890.12.azuredatabricks.net
MODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT")  # e.g. databricks-meta-llama-3-70b-instruct

# Get serving endpoint from environment
SERVING_ENDPOINT = MODEL_ENDPOINT or os.getenv('SERVING_ENDPOINT')

assert SERVING_ENDPOINT, \
    ("Unable to determine serving endpoint to use for chatbot app. If developing locally, "
     "set the MODEL_ENDPOINT or SERVING_ENDPOINT environment variable to the name of your serving endpoint. If "
     "deploying to a Databricks app, include a serving endpoint resource named "
     "'serving_endpoint' with CAN_QUERY permissions, as described in "
     "https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app#deploy-the-databricks-app")

# Check if the endpoint is supported
endpoint_supported = is_endpoint_supported(SERVING_ENDPOINT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with Lakebase integration"""
    # Startup
    logger.info("🚀 Starting Danone Onesource 2.0 Assistant...")
    
    try:
        logger.info("🔍 Attempting to initialize database connection...")
        
        # Always try to initialize the database engine
        # The check_database_exists() might fail due to permissions, but the actual connection might work
        try:
            init_engine()
            logger.info("✅ Database engine initialized successfully")
            
            # Ensure tables exist
            from config.database import ensure_database_tables
            tables_created = await ensure_database_tables()
            if tables_created:
                logger.info("✅ Database tables ensured")
            else:
                logger.warning("⚠️ Failed to ensure database tables")
            
            # Start background token refresh only if using OAuth approach
            from config.database import database_instance
            if database_instance is not None:
                await start_token_refresh()
                logger.info("✅ Application started with Lakebase connection and token refresh")
            else:
                logger.info("✅ Application started with Lakebase connection (static credentials)")
                
        except Exception as db_init_error:
            logger.warning(f"⚠️ Database initialization failed: {db_init_error}")
            logger.info("💡 Continuing without database - conversation history will be disabled")
            logger.info("💡 This is normal if Lakebase is not configured or accessible")
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.warning("⚠️ Continuing without database - conversation history disabled")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down application...")
    try:
        await stop_token_refresh()
    except Exception as e:
        logger.error(f"Error during token refresh shutdown: {e}")
    logger.info("✅ Application shutdown complete")

app = FastAPI(
    title="Danone Onesource 2.0 Assistant",
    description="AI-powered assistant with Onesource documentation and conversation history",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
frontend_static_path = os.path.join(os.path.dirname(__file__), "../../frontend/static")
if os.path.exists(frontend_static_path):
    app.mount("/static", StaticFiles(directory=frontend_static_path), name="static")
    logger.info(f"✅ Static files mounted from: {frontend_static_path}")
else:
    logger.warning(f"❌ Static directory not found: {frontend_static_path}")
    # Try alternative path for deployed environment
    alt_static_path = os.path.join(os.getcwd(), "frontend/static")
    if os.path.exists(alt_static_path):
        app.mount("/static", StaticFiles(directory=alt_static_path), name="static")
        logger.info(f"✅ Static files mounted from alternative path: {alt_static_path}")
    else:
        logger.error(f"❌ Alternative static directory also not found: {alt_static_path}")

frontend_js_path = os.path.join(os.path.dirname(__file__), "../../frontend/js")
if os.path.exists(frontend_js_path):
    app.mount("/js", StaticFiles(directory=frontend_js_path), name="js")

# In-memory conversation storage (fallback until Lakebase is set up)
conversations_storage = {}
users_storage = {}

# Mock database flag - set to True to disable database operations
MOCK_DATABASE = False

# Mock functions for database operations
async def mock_get_or_create_user(email: str, display_name: str = None, username: str = None):
    """Mock user creation/retrieval"""
    if email not in users_storage:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        users_storage[email] = {
            "id": user_id,
            "email": email,
            "display_name": display_name or email.split('@')[0],
            "username": username or email.split('@')[0],
            "last_login": datetime.now().isoformat()
        }
    else:
        # Update last login
        users_storage[email]["last_login"] = datetime.now().isoformat()
    
    return users_storage[email]

async def mock_create_conversation(user_email: str, title: str, messages: list = None):
    """Mock conversation creation"""
    import time
    import random
    conversation_id = f"conv_{int(time.time() * 1000)}_{random.randint(100000000, 999999999)}"
    now = datetime.now().isoformat()
    
    conversation = {
        "id": conversation_id,
        "title": title,
        "user_email": user_email,
        "messages": messages or [],
        "created_at": now,
        "updated_at": now
    }
    
    conversations_storage[conversation_id] = conversation
    logger.info(f"Mock: Created conversation {conversation_id} for user {user_email}")
    return conversation

async def mock_update_conversation(conversation_id: str, user_email: str, title: str = None, messages: list = None):
    """Mock conversation update"""
    conversation = conversations_storage.get(conversation_id)
    
    if not conversation or conversation.get('user_email') != user_email:
        return None
    
    if title is not None:
        conversation['title'] = title
    if messages is not None:
        conversation['messages'] = messages
    
    conversation['updated_at'] = datetime.now().isoformat()
    logger.info(f"Mock: Updated conversation {conversation_id}")
    return conversation

async def mock_get_user_conversations(user_email: str):
    """Mock get user conversations"""
    user_conversations = [conv for conv in conversations_storage.values() if conv.get('user_email') == user_email]
    user_conversations.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return user_conversations

async def mock_delete_conversation(conversation_id: str, user_email: str):
    """Mock conversation deletion"""
    conversation = conversations_storage.get(conversation_id)
    
    if not conversation or conversation.get('user_email') != user_email:
        return False
    
    del conversations_storage[conversation_id]
    logger.info(f"Mock: Deleted conversation {conversation_id}")
    return True

async def mock_cleanup_empty_conversations(user_email: str):
    """Mock cleanup empty conversations"""
    empty_conversation_ids = []
    for conv_id, conv in conversations_storage.items():
        if (conv.get('user_email') == user_email and 
            (not conv.get('messages') or len(conv.get('messages', [])) == 0)):
            empty_conversation_ids.append(conv_id)

    deleted_count = 0
    for conv_id in empty_conversation_ids:
        del conversations_storage[conv_id]
        deleted_count += 1

    logger.info(f"Mock: Cleaned up {deleted_count} empty conversations for user {user_email}")
    return deleted_count

@app.get("/conversations")
async def get_conversations(request: Request):
    """Get all conversations for a user"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Debug logging
        logger.info(f"GET /conversations - Headers: {dict(request.headers)}")
        logger.info(f"X-Forwarded-Access-Token present: {bool(user_token)}")
        if user_token:
            logger.info(f"Token length: {len(user_token)}")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            logger.warning("No user email found for conversations")
            return {"conversations": []}
        
        if MOCK_DATABASE:
            # Use mock functions
            conversations = await mock_get_user_conversations(user_email)
            return {"conversations": conversations}
        else:
            # Try Lakebase first - always try database, don't check if it exists
            try:
                conversations = await get_user_conversations(user_email)
                logger.info(f"Retrieved {len(conversations)} conversations for user {user_email}")
                logger.info(f"Conversation IDs: {[conv.get('id') for conv in conversations]}")
                return {"conversations": conversations}
            except Exception as db_error:
                logger.error(f"Database error in get conversations: {db_error}")
                
                # Try to initialize database engine if it's not initialized
                try:
                    from config.database import engine
                    if engine is None:
                        logger.info("Database engine not initialized, attempting to initialize...")
                        init_engine()
                        # Try again after initialization
                        conversations = await get_user_conversations(user_email)
                        return {"conversations": conversations}
                except Exception as init_error:
                    logger.error(f"Failed to initialize database engine: {init_error}")
                
                # Fall back to in-memory storage if database fails
                user_conversations = [conv for conv in conversations_storage.values() if conv.get('user_email') == user_email]
                user_conversations.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
                return {"conversations": user_conversations}
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return {"conversations": []}

@app.post("/conversations")
async def create_conversation(conversation_data: dict, request: Request):
    """Create a new conversation"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Log all headers for debugging
        logger.info(f"Create conversation request headers: {dict(request.headers)}")
        logger.info(f"Create conversation request body: {conversation_data}")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            logger.error("No user email found in request")
            raise HTTPException(status_code=400, detail="User email not found in request")
        
        # Try Lakebase database first
        try:
            logger.info(f"Creating conversation for user: {user_email}")
            
            # Create or get user first
            user = await get_or_create_user(user_email)
            if not user:
                logger.error(f"Failed to create or retrieve user: {user_email}")
                raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
            
            logger.info(f"User created/retrieved: {user.id}")
            
            conversation = await create_conversation_service(
                user_email=user_email,
                title=conversation_data.get("title", "New Conversation"),
                messages=conversation_data.get("messages", []),
                conversation_id=conversation_data.get("id")
            )
            
            if not conversation:
                logger.error(f"Failed to create conversation for user: {user_email}")
                raise HTTPException(status_code=500, detail="Failed to create conversation")
            
            logger.info(f"Conversation created successfully: {conversation.get('id')}")
            return conversation
            
        except Exception as db_error:
            logger.error(f"Database error in conversation creation: {db_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Fall back to in-memory storage if database fails
            import time
            import random
            conversation_id = f"conv_{int(time.time() * 1000)}_{random.randint(100000000, 999999999)}"
            now = datetime.now().isoformat()
            
            # Store user info
            if user_email not in users_storage:
                users_storage[user_email] = {
                    "id": f"user_{uuid.uuid4().hex[:8]}",
                    "email": user_email,
                    "display_name": user_email.split('@')[0],
                    "created_at": now,
                    "last_login": now
                }
            
            conversation = {
                "id": conversation_id,
                "title": conversation_data.get("title", "New Conversation"),
                "user_email": user_email,
                "messages": conversation_data.get("messages", []),
                "created_at": now,
                "updated_at": now
            }
            
            conversations_storage[conversation_id] = conversation
            logger.warning(f"Using fallback storage for conversation: {conversation_id}")
            return conversation
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

@app.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, conversation_data: dict, request: Request):
    """Update a conversation"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not found in request")
        
        # Try Lakebase database first
        try:
            logger.info(f"Updating conversation {conversation_id} for user: {user_email}")
            logger.info(f"Conversation data received: {conversation_data}")
            
            conversation = await update_conversation_service(
                conversation_id=conversation_id,
                user_email=user_email,
                title=conversation_data.get('title'),
                messages=conversation_data.get('messages')
            )
            
            if not conversation:
                logger.error(f"Conversation not found: {conversation_id} for user: {user_email}")
                # Let's check if the user exists and what conversations they have
                from services.conversation_service import get_user_conversations
                user_conversations = await get_user_conversations(user_email)
                logger.info(f"User {user_email} has {len(user_conversations)} conversations")
                logger.info(f"Available conversation IDs: {[conv.get('id') for conv in user_conversations]}")
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            logger.info(f"Conversation updated successfully: {conversation_id}")
            return conversation
            
        except Exception as db_error:
            logger.error(f"Database error in conversation update: {db_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Fall back to in-memory storage if database fails
            conversation = conversations_storage.get(conversation_id)
            
            if not conversation or conversation.get('user_email') != user_email:
                logger.error(f"Conversation not found in fallback storage: {conversation_id}")
                raise HTTPException(status_code=404, detail="Conversation not found")

            if 'title' in conversation_data:
                conversation['title'] = conversation_data['title']
            if 'messages' in conversation_data:
                conversation['messages'] = conversation_data['messages']
            
            conversation['updated_at'] = datetime.now().isoformat()
            logger.warning(f"Using fallback storage for conversation update: {conversation_id}")
            return conversation
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation")

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    """Delete a conversation"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not found in request")
        
        # Try Lakebase first - always try database, don't check if it exists
        try:
            success = await delete_conversation_service(conversation_id, user_email)
            
            if not success:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            return {"message": "Conversation deleted successfully", "id": conversation_id}
        except Exception as db_error:
            logger.error(f"Database error in delete conversation: {db_error}")
            # Fall back to in-memory storage if database fails
            # Fallback to in-memory storage
            conversation = conversations_storage.get(conversation_id)
            
            if not conversation or conversation.get('user_email') != user_email:
                raise HTTPException(status_code=404, detail="Conversation not found")

            del conversations_storage[conversation_id]
            return {"message": "Conversation deleted successfully", "id": conversation_id}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")

@app.post("/conversations/cleanup")
async def cleanup_conversations(request: Request):
    """Clean up empty conversations"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not found in request")
        
        # Try Lakebase first - always try database, don't check if it exists
        try:
            deleted_count = await cleanup_empty_conversations(user_email)
            return {"message": f"Cleaned up {deleted_count} empty conversations", "deleted_count": deleted_count}
        except Exception as db_error:
            logger.error(f"Database error in cleanup conversations: {db_error}")
            # Fall back to in-memory storage if database fails
            # Fallback to in-memory storage
            empty_conversation_ids = []
            for conv_id, conv in conversations_storage.items():
                if (conv.get('user_email') == user_email and 
                    (not conv.get('messages') or len(conv.get('messages', [])) == 0)):
                    empty_conversation_ids.append(conv_id)

            deleted_count = 0
            for conv_id in empty_conversation_ids:
                del conversations_storage[conv_id]
                deleted_count += 1

            return {"message": f"Cleaned up {deleted_count} empty conversations", "deleted_count": deleted_count}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up conversations: {e}")
        return {"message": "Failed to cleanup conversations", "deleted_count": 0}

# Pydantic models
class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

async def query_llm(message: str, history: list = None, user_token: str = None) -> str:
    """
    Query the LLM with the given message and chat history.
    `message`: str - the latest user input.
    `history`: list of tuples - (user_msg, assistant_msg) pairs.
    `user_token`: str - user's access token for serving endpoint authentication.
    """
    if not message.strip():
        return "ERROR: The question should not be empty"

    # Convert from history format to OpenAI-style messages
    message_history = []
    if history:
        for user_msg, assistant_msg in history:
            message_history.append({"role": "user", "content": user_msg})
            message_history.append({"role": "assistant", "content": assistant_msg})

    # Add the latest user message
    message_history.append({"role": "user", "content": message})

    try:
        logger.info(f"Querying model endpoint: {SERVING_ENDPOINT}")
        response = await query_endpoint(
            endpoint_name=SERVING_ENDPOINT,
            messages=message_history,
            max_tokens=1000
        )
        return response["content"]
    except Exception as e:
        logger.error(f"Error querying model: {str(e)}", exc_info=True)
        return f"Error: {str(e)}"

# Health check endpoint with database status
@app.get("/health")
async def health_check():
    from config.database import database_health, check_database_exists
    
    database_exists = check_database_exists()
    database_healthy = False
    
    if database_exists:
        try:
            database_healthy = await database_health()
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
    
    return {
        "status": "healthy" if database_healthy else "degraded",
        "message": "Service is running",
        "timestamp": "2024-01-01T00:00:00Z",
        "environment": "databricks-apps",
        "database": {
            "exists": database_exists,
            "healthy": database_healthy,
            "conversation_history": database_healthy,
            "lakebase_id": "cc424808-7c73-4954-af28-539b992b0587"
        }
    }

# Debug endpoint to see raw user info
@app.get("/debug/user")
async def debug_user_info():
    """Debug endpoint to see raw user information"""
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        current_user = w.current_user.me()
        
        return {
            "raw_user": str(current_user),
            "user_name": current_user.user_name,
            "display_name": current_user.display_name,
            "user_id": str(current_user.id),
            "groups": [str(group) for group in current_user.groups] if current_user.groups else [],
            "roles": [str(role) for role in current_user.roles] if current_user.roles else [],
            "all_attributes": dir(current_user)
        }
    except Exception as e:
        return {"error": str(e)}

# Debug endpoint to test token retrieval
@app.get("/debug/token")
async def debug_token():
    """Debug endpoint to test app token retrieval"""
    try:
        from .model_serving_utils import get_databricks_token
        token = get_databricks_token()
        return {
            "token_length": len(token),
            "token_preview": f"{token[:20]}...{token[-20:]}" if len(token) > 40 else token,
            "token_type": type(token).__name__,
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to test OAuth token extraction
@app.get("/debug/oauth")
async def debug_oauth(request: Request):
    """Debug endpoint to test OAuth token extraction"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Get all headers for debugging
        all_headers = dict(request.headers)
        
        if not user_token:
            return {
                "error": "No X-Forwarded-Access-Token header found",
                "all_headers": all_headers,
                "success": False
            }
        
        # Extract user email from OAuth token
        user_email = get_user_email_from_token(user_token)
        user_info = get_user_info_from_token(user_token)
        
        return {
            "user_token_present": True,
            "user_token_length": len(user_token),
            "user_token_preview": f"{user_token[:20]}...{user_token[-20:]}" if len(user_token) > 40 else user_token,
            "user_email": user_email,
            "user_info": user_info,
            "all_headers": all_headers,
            "success": user_email is not None
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Simple test endpoint to verify OAuth token is being received
@app.get("/debug/headers")
async def debug_headers(request: Request):
    """Debug endpoint to check if OAuth headers are being received"""
    try:
        all_headers = dict(request.headers)
        
        # Check for various OAuth-related headers
        oauth_headers = {
            "X-Forwarded-Access-Token": request.headers.get("X-Forwarded-Access-Token"),
            "X-Forwarded-Email": request.headers.get("X-Forwarded-Email"),
            "Authorization": request.headers.get("Authorization"),
            "X-Databricks-User": request.headers.get("X-Databricks-User"),
            "X-Databricks-User-Id": request.headers.get("X-Databricks-User-Id"),
        }
        
        return {
            "all_headers": all_headers,
            "oauth_headers": oauth_headers,
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to check database connection
@app.get("/debug/database")
async def debug_database():
    """Debug endpoint to check database connection and operations"""
    try:
        from config.database import get_async_db, check_database_exists, ensure_database_tables
        from sqlalchemy import text
        
        # Check database health
        db_health = check_database_exists()
        
        # Test database operations
        user_creation = None
        conversation_creation = None
        table_creation = None
        
        if db_health:
            try:
                # Test table creation
                table_creation = await ensure_database_tables()
                
                # Test user creation
                async for db in get_async_db():
                    # Test a simple query
                    result = await db.execute(text("SELECT 1 as test"))
                    test_value = result.scalar()
                    
                    # Test user creation
                    from services.user_service import create_user
                    user = await create_user("test@example.com")
                    user_creation = {
                        "success": True,
                        "user_id": user.id if user else None,
                        "email": user.email if user else None
                    }
                    
                    # Test conversation creation
                    from services.conversation_service import create_conversation
                    conversation = await create_conversation("test@example.com", "Test Conversation", [])
                    conversation_creation = {
                        "success": True,
                        "conversation_id": conversation.id if conversation else None,
                        "title": conversation.title if conversation else None
                    }
                    break
                    
            except Exception as e:
                logger.error(f"Database operations test failed: {e}")
                user_creation = {"success": False, "error": str(e)}
                conversation_creation = {"success": False, "error": str(e)}
        
        return {
            "database_health": db_health,
            "table_creation": {"success": table_creation} if table_creation is not None else None,
            "user_creation": user_creation,
            "conversation_creation": conversation_creation,
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to check OAuth token
@app.get("/debug/oauth")
async def debug_oauth(request: Request):
    """Debug endpoint to check OAuth token extraction"""
    try:
        # Get the OAuth token from headers
        user_token = request.headers.get('X-Forwarded-Access-Token')
        
        if not user_token:
            return {
                "error": "No X-Forwarded-Access-Token header found",
                "success": False
            }
        
        # Try to extract user email
        user_email = get_user_email_from_token(user_token)
        user_info = get_user_info_from_token(user_token)
        
        return {
            "token_found": True,
            "token_length": len(user_token),
            "token_preview": user_token[:20] + "..." if len(user_token) > 20 else user_token,
            "user_email": user_email,
            "user_info": user_info,
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to test database connection
@app.get("/debug/db-connection")
async def debug_db_connection():
    """Debug endpoint to test database connection using the simplified approach"""
    try:
        from config.database import get_async_db, check_database_exists, engine
        from sqlalchemy import text
        
        # Check if database is accessible
        db_health = check_database_exists()
        
        if not db_health:
            return {
                "error": "Database connection failed",
                "connection_url": str(engine.url) if engine else "No engine",
                "success": False
            }
        
        # Test a simple query
        async for db in get_async_db():
            result = await db.execute(text("SELECT 1 as test, current_database() as db_name, current_user as db_user"))
            row = result.fetchone()
            
            return {
                "connection_test": row[0] if row else None,
                "database_name": row[1] if row else None,
                "database_user": row[2] if row else None,
                "connection_url": str(engine.url) if engine else "No engine",
                "success": True
            }
            
    except Exception as e:
        return {
            "error": str(e),
            "connection_url": str(engine.url) if engine else "No engine",
            "success": False
        }

# Debug endpoint to check if tables exist
@app.get("/debug/tables")
async def debug_tables():
    """Debug endpoint to check if database tables exist"""
    try:
        from sqlalchemy import text
        from config.database import get_async_db
        
        async for db in get_async_db():
            # Check if users table exists
            users_check = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                );
            """))
            users_exists = users_check.scalar()
            
            # Check if conversations table exists
            conversations_check = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'conversations'
                );
            """))
            conversations_exists = conversations_check.scalar()
            
            # Get table counts
            users_count = 0
            conversations_count = 0
            
            if users_exists:
                users_count_result = await db.execute(text("SELECT COUNT(*) FROM users"))
                users_count = users_count_result.scalar()
            
            if conversations_exists:
                conversations_count_result = await db.execute(text("SELECT COUNT(*) FROM conversations"))
                conversations_count = conversations_count_result.scalar()
            
            return {
                "users_table_exists": users_exists,
                "conversations_table_exists": conversations_exists,
                "users_count": users_count,
                "conversations_count": conversations_count,
                "success": True
            }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to check environment variables
@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment variables"""
    import os
    env_vars = [
        'DATABRICKS_TOKEN',
        'DATABRICKS_ACCESS_TOKEN', 
        'ACCESS_TOKEN',
        'APP_TOKEN',
        'DATABRICKS_WORKSPACE_URL',
        'DATABRICKS_HOST',
        'SERVING_ENDPOINT'
    ]
    
    result = {}
    for var in env_vars:
        value = os.getenv(var)
        if value:
            if 'TOKEN' in var:
                result[var] = f"{value[:20]}...{value[-20:]}" if len(value) > 40 else value
            else:
                result[var] = value
        else:
            result[var] = "Not set"
    
    return result

# Debug endpoint to test serving endpoint directly
@app.get("/debug/serving")
async def debug_serving():
    """Debug endpoint to test serving endpoint directly"""
    try:
        from .model_serving_utils import _query_endpoint
        result = await _query_endpoint('databricks-gpt-oss-20b', [{'role': 'user', 'content': 'Hello, test message'}], 50)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Debug endpoint to test database connection
@app.get("/debug/database")
async def debug_database():
    """Debug endpoint to test database connection"""
    try:
        from config.database import database_health, get_fresh_database_token
        from services.user_service import get_or_create_user
        from services.conversation_service import create_conversation as create_conversation_service
        
        # Test database health
        db_healthy = await database_health()
        
        # Test token retrieval
        try:
            token = get_fresh_database_token()
            token_info = {
                "success": True,
                "length": len(token),
                "preview": f"{token[:20]}...{token[-20:]}" if len(token) > 40 else token
            }
        except Exception as token_error:
            token_info = {
                "success": False,
                "error": str(token_error)
            }
        
        # Test user creation
        try:
            user = await get_or_create_user("test@example.com")
            user_info = {
                "success": True,
                "user_id": user.id if user else None,
                "email": user.email if user else None
            }
        except Exception as user_error:
            user_info = {
                "success": False,
                "error": str(user_error)
            }
        
        # Test table creation
        try:
            from config.database import ensure_database_tables
            tables_created = await ensure_database_tables()
            table_info = {
                "success": tables_created,
                "message": "Tables ensured" if tables_created else "Failed to ensure tables"
            }
        except Exception as table_error:
            table_info = {
                "success": False,
                "error": str(table_error)
            }
        
        # Test conversation creation
        try:
            conversation = await create_conversation_service(
                user_email="test@example.com",
                title="Test Conversation",
                messages=[{"role": "user", "content": "Test message"}]
            )
            conversation_info = {
                "success": True,
                "conversation_id": conversation.get("id") if conversation else None,
                "title": conversation.get("title") if conversation else None
            }
        except Exception as conv_error:
            conversation_info = {
                "success": False,
                "error": str(conv_error)
            }
        
        return {
            "database_health": db_healthy,
            "token_info": token_info,
            "table_creation": table_info,
            "user_creation": user_info,
            "conversation_creation": conversation_info
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Simple test endpoint
@app.get("/debug/test")
async def debug_test():
    """Simple test endpoint to verify backend is working"""
    return {"message": "Backend is working!", "timestamp": "2024-01-01T00:00:00Z"}

# Debug endpoint to check static files
@app.get("/debug/static")
async def debug_static():
    """Debug endpoint to check static file serving"""
    import os
    
    # Check if static directory exists
    frontend_static_path = os.path.join(os.path.dirname(__file__), "../../frontend/static")
    static_exists = os.path.exists(frontend_static_path)
    
    # Check if logo file exists
    logo_path = os.path.join(frontend_static_path, "onesource-logo.png")
    logo_exists = os.path.exists(logo_path)
    
    # List files in static directory
    static_files = []
    if static_exists:
        try:
            static_files = os.listdir(frontend_static_path)
        except Exception as e:
            static_files = [f"Error listing files: {e}"]
    
    return {
        "static_directory_exists": static_exists,
        "static_directory_path": frontend_static_path,
        "logo_file_exists": logo_exists,
        "logo_file_path": logo_path,
        "static_files": static_files,
        "current_working_directory": os.getcwd(),
        "script_directory": os.path.dirname(__file__)
    }

@app.get("/debug/serving-test")
async def debug_serving_test():
    """Debug serving endpoint with a simple test"""
    try:
        from .model_serving_utils import query_endpoint
        
        # Simple test message
        test_messages = [{"role": "user", "content": "Hello, how are you?"}]
        
        logger.info("🧪 Testing serving endpoint...")
        response = await query_endpoint(
            endpoint_name=SERVING_ENDPOINT,
            messages=test_messages,
            max_tokens=100
        )
        
        return {
            "status": "success",
            "response": response,
            "response_type": str(type(response)),
            "endpoint": SERVING_ENDPOINT
        }
    except Exception as e:
        logger.error(f"❌ Debug serving test failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "error_type": str(type(e)),
            "endpoint": SERVING_ENDPOINT
        }

@app.get("/debug/token-test")
async def debug_token_test():
    """Debug token retrieval"""
    try:
        from .model_serving_utils import get_databricks_token
        
        logger.info("🔑 Testing token retrieval...")
        token = get_databricks_token()
        
        # Don't return the full token for security
        token_preview = token[:10] + "..." + token[-10:] if len(token) > 20 else "***"
        
        return {
            "status": "success",
            "token_length": len(token),
            "token_preview": token_preview,
            "message": "Token retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Debug token test failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to retrieve token"
        }

# Test chat endpoint
@app.post("/debug/chat")
async def debug_chat(request: Request):
    """Debug chat endpoint to test request flow"""
    try:
        # Get all headers
        headers = dict(request.headers)
        
        # Get user token and email
        user_token = request.headers.get("X-Forwarded-Access-Token")
        user_email = request.headers.get("X-Forwarded-Email")
        
        return {
            "message": "Debug chat endpoint reached",
            "user_email": user_email,
            "user_token_present": user_token is not None,
            "user_token_length": len(user_token) if user_token else 0,
            "all_headers": headers
        }
    except Exception as e:
        return {"error": str(e)}

# Serve the main HTML file
@app.get("/app")
async def serve_app():
    """Serve the main application HTML file"""
    frontend_path = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    else:
        return {"message": "Frontend files not found", "path": frontend_path}

# Redirect root to app
@app.get("/", include_in_schema=False)
async def redirect_to_app():
    """Redirect root to the app"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app")

# Ask endpoint using App auth
@app.get("/ask")
async def ask_databricks(question: str, request: Request):
    """
    Call a Databricks foundation model endpoint using App auth
    """
    try:
        response_content = query_llm(question)
        return {"response": response_content}
    except Exception as e:
        logger.error(f"Error in ask endpoint: {str(e)}", exc_info=True)
        return {"error": f"Error calling model endpoint: {str(e)}"}

# Chat endpoint with conversation history integration
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_message: ChatMessage, request: Request):
    """Handle chat messages and return AI responses with conversation history"""
    if not chat_message.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Extract user email from OAuth token
        user_email = None
        if user_token:
            user_email = get_user_email_from_token(user_token)
            logger.info(f"Extracted user email from OAuth token: {user_email}")
        else:
            # Fallback to header-based email if token extraction fails
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
        
        if not user_email:
            logger.warning("No user email found, using fallback")
            user_email = "unknown@databricks.com"
        
        logger.info(f"Chat request from user: {user_email}")
        
        # Use App auth for model calls
        response_content = await query_llm(chat_message.message)
        
        return ChatResponse(response=response_content)
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        # Fallback response on any error
        return ChatResponse(response="I'm sorry, I encountered an error. Please try again.")

# Conversation endpoints are now handled by the conversations router

# User info endpoint
@app.get("/user/info")
async def get_user_info(request: Request):
    """Get user information for display in the app"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        
        # Extract user information from OAuth token
        user_info = None
        if user_token:
            user_info = get_user_info_from_token(user_token)
            logger.info(f"Extracted user info from OAuth token: {user_info}")
        
        if user_info and user_info.get("email"):
            # Use OAuth-extracted info
            email = user_info["email"]
            display_name = user_info.get("display_name") or email.split('@')[0].replace('.', ' ').title()
            username = user_info.get("user_name") or email.split('@')[0]
            
            return {
                "user": {
                    "uid": username,
                    "email": email,
                    "display_name": display_name,
                    "username": username,
                    "initials": "".join([name[0].upper() for name in display_name.split()[:2]]),
                    "groups": user_info.get("groups", []),
                    "roles": user_info.get("roles", []),
                    "scopes": ["serving.serving-endpoints"],
                    "authenticated": True
                },
                "auth_provider": "Databricks Apps (OAuth)",
                "login_time": "Current session"
            }
        else:
            # Fallback to header-based email
            user_email = request.headers.get("X-Forwarded-Email")
            logger.info(f"Using header-based user email: {user_email}")
            
            if user_email:
                display_name = user_email.split('@')[0].replace('.', ' ').title()
                return {
                    "user": {
                        "uid": user_email.split('@')[0],
                        "email": user_email,
                        "display_name": display_name,
                        "username": user_email.split('@')[0],
                        "initials": "".join([name[0].upper() for name in display_name.split()[:2]]),
                        "groups": [],
                        "roles": [],
                        "scopes": ["serving.serving-endpoints"],
                        "authenticated": True
                    },
                    "auth_provider": "Databricks Apps (Header)",
                    "login_time": "Current session"
                }
            else:
                # No user info available
                logger.warning("No user info found - using fallback user info")
                return {
                    "user": {
                        "uid": "databricks_user",
                        "email": "user@databricks.com",
                        "display_name": "Databricks User",
                        "username": "databricks_user",
                        "initials": "DU",
                        "groups": [],
                        "roles": [],
                        "scopes": ["serving.serving-endpoints"],
                        "authenticated": True
                    },
                    "auth_provider": "Databricks Apps Platform (Fallback)",
                    "login_time": "Current session"
                }
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        # Fallback to hardcoded user info
        return {
            "user": {
                "uid": "databricks_user",
                "email": "user@databricks.com",
                "display_name": "Databricks User",
                "username": "databricks_user",
                "initials": "DU",
                "groups": [],
                "roles": [],
                "scopes": ["serving.serving-endpoints"],
                "authenticated": True
            },
            "auth_provider": "Databricks Apps Platform (Error)",
            "login_time": "Current session"
        }

# Debug endpoint to check database initialization
@app.get("/debug/db-init")
async def debug_db_init():
    """Debug endpoint to check database initialization process"""
    try:
        import os
        from config.database import init_engine, check_database_exists, database_health, workspace_client, database_instance, postgres_password
        
        # Check environment variables
        env_vars = {
            "LAKEBASE_INSTANCE_NAME": os.getenv("LAKEBASE_INSTANCE_NAME"),
            "LAKEBASE_DATABASE_NAME": os.getenv("LAKEBASE_DATABASE_NAME"),
            "DATABRICKS_DATABASE_PORT": os.getenv("DATABRICKS_DATABASE_PORT"),
            "DATABRICKS_CLIENT_ID": os.getenv("DATABRICKS_CLIENT_ID"),
        }
        
        # Check if database exists
        db_exists = check_database_exists()
        
        # Try to initialize engine
        init_error = None
        engine_initialized = False
        try:
            init_engine()
            engine_initialized = True
        except Exception as e:
            init_error = str(e)
            import traceback
            init_error += f"\nTraceback: {traceback.format_exc()}"
        
        # Check database health if engine was initialized
        db_health = False
        if engine_initialized:
            try:
                db_health = await database_health()
            except Exception as e:
                db_health = f"Health check failed: {e}"
        
        # Get workspace client info
        workspace_info = {}
        if workspace_client:
            try:
                current_user = workspace_client.current_user.me()
                workspace_info = {
                    "user_name": current_user.user_name,
                    "user_id": current_user.id,
                    "host": workspace_client.config.host
                }
            except Exception as e:
                workspace_info = {"error": str(e)}
        
        # Get database instance info
        instance_info = {}
        if database_instance:
            try:
                instance_info = {
                    "name": database_instance.name,
                    "read_write_dns": database_instance.read_write_dns,
                    "status": getattr(database_instance, 'status', 'unknown')
                }
            except Exception as e:
                instance_info = {"error": str(e)}
        
        return {
            "environment_variables": env_vars,
            "database_exists": db_exists,
            "engine_initialized": engine_initialized,
            "init_error": init_error,
            "database_health": db_health,
            "workspace_client": workspace_info,
            "database_instance": instance_info,
            "token_info": {
                "has_token": postgres_password is not None,
                "token_length": len(postgres_password) if postgres_password else 0,
                "token_preview": postgres_password[:20] + "..." if postgres_password and len(postgres_password) > 20 else postgres_password
            },
            "success": True
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

# Debug endpoint to test database connection step by step
@app.get("/debug/db-step-by-step")
async def debug_db_step_by_step():
    """Debug endpoint to test database connection step by step"""
    try:
        import os
        from databricks.sdk import WorkspaceClient
        
        steps = {}
        
        # Step 1: Check environment variables
        try:
            instance_name = os.getenv("LAKEBASE_INSTANCE_NAME")
            database_name = os.getenv("LAKEBASE_DATABASE_NAME")
            port = os.getenv("DATABRICKS_DATABASE_PORT", "5432")
            
            steps["env_vars"] = {
                "LAKEBASE_INSTANCE_NAME": instance_name,
                "LAKEBASE_DATABASE_NAME": database_name,
                "DATABRICKS_DATABASE_PORT": port,
                "success": bool(instance_name and database_name)
            }
        except Exception as e:
            steps["env_vars"] = {"error": str(e), "success": False}
        
        # Step 2: Create WorkspaceClient
        try:
            workspace_client = WorkspaceClient()
            current_user = workspace_client.current_user.me()
            steps["workspace_client"] = {
                "user_name": current_user.user_name,
                "user_id": current_user.id,
                "host": workspace_client.config.host,
                "success": True
            }
        except Exception as e:
            steps["workspace_client"] = {"error": str(e), "success": False}
            return {"steps": steps, "success": False}
        
        # Step 3: Get database instance
        try:
            instance_name = os.getenv("LAKEBASE_INSTANCE_NAME")
            database_instance = workspace_client.database.get_database_instance(name=instance_name)
            steps["database_instance"] = {
                "name": database_instance.name,
                "read_write_dns": database_instance.read_write_dns,
                "status": getattr(database_instance, 'status', 'unknown'),
                "success": True
            }
        except Exception as e:
            steps["database_instance"] = {"error": str(e), "success": False}
            return {"steps": steps, "success": False}
        
        # Step 4: Generate database credentials
        try:
            import uuid
            cred = workspace_client.database.generate_database_credential(
                request_id=str(uuid.uuid4()),
                instance_names=[database_instance.name]
            )
            steps["credentials"] = {
                "has_token": bool(cred.token),
                "token_length": len(cred.token) if cred.token else 0,
                "token_preview": cred.token[:20] + "..." if cred.token and len(cred.token) > 20 else cred.token,
                "success": True
            }
        except Exception as e:
            steps["credentials"] = {"error": str(e), "success": False}
            return {"steps": steps, "success": False}
        
        # Step 5: Test database connection
        try:
            from sqlalchemy import URL, text
            from sqlalchemy.ext.asyncio import create_async_engine
            
            database_name = os.getenv("LAKEBASE_DATABASE_NAME", database_instance.name)
            username = workspace_client.current_user.me().user_name
            
            url = URL.create(
                drivername="postgresql+asyncpg",
                username=username,
                password=cred.token,
                host=database_instance.read_write_dns,
                port=int(os.getenv("DATABRICKS_DATABASE_PORT", "5432")),
                database=database_name,
            )
            
            # Create a test engine
            test_engine = create_async_engine(
                url,
                pool_pre_ping=False,
                echo=False,
                connect_args={
                    "command_timeout": 10,
                    "server_settings": {
                        "application_name": "debug_test",
                    },
                    "ssl": "require",
                },
            )
            
            # Test connection
            async with test_engine.connect() as connection:
                result = await connection.execute(text("SELECT 1 as test"))
                test_value = result.scalar()
            
            await test_engine.dispose()
            
            steps["connection_test"] = {
                "url": str(url).replace(cred.token, "***"),
                "test_query_result": test_value,
                "success": True
            }
        except Exception as e:
            steps["connection_test"] = {"error": str(e), "success": False}
        
        return {
            "steps": steps,
            "overall_success": all(step.get("success", False) for step in steps.values()),
            "success": True
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

# Debug endpoint to list all database instances
@app.get("/debug/db-instances")
async def debug_db_instances():
    """Debug endpoint to list all available database instances"""
    try:
        from databricks.sdk import WorkspaceClient
        
        workspace_client = WorkspaceClient()
        
        # Try different methods to list database instances
        instances = []
        
        try:
            # Method 1: Direct API call
            instances_list = workspace_client.database.list_database_instances()
            instances = [{"name": inst.name, "status": getattr(inst, 'status', 'unknown'), "method": "list_database_instances"} for inst in instances_list]
        except Exception as e:
            instances.append({"error": f"list_database_instances failed: {e}", "method": "list_database_instances"})
        
        try:
            # Method 2: Try to get specific instance
            instance_name = "onesource-chatbot-pg"
            instance = workspace_client.database.get_database_instance(name=instance_name)
            instances.append({
                "name": instance.name,
                "status": getattr(instance, 'status', 'unknown'),
                "read_write_dns": getattr(instance, 'read_write_dns', 'unknown'),
                "method": "get_database_instance"
            })
        except Exception as e:
            instances.append({"error": f"get_database_instance failed: {e}", "method": "get_database_instance"})
        
        # Get current user info
        try:
            current_user = workspace_client.current_user.me()
            user_info = {
                "user_name": current_user.user_name,
                "user_id": current_user.id,
                "host": workspace_client.config.host
            }
        except Exception as e:
            user_info = {"error": str(e)}
        
        return {
            "instances": instances,
            "user_info": user_info,
            "success": True
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

# Debug endpoint to test conversation operations
@app.get("/debug/conversations")
async def debug_conversations(request: Request):
    """Debug endpoint to test conversation operations"""
    try:
        # Use a fake user email for debugging to avoid interfering with real user data
        user_email = "debug@databricks.com"
        
        # Test conversation creation
        from services.conversation_service import create_conversation, get_user_conversations
        
        # Create a test conversation
        test_conversation = await create_conversation(
            user_email=user_email,
            title="Debug Test Conversation",
            messages=[{"role": "user", "content": "Test message"}]
        )
        
        # Get user conversations
        user_conversations = await get_user_conversations(user_email)
        
        # Test conversation update
        update_success = False
        update_error = None
        if test_conversation:
            try:
                from services.conversation_service import update_conversation
                updated_conversation = await update_conversation(
                    conversation_id=test_conversation.get('id'),
                    user_email=user_email,
                    title="Updated Debug Test Conversation",
                    messages=[{"role": "user", "content": "Updated test message"}]
                )
                update_success = updated_conversation is not None
            except Exception as e:
                update_error = str(e)
        
        return {
            "user_email": user_email,
            "test_conversation_created": test_conversation is not None,
            "test_conversation_id": test_conversation.get('id') if test_conversation else None,
            "test_conversation_title": test_conversation.get('title') if test_conversation else None,
            "total_conversations": len(user_conversations),
            "conversation_ids": [conv.get('id') for conv in user_conversations],
            "conversation_titles": [conv.get('title') for conv in user_conversations],
            "update_test": {
                "success": update_success,
                "error": update_error
            },
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

# Debug endpoint to test specific conversation ID
@app.get("/debug/conversation/{conversation_id}")
async def debug_specific_conversation(conversation_id: str, request: Request):
    """Debug endpoint to test a specific conversation ID"""
    try:
        # Get user token from headers
        user_token = request.headers.get("X-Forwarded-Access-Token")
        user_email = get_user_email_from_token(user_token) if user_token else "test@example.com"
        
        from services.conversation_service import get_user_conversations, update_conversation
        
        # Get all user conversations
        user_conversations = await get_user_conversations(user_email)
        
        # Find the specific conversation
        target_conversation = None
        for conv in user_conversations:
            if conv.get('id') == conversation_id:
                target_conversation = conv
                break
        
        # Try to update the conversation
        update_result = None
        update_error = None
        try:
            update_result = await update_conversation(
                conversation_id=conversation_id,
                user_email=user_email,
                title="Debug Update Test",
                messages=[{"role": "user", "content": "Debug update message"}]
            )
        except Exception as e:
            update_error = str(e)
        
        return {
            "conversation_id": conversation_id,
            "user_email": user_email,
            "conversation_found": target_conversation is not None,
            "conversation_details": target_conversation,
            "total_user_conversations": len(user_conversations),
            "all_conversation_ids": [conv.get('id') for conv in user_conversations],
            "update_test": {
                "success": update_result is not None,
                "result": update_result,
                "error": update_error
            },
            "success": True
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

# Debug endpoint to check if tables exist
@app.get("/debug/tables")
async def debug_tables():
    """Debug endpoint to check if database tables exist"""
    try:
        from sqlalchemy import text
        from config.database import get_async_db
        
        async for db in get_async_db():
            # Check if users table exists
            users_result = await db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """))
            users_exists = users_result.fetchone() is not None
            
            # Check if conversations table exists
            conversations_result = await db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'conversations'
            """))
            conversations_exists = conversations_result.fetchone() is not None
            
            # Get table counts
            users_count = 0
            conversations_count = 0
            
            if users_exists:
                users_count_result = await db.execute(text("SELECT COUNT(*) FROM users"))
                users_count = users_count_result.scalar()
            
            if conversations_exists:
                conversations_count_result = await db.execute(text("SELECT COUNT(*) FROM conversations"))
                conversations_count = conversations_count_result.scalar()
            
            return {
                "users_table": {
                    "exists": users_exists,
                    "count": users_count
                },
                "conversations_table": {
                    "exists": conversations_exists,
                    "count": conversations_count
                },
                "success": True
            }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

# Debug endpoint to check database configuration
@app.get("/debug/db-config")
async def debug_db_config():
    """Debug endpoint to check database configuration"""
    try:
        from config.lakebase_config import get_lakebase_connection_config
        import os
        
        config = get_lakebase_connection_config()
        
        # Check for relevant environment variables
        env_vars = {
            # Databricks-provided environment variables (preferred)
            "DATABRICKS_DATABASE_HOST": os.getenv("DATABRICKS_DATABASE_HOST"),
            "DATABRICKS_DATABASE_PORT": os.getenv("DATABRICKS_DATABASE_PORT"),
            "DATABRICKS_DATABASE_NAME": os.getenv("DATABRICKS_DATABASE_NAME"),
            "DATABRICKS_DATABASE_USER": os.getenv("DATABRICKS_DATABASE_USER"),
            "DATABRICKS_DATABASE_PASSWORD": "***" if os.getenv("DATABRICKS_DATABASE_PASSWORD") else None,
            # Custom environment variables (fallback)
            "LAKEBASE_HOST": os.getenv("LAKEBASE_HOST"),
            "LAKEBASE_PORT": os.getenv("LAKEBASE_PORT"),
            "LAKEBASE_DATABASE_NAME": os.getenv("LAKEBASE_DATABASE_NAME"),
            "LAKEBASE_USERNAME": os.getenv("LAKEBASE_USERNAME"),
            "LAKEBASE_PASSWORD": "***" if os.getenv("LAKEBASE_PASSWORD") else None,
            # Other potential variables
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "DATABRICKS_DATABASE_URL": os.getenv("DATABRICKS_DATABASE_URL"),
        }
        
        return {
            "config": config,
            "environment_variables": env_vars,
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment variable (Cloud Run sets this)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    uvicorn.run(app, host=host, port=port)