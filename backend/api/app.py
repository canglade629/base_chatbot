from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
import random
import os
import httpx
import asyncio
from dotenv import load_dotenv
from datetime import timedelta

# Import our custom modules
import sys
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from services.firestore_auth import firestore_auth
    logger.info("✅ Using Firestore-only authentication")
    logger.info(f"🔧 Mock mode: {firestore_auth.use_mock}")
except Exception as e:
    logger.error(f"❌ Failed to import firestore_auth: {e}")
    # Create a mock auth object for fallback
    class MockAuth:
        use_mock = True
        def verify_token(self, token): return None
        def create_access_token(self, data): return "mock_token"
    firestore_auth = MockAuth()

try:
    from services.auth_service import auth_service
    logger.info("✅ Auth service imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import auth_service: {e}")
    # Create a mock auth service for fallback
    class MockAuthService:
        def get_current_user(self, token): return {"email": "mock@user.com", "user_id": "mock_user"}
    auth_service = MockAuthService()

# Load environment variables from .env file
load_dotenv()

# Databricks endpoint configuration
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "https://dbc-0619d7f5-0bda.cloud.databricks.com")
# Use the correct model serving endpoint based on the production code
DATABRICKS_ENDPOINT = f"{DATABRICKS_HOST}/serving-endpoints/icc_chatbot_endpoint/invocations"
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

if not DATABRICKS_TOKEN:
    logger.warning("⚠️ DATABRICKS_TOKEN not found in environment variables")
    logger.warning("Chat functionality will be limited")
else:
    logger.info(f"✅ Databricks configured: {DATABRICKS_HOST}")
    logger.info(f"✅ Model serving endpoint: {DATABRICKS_ENDPOINT}")

app = FastAPI(title="ICC Legal Research Assistant")

# Add health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Service is running",
        "timestamp": "2024-01-01T00:00:00Z"
    }

# Add API info endpoint
@app.get("/api/info")
async def api_info():
    return {
        "message": "ICC Legal Research Assistant API", 
        "status": "running",
        "version": "1.0.0"
    }

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files from frontend/static directory
import os
frontend_static_path = os.path.join(os.path.dirname(__file__), "../../frontend/static")
app.mount("/static", StaticFiles(directory=frontend_static_path), name="static")

# Mount JS files from frontend/js directory
frontend_js_path = os.path.join(os.path.dirname(__file__), "../../frontend/js")
app.mount("/js", StaticFiles(directory=frontend_js_path), name="js")

# Serve the main HTML file
@app.get("/app")
async def serve_app():
    """Serve the main application HTML file"""
    frontend_path = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    return FileResponse(frontend_path)

# Redirect root to app
@app.get("/", include_in_schema=False)
async def redirect_to_app():
    """Redirect root to the app"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app")

# Security
security = HTTPBearer()

# Pydantic models
class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# Databricks API models
class DatabricksRequest(BaseModel):
    query: List[str]
    num_results: List[int]
    conversation_id: List[str]

class Source(BaseModel):
    source: str
    source_type: str
    section: str
    page_number: int
    article: Optional[str] = None
    relevance_score: float

class DatabricksResponse(BaseModel):
    question: str
    analysis: str
    routing_decision: str
    sources_used: int
    confidence_score: float
    key_findings: List[str]
    citations: List[str]
    processing_time_seconds: float
    conversation_id: str
    sources: List[Source]

class EnhancedChatResponse(BaseModel):
    response: str
    analysis: Optional[str] = None
    routing_decision: Optional[str] = None
    sources_used: Optional[int] = None
    confidence_score: Optional[float] = None
    key_findings: Optional[List[str]] = None
    citations: Optional[List[str]] = None
    processing_time_seconds: Optional[float] = None
    sources: Optional[List[Dict[str, Any]]] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None

class UserResponse(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenData(BaseModel):
    uid: Optional[str] = None

class ConversationResponse(BaseModel):
    id: str
    title: str
    messages: list
    created_at: str
    updated_at: str

class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[list] = None

# Function to call Databricks endpoint
async def call_databricks_endpoint(query: str, conversation_id: str = None) -> Dict[str, Any]:
    """Call the Databricks chatbot endpoint"""
    if not DATABRICKS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Databricks token not configured"
        )
    
    if conversation_id is None:
        conversation_id = f"conv_{random.randint(100000, 999999)}"
    
    # Prepare request payload for Databricks model serving endpoint
    # Based on the production model signature from ICC_Enhanced_RAG_Production.py
    payload = {
        "inputs": {
            "question": query,
            "top_k": 10,
            "conversation_id": conversation_id
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DATABRICKS_ENDPOINT,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {DATABRICKS_TOKEN}"
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request to chatbot service timed out"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chatbot service error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to call chatbot service: {str(e)}"
        )

# Dependency to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = auth_service.verify_token(credentials.credentials)
        if payload is None:
            raise credentials_exception
        
        uid: str = payload.get("sub")
        if uid is None:
            raise credentials_exception
        
        # Get user from Firestore
        user = await firestore_auth.get_user_by_uid(uid)
        return user
    except Exception:
        raise credentials_exception

# Canned responses for the ICC Assistant (with markdown formatting)
CANNED_RESPONSES = [
    """# Welcome to ICC Assistant! 🤖

