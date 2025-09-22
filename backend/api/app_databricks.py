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
from config.database import init_engine, start_token_refresh, stop_token_refresh, check_database_exists
from services.user_service import get_or_create_user
from services.conversation_service import (
    get_user_conversations, 
    create_conversation as create_conversation_service, 
    update_conversation as update_conversation_service, 
    delete_conversation as delete_conversation_service, 
    cleanup_empty_conversations
)

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
        if check_database_exists():
            logger.info("✅ Lakebase database found - initializing connection...")
            init_engine()
            await start_token_refresh()
            logger.info("✅ Application started with Lakebase connection")
        else:
            logger.warning("⚠️ Lakebase database not found - conversation history disabled")
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        logger.warning("⚠️ Continuing without database - conversation history disabled")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down application...")
    try:
        await stop_token_refresh()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
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
MOCK_DATABASE = True

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
async def get_conversations(user_email: str = Query(...)):
    """Get all conversations for a user"""
    try:
        if MOCK_DATABASE:
            # Use mock functions
            conversations = await mock_get_user_conversations(user_email)
            return {"conversations": conversations}
        else:
            # Try Lakebase first - always try database, don't check if it exists
            try:
                conversations = await get_user_conversations(user_email)
                return {"conversations": conversations}
            except Exception as db_error:
                logger.error(f"Database error in get conversations: {db_error}")
                # Fall back to in-memory storage if database fails
                user_conversations = [conv for conv in conversations_storage.values() if conv.get('user_email') == user_email]
                user_conversations.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
                return {"conversations": user_conversations}
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return {"conversations": []}

@app.post("/conversations")
async def create_conversation(conversation_data: dict):
    """Create a new conversation"""
    try:
        user_email = conversation_data.get("user_email")
        if not user_email:
            raise HTTPException(status_code=400, detail="user_email is required")
        
        if MOCK_DATABASE:
            # Use mock functions
            user = await mock_get_or_create_user(user_email)
            conversation = await mock_create_conversation(
                user_email=user_email,
                title=conversation_data.get("title", "New Conversation"),
                messages=conversation_data.get("messages", [])
            )
            return conversation
        else:
            # Try Lakebase first - always try database, don't check if it exists
            try:
                # Create or get user first
                user = await get_or_create_user(user_email)
                if not user:
                    raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
                
                conversation = await create_conversation_service(
                    user_email=user_email,
                    title=conversation_data.get("title", "New Conversation"),
                    messages=conversation_data.get("messages", [])
                )
                
                if not conversation:
                    raise HTTPException(status_code=500, detail="Failed to create conversation")
                
                return conversation
            except Exception as db_error:
                logger.error(f"Database error in conversation creation: {db_error}")
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
                return conversation
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

@app.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, conversation_data: dict, user_email: str = Query(...)):
    """Update a conversation"""
    try:
        if MOCK_DATABASE:
            # Use mock functions
            conversation = await mock_update_conversation(
                conversation_id=conversation_id,
                user_email=user_email,
                title=conversation_data.get('title'),
                messages=conversation_data.get('messages')
            )
            
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            return conversation
        else:
            # Try Lakebase first - always try database, don't check if it exists
            try:
                conversation = await update_conversation_service(
                    conversation_id=conversation_id,
                    user_email=user_email,
                    title=conversation_data.get('title'),
                    messages=conversation_data.get('messages')
                )
                
                if not conversation:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                
                return conversation
            except Exception as db_error:
                logger.error(f"Database error in conversation update: {db_error}")
                # Fall back to in-memory storage if database fails
                conversation = conversations_storage.get(conversation_id)
                
                if not conversation or conversation.get('user_email') != user_email:
                    raise HTTPException(status_code=404, detail="Conversation not found")

                if 'title' in conversation_data:
                    conversation['title'] = conversation_data['title']
                if 'messages' in conversation_data:
                    conversation['messages'] = conversation_data['messages']
                
                conversation['updated_at'] = datetime.now().isoformat()
                return conversation
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation")

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, user_email: str = Query(...)):
    """Delete a conversation"""
    try:
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
async def cleanup_conversations(user_email: str = Query(...)):
    """Clean up empty conversations"""
    try:
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
        
        return {
            "database_health": db_healthy,
            "token_info": token_info,
            "user_creation": user_info
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
        # Get user email from headers for conversation tracking
        user_email = request.headers.get("X-Forwarded-Email")
        
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
        # Get user email from headers
        user_email = request.headers.get("X-Forwarded-Email")
        
        logger.info(f"User authentication via App auth: {user_email}")
        
        if user_email:
            # Use header-based info for app-auth
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
                    "auth_provider": "Databricks Apps (App auth)",
                "login_time": "Current session"
            }
        else:
            # No user headers, this means we're not in a user context
            logger.warning("No user headers found - using fallback user info")
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
                "auth_provider": "Databricks Apps Platform (App auth)",
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

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment variable (Cloud Run sets this)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    uvicorn.run(app, host=host, port=port)