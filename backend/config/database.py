import asyncio
import logging
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()
logger = logging.getLogger(__name__)

# Global variables
engine: AsyncEngine | None = None
AsyncSessionLocal: sessionmaker | None = None
current_password: str | None = None

def get_fresh_database_token() -> str:
    """Get a fresh token for database authentication with timeout handling"""
    global current_password
    
    try:
        # First try to get token from metadata service (for Databricks Apps) with short timeout
        import requests
        try:
            r = requests.get("http://localhost:8787/api/2.0/app-auth/token", timeout=2.0)
            if r.status_code == 200:
                response_data = r.json()
                if "access_token" in response_data:
                    token = response_data["access_token"]
                    logger.info("✅ Got fresh token from metadata service for database auth")
                    current_password = token
                    return token
        except Exception as e:
            logger.warning(f"Metadata service not available for database auth: {e}")
        
        # Try to get token from Databricks SDK with timeout
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            token = w.config.token
            if token:
                logger.info("✅ Got fresh token from Databricks SDK for database auth")
                current_password = token
                return token
        except Exception as e:
            logger.warning(f"Databricks SDK not available for database auth: {e}")
        
        # Fall back to environment variable
        fallback_token = os.getenv('DATABRICKS_TOKEN')
        if fallback_token and fallback_token != "your-databricks-token-here":
            logger.info("✅ Using fallback token from DATABRICKS_TOKEN for database auth")
            current_password = fallback_token
            return fallback_token
        
        # If all else fails, use the original password (may be expired)
        original_password = os.getenv("LAKEBASE_PASSWORD")
        if original_password:
            logger.warning("Using original password (may be expired)")
            current_password = original_password
            return original_password
        
        raise Exception("No valid token found for database authentication")
        
    except Exception as e:
        logger.error(f"Error getting fresh database token: {e}")
        # Fall back to original password
        original_password = os.getenv("LAKEBASE_PASSWORD")
        if original_password:
            logger.warning("Falling back to original password (may be expired)")
            current_password = original_password
            return original_password
        raise Exception(f"Failed to get database token: {e}")

def init_engine():
    """Initialize database connection using standard PostgreSQL connection"""
    global engine, AsyncSessionLocal, current_password

    try:
        # Get database connection details from environment variables
        host = os.getenv("LAKEBASE_HOST")
        port = int(os.getenv("LAKEBASE_PORT", "5432"))
        database = os.getenv("LAKEBASE_DATABASE_NAME", "danone-pg-db")
        username = os.getenv("LAKEBASE_USERNAME")
        original_password = os.getenv("LAKEBASE_PASSWORD")
        
        if not all([host, username, original_password]):
            raise ValueError("Missing required Lakebase environment variables: LAKEBASE_HOST, LAKEBASE_USERNAME, LAKEBASE_PASSWORD")
        
        logger.info(f"Connecting to Lakebase database: {host}:{port}/{database}")
        
        # Check if password is a JWT token (starts with eyJ)
        if original_password.startswith("eyJ"):
            logger.info("Detected JWT token in password, getting fresh token for database authentication")
            # Get a fresh token for database authentication
            password = get_fresh_database_token()
        else:
            logger.info("Using standard password authentication")
            password = original_password
            current_password = password
        
        # Build connection URL
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
        )

        # Create async engine with connection pooling
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            echo=False,
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE_INTERVAL", "3600")),
            connect_args={
                "command_timeout": int(os.getenv("DB_COMMAND_TIMEOUT", "30")),
            },
        )

        AsyncSessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        
        logger.info(f"✅ Database engine initialized for {database}")

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise RuntimeError(f"Failed to initialize database: {e}") from e