I'm here to help you with **ICC documentation**. How can I assist you today?

## What I can help you with:
- Product information and specifications
- Process documentation and workflows
- Technical guides and tutorials
- Best practices and recommendations

Just ask me anything!""",

    """# ICC Documentation Hub 📚

Welcome to **ICC**! I can help you find information about:

## Our Services:
- **Product Documentation** - Complete product specifications and guides
- **Process Workflows** - Step-by-step process documentation
- **Technical Resources** - API documentation and integration guides
- **Best Practices** - Industry standards and recommendations

What specific information are you looking for?""",

    """# Hello! 👋

I'm your **ICC documentation assistant**. I can help you navigate through our comprehensive knowledge base and find exactly what you need.

## Quick Start:
1. **Search** for specific topics or products
2. **Browse** by category or department
3. **Ask** me direct questions
4. **Get** instant, accurate answers

What would you like to explore today?""",

    """# Great Question! 💡

Let me help you with that. **ICC 2.0** has many powerful features:

## Key Features:
- **Advanced Search** - Find information quickly
- **Real-time Updates** - Always current documentation
- **Multi-format Support** - PDFs, videos, interactive guides
- **Collaborative Tools** - Share and collaborate on documents

## Next Steps:
- Tell me more about your specific needs
- I can guide you to the right resources
- We can explore related topics together

What would you like to know more about?""",

    """# Comprehensive Documentation Solution 📖

**ICC 2.0** provides extensive documentation and resources for all your needs:

## Documentation Types:
- **User Guides** - Step-by-step instructions
- **API Documentation** - Technical integration details
- **Process Maps** - Visual workflow representations
- **Training Materials** - Learning resources and tutorials

## Benefits:
- ✅ **Centralized Access** - Everything in one place
- ✅ **Always Updated** - Real-time synchronization
- ✅ **Easy Navigation** - Intuitive search and browse
- ✅ **Mobile Friendly** - Access anywhere, anytime

What specific area interests you most?""",

    """# Interesting Topic! 🔍

**ICC 2.0** has extensive documentation that covers this area. Let me help you find the right resources:

## Available Resources:
- **Technical Specifications** - Detailed technical information
- **Implementation Guides** - How-to documentation
- **Case Studies** - Real-world examples and success stories
- **FAQ Section** - Common questions and answers

## How I Can Help:
1. **Direct you** to specific documentation
2. **Explain** complex concepts in simple terms
3. **Provide** step-by-step guidance
4. **Answer** follow-up questions

What aspect would you like to explore first?""",

    """# Documentation Made Easy! 🚀

I'm here to make your **ICC 2.0** documentation journey smoother:

## What You Can Do:
- **Ask Questions** - Get instant answers
- **Browse Topics** - Explore by category
- **Get Recommendations** - Personalized suggestions
- **Learn Best Practices** - Industry insights

## Popular Topics:
- Product specifications and features
- Integration and setup guides
- Troubleshooting and support
- Updates and new features

What would you like to start with?""",

    """# Thank You! 🙏

**ICC 2.0** is designed to be your comprehensive documentation solution. Here's how I can continue helping:

## Ongoing Support:
- **24/7 Availability** - I'm always here to help
- **Personalized Assistance** - Tailored to your needs
- **Regular Updates** - Stay current with latest information
- **Expert Knowledge** - Deep understanding of ICC

## Ready to Help:
- Ask me anything about ICC
- Request specific documentation
- Get guidance on implementation
- Explore advanced features

What else can I help you with today?""",

    """# Appreciate Your Interest! 💼

**ICC 2.0** has evolved to better serve your documentation needs. Here's what's new:

## Recent Enhancements:
- **Improved Search** - Faster, more accurate results
- **Better Navigation** - Intuitive user interface
- **Enhanced Mobile** - Optimized for all devices
- **Real-time Sync** - Always up-to-date content

