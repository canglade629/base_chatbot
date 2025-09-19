#!/usr/bin/env python3
"""
ICC Legal Research Assistant - Main Entry Point

This is the main entry point for the ICC Legal Research Assistant application.
It imports and runs the FastAPI application from the backend/api module.
"""

import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def check_environment():
    """Check if all required environment variables are set"""
    required_vars = ['DATABRICKS_TOKEN']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {missing_vars}")
        logger.warning("Some features may not work properly")
    else:
        logger.info("All required environment variables are set")

def create_app():
    """Create and configure the FastAPI app with error handling"""
    try:
        from api.app import app
        logger.info("✅ FastAPI app imported successfully")
        return app
    except Exception as e:
        logger.error(f"❌ Failed to import FastAPI app: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment variable (Cloud Run sets this)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Starting ICC Legal Research Assistant on {host}:{port}")
    logger.info(f"📁 Working directory: {os.getcwd()}")
    logger.info(f"🐍 Python path: {sys.path}")
    
    # Check environment
    check_environment()
    
    # Create app with error handling
    try:
        app = create_app()
        logger.info("✅ App configured successfully, starting server...")
        
        # Start the server
        uvicorn.run(
            app, 
            host=host, 
            port=port, 
            log_level="info",
            access_log=True,
            server_header=False,
            date_header=False
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)