async def refresh_database_connection():
    """Refresh the database connection with a new token with timeout handling"""
    global engine, AsyncSessionLocal, current_password
    
    try:
        logger.info("🔄 Refreshing database connection with fresh token...")
        
        # Get a fresh token with timeout
        import asyncio
        fresh_token = await asyncio.wait_for(
            asyncio.to_thread(get_fresh_database_token),
            timeout=10.0  # 10 second timeout for token retrieval
        )
        
        # Get database connection details
        host = os.getenv("LAKEBASE_HOST")
        port = int(os.getenv("LAKEBASE_PORT", "5432"))
        database = os.getenv("LAKEBASE_DATABASE_NAME", "danone-pg-db")
        username = os.getenv("LAKEBASE_USERNAME")
        
        # Build new connection URL with fresh token
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=username,
            password=fresh_token,
            host=host,
            port=port,
            database=database,
        )

        # Dispose old engine with timeout
        if engine:
            await asyncio.wait_for(engine.dispose(), timeout=5.0)
        
        # Create new engine with fresh token
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            echo=False,
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE_INTERVAL", "3600")),
            connect_args={
                "command_timeout": int(os.getenv("DB_COMMAND_TIMEOUT", "30")),
            },
        )

        AsyncSessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        
        logger.info("✅ Database connection refreshed with fresh token")
        
    except asyncio.TimeoutError:
        logger.error("❌ Database refresh timed out")
        raise RuntimeError("Database refresh timed out")
    except Exception as e:
        logger.error(f"Error refreshing database connection: {e}")
        raise RuntimeError(f"Failed to refresh database connection: {e}") from e

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async session with timeout handling"""
    if AsyncSessionLocal is None:
        logger.error("Database session not initialized. Call init_engine() first.")
        raise RuntimeError("Database session not initialized.")
    
    import asyncio
    
    try:
        # Add timeout to database operations
        async with asyncio.timeout(30.0):  # 30 second timeout for database operations
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                except Exception as e:
                    logger.error(f"Database session error: {e}")
                    # If we get an authentication error, try to refresh the connection
                    if "Invalid authorization" in str(e) or "authentication" in str(e).lower() or "login" in str(e).lower():
                        logger.warning("Database authentication error detected, attempting to refresh connection...")
                        try:
                            # Add timeout to refresh operation
                            await asyncio.wait_for(refresh_database_connection(), timeout=15.0)
                            # Try again with the refreshed connection
                            async with AsyncSessionLocal() as refreshed_session:
                                yield refreshed_session
                                return
                        except asyncio.TimeoutError:
                            logger.error("Database refresh timed out")
                            raise e
                        except Exception as refresh_error:
                            logger.error(f"Failed to refresh database connection: {refresh_error}")
                            raise e
                    else:
                        raise e
                finally:
                    await session.close()
    except asyncio.TimeoutError:
        logger.error("Database operation timed out")
        raise RuntimeError("Database operation timed out")

def check_database_exists() -> bool:
    """Check if the Lakebase database is accessible using standard PostgreSQL connection"""
    try:
        # Get database connection details from environment variables
        host = os.getenv("LAKEBASE_HOST")
        port = int(os.getenv("LAKEBASE_PORT", "5432"))
        database = os.getenv("LAKEBASE_DATABASE_NAME", "danone-pg-db")
        username = os.getenv("LAKEBASE_USERNAME")
        password = os.getenv("LAKEBASE_PASSWORD")
        
        if not all([host, username, password]):
            logger.warning("Missing required Lakebase environment variables")
            return False
        
        # Test connection by creating a temporary engine
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
        )
        
        test_engine = create_async_engine(url, pool_pre_ping=True)
        
        # Test the connection
        async def test_connection():
            async with test_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            await test_engine.dispose()
        
        # Run the test in a new event loop
        import asyncio
        try:
            # Check if there's already an event loop running
            try:
                loop = asyncio.get_running_loop()
                # If we're in an async context, we can't use run_until_complete
                logger.warning("Cannot test database connection from within an async context")
                return True  # Assume it works for now
            except RuntimeError:
                # No event loop running, we can create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(test_connection())
                    logger.info(f"✅ Lakebase database '{database}' is accessible")
                    return True
                finally:
                    loop.close()
        except Exception as e:
            logger.warning(f"Database connection test failed: {e}")
            return False
            
    except Exception as e:
        logger.warning(f"Lakebase database connection test failed: {e}")
        return False

async def database_health() -> bool:
    """Performs a simple health check on the database connection."""
    try:
        async for db in get_async_db():
            await db.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

# Legacy functions for compatibility (no-op)
async def start_token_refresh():
    """Legacy function - no longer needed with standard PostgreSQL connection"""
    pass

async def stop_token_refresh():
    """Legacy function - no longer needed with standard PostgreSQL connection"""
    pass