## What I Can Help With:
- **Specific Queries** - Direct questions about features
- **Implementation** - Step-by-step guidance
- **Troubleshooting** - Problem-solving assistance
- **Best Practices** - Industry recommendations

What specific information are you looking for?""",

    """# Let's Get Started! 🎯

I'm excited to help you with **ICC 2.0**! Here's how we can work together:

## My Capabilities:
- **Instant Answers** - Quick responses to your questions
- **Detailed Explanations** - In-depth information when needed
- **Resource Discovery** - Find the right documentation
- **Process Guidance** - Step-by-step assistance

## Getting the Most Out of ICC:
1. **Be Specific** - The more detailed your question, the better my answer
2. **Ask Follow-ups** - I'm here for ongoing conversation
3. **Explore Topics** - Don't hesitate to ask about related areas
4. **Request Examples** - I can provide practical examples

**What would you like to know about ICC 2.0?**"""
]

# Authentication endpoints
@app.post("/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup):
    """Register a new user"""
    try:
        # Create user in Firestore
        user = await firestore_auth.create_user(
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.display_name
        )
        
        # Create JWT tokens
        access_token = auth_service.create_access_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        refresh_token = auth_service.create_refresh_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(**user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )

@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """Authenticate user and return tokens"""
    try:
        # Verify user credentials
        user = await firestore_auth.verify_user(
            email=user_data.email,
            password=user_data.password
        )
        
        # Create JWT tokens
        access_token = auth_service.create_access_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        refresh_token = auth_service.create_refresh_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(**user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}"
        )

@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str):
    """Refresh access token using refresh token"""
    try:
        payload = auth_service.verify_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        uid = payload.get("sub")
        user = await firestore_auth.get_user_by_uid(uid)
        
        # Create new tokens
        access_token = auth_service.create_access_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        new_refresh_token = auth_service.create_refresh_token(
            data={"sub": user["uid"], "email": user["email"]}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user=UserResponse(**user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {str(e)}"
        )

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(**current_user)

@app.put("/auth/profile", response_model=UserResponse)
async def update_profile(
    display_name: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile"""
    try:
        updated_user = await firestore_auth.update_user_profile(
            uid=current_user["uid"],
            display_name=display_name
        )
        return UserResponse(**updated_user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profile update failed: {str(e)}"
        )

@app.delete("/auth/account")
async def delete_account(current_user: dict = Depends(get_current_user)):
    """Delete user account"""
    try:
        await firestore_auth.delete_user(current_user["uid"])
        return {"message": "Account deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account deletion failed: {str(e)}"
        )

# Conversation endpoints
@app.get("/conversations", response_model=list[ConversationResponse])
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """Get all conversations for the current user"""
    try:
        conversations = await firestore_auth.get_user_conversations(current_user["uid"])
        return conversations
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get conversations: {str(e)}"
        )

class ConversationCreate(BaseModel):
    title: str = "New Conversation"

@app.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new conversation"""
    try:
        conversation = await firestore_auth.create_conversation(current_user["uid"], conversation_data.title)
        return conversation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create conversation: {str(e)}"
        )

@app.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    update_data: ConversationUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a conversation"""
    try:
        # Verify conversation belongs to user
        conversations = await firestore_auth.get_user_conversations(current_user["uid"])
        if not any(conv["id"] == conversation_id for conv in conversations):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        await firestore_auth.update_conversation(
            conversation_id,
            title=update_data.title,
            messages=update_data.messages
        )
        return {"message": "Conversation updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update conversation: {str(e)}"
        )

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a conversation"""
    try:
        # Verify conversation belongs to user
        conversations = await firestore_auth.get_user_conversations(current_user["uid"])
        if not any(conv["id"] == conversation_id for conv in conversations):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        await firestore_auth.delete_conversation(conversation_id)
        return {"message": "Conversation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete conversation: {str(e)}"
        )

@app.post("/conversations/cleanup")
async def cleanup_empty_conversations(current_user: dict = Depends(get_current_user)):
    """Delete all empty conversations for the current user"""
    try:
        conversations = await firestore_auth.get_user_conversations(current_user["uid"])
        empty_conversations = [conv for conv in conversations if len(conv.get("messages", [])) == 0]
        
        deleted_count = 0
        for conv in empty_conversations:
            await firestore_auth.delete_conversation(conv["id"])
            deleted_count += 1
        
        return {"message": f"Deleted {deleted_count} empty conversations"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to cleanup conversations: {str(e)}"
        )

# Main app routes
@app.get("/")
async def read_index():
    """Serve the React app"""
    frontend_file = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    return FileResponse(frontend_file)

@app.get("/auth")
async def read_auth():
    """Serve the authentication page"""
    auth_file = os.path.join(os.path.dirname(__file__), "../../frontend/components/auth.html")
    return FileResponse(auth_file)

@app.get("/auth.html")
async def read_auth_html():
    """Serve the authentication page (alternative route)"""
    auth_file = os.path.join(os.path.dirname(__file__), "../../frontend/components/auth.html")
    return FileResponse(auth_file)

@app.post("/chat", response_model=EnhancedChatResponse)
async def chat_endpoint(
    chat_message: ChatMessage,
    current_user: dict = Depends(get_current_user)
):
    """Handle chat messages and return AI responses (protected endpoint)"""
    if not chat_message.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        # Call the real Databricks endpoint
        databricks_response = await call_databricks_endpoint(chat_message.message)
        
        # Extract the response from the Databricks model serving endpoint
        # The response comes wrapped in a "predictions" object
        response_data = {}
        if isinstance(databricks_response, dict) and "predictions" in databricks_response:
            predictions = databricks_response["predictions"]
            if isinstance(predictions, dict):
                # Predictions is a dictionary (not a list)
                response_data = predictions
            elif isinstance(predictions, list) and len(predictions) > 0:
                response_data = predictions[0]
        elif isinstance(databricks_response, list) and len(databricks_response) > 0:
            response_data = databricks_response[0]
        elif isinstance(databricks_response, dict):
            # Direct response format
            response_data = databricks_response
        
        # Format the response with enhanced analysis and sources
        if response_data:
            # Extract fields based on the production model output format
            question = response_data.get('question', query)
            analysis = response_data.get('analysis', 'No analysis available')
            key_findings = response_data.get('key_findings', [])
            citations = response_data.get('citations', [])
            confidence_score = response_data.get('confidence_score', 0.0)
            sources_used = response_data.get('sources_used', 0)
            processing_time = response_data.get('processing_time', 0.0)
            
            # Confidence indicator
            confidence_level = "High" if confidence_score >= 0.8 else "Medium" if confidence_score >= 0.6 else "Low"                                                                                                    
            confidence_emoji = "🟢" if confidence_score >= 0.8 else "🟡" if confidence_score >= 0.6 else "🔴"                                                                                                           
            
            formatted_response = f"# ⚖️ Legal Analysis\n\n"
            formatted_response += f"**Research Question:** {question}\n\n"
            formatted_response += f"**Analysis Quality:** {confidence_emoji} {confidence_level} Confidence ({confidence_score:.2f})\n"                                                                                  
            formatted_response += f"**Sources Analyzed:** {sources_used} documents\n"
            formatted_response += f"**Processing Time:** {processing_time:.2f}s\n\n"
            
            # Main analysis with better formatting
            formatted_response += f"## 📋 Analysis\n\n{analysis}\n\n"
            
            # Enhanced key findings section
            if key_findings:
                formatted_response += f"## 🔍 Key Findings\n\n"
                for i, finding in enumerate(key_findings, 1):
                    # Clean up the finding text
                    clean_finding = finding.replace('•', '').replace('*', '').strip()
                    if clean_finding.startswith('📋'):
                        formatted_response += f"{clean_finding}\n"
                    else:
                        formatted_response += f"{i}. {clean_finding}\n"
                formatted_response += "\n"
            
            # Enhanced citations section
            if citations:
                formatted_response += f"## 📚 Legal Citations\n\n"
                for i, citation in enumerate(citations, 1):
                    formatted_response += f"{i}. {citation}\n"
                formatted_response += "\n"
            
            # Add footer with disclaimer
            formatted_response += "---\n"
            formatted_response += "*This analysis is based on retrieved legal documents and should be verified against primary sources.*\n"                                                                             
        else:
            # Fallback to canned response if format is unexpected
            formatted_response = random.choice(CANNED_RESPONSES)
        
        return EnhancedChatResponse(
            response=formatted_response,
            analysis=response_data.get('analysis'),
            routing_decision=response_data.get('routing_decision'),
            sources_used=response_data.get('sources_used'),
            confidence_score=response_data.get('confidence_score'),
            key_findings=response_data.get('key_findings'),
            citations=response_data.get('citations'),
            processing_time_seconds=response_data.get('processing_time'),
            sources=response_data.get('sources')
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions from the Databricks call
        raise
    except Exception as e:
        # Fallback to canned response on any other error
        print(f"Error calling Databricks endpoint: {str(e)}")
        response = random.choice(CANNED_RESPONSES)
        return EnhancedChatResponse(response=response)

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment variable (Cloud Run sets this)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    uvicorn.run(app, host=host, port=port)
