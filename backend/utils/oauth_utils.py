"""
OAuth utilities for extracting user information from Databricks OAuth tokens
"""
import logging
from typing import Optional
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)

def get_user_email_from_token(user_token: str) -> Optional[str]:
    """
    Extract user email from OAuth token using Databricks SDK
    
    Args:
        user_token: The OAuth token from X-Forwarded-Access-Token header
        
    Returns:
        User email if successful, None otherwise
    """
    try:
        if not user_token:
            logger.warning("No user token provided")
            return None
            
        logger.info(f"Attempting to extract user email from token (length: {len(user_token)})")
        
        # Create WorkspaceClient with the user's token
        w = WorkspaceClient(token=user_token, auth_type="pat")
        
        # Get the current user information
        user_info = w.current_user.me()
        
        logger.info(f"User info object: {user_info}")
        logger.info(f"User info type: {type(user_info)}")
        logger.info(f"User info attributes: {dir(user_info) if user_info else 'None'}")
        
        if user_info:
            # Try different ways to get the email
            email = None
            
            # Method 1: Direct attribute access
            if hasattr(user_info, 'email'):
                email = user_info.email
                logger.info(f"Found email via direct attribute: {email}")
            
            # Method 2: Try user_name if email not found
            elif hasattr(user_info, 'user_name'):
                email = user_info.user_name
                logger.info(f"Using user_name as email: {email}")
            
            # Method 3: Try display_name if available
            elif hasattr(user_info, 'display_name'):
                email = user_info.display_name
                logger.info(f"Using display_name as email: {email}")
            
            if email:
                logger.info(f"Successfully extracted user email: {email}")
                return email
            else:
                logger.warning("No email found in user info")
                return None
        else:
            logger.warning("No user info returned from token")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting user email from token: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def get_user_info_from_token(user_token: str) -> Optional[dict]:
    """
    Extract full user information from OAuth token using Databricks SDK
    
    Args:
        user_token: The OAuth token from X-Forwarded-Access-Token header
        
    Returns:
        Dictionary with user information if successful, None otherwise
    """
    try:
        if not user_token:
            logger.warning("No user token provided")
            return None
            
        # Create WorkspaceClient with the user's token
        w = WorkspaceClient(token=user_token, auth_type="pat")
        
        # Get the current user information
        user_info = w.current_user.me()
        
        if user_info:
            user_data = {
                "email": getattr(user_info, 'email', None),
                "user_name": getattr(user_info, 'user_name', None),
                "display_name": getattr(user_info, 'display_name', None),
                "user_id": str(getattr(user_info, 'id', None)),
                "groups": [str(group) for group in getattr(user_info, 'groups', [])],
                "roles": [str(role) for role in getattr(user_info, 'roles', [])]
            }
            logger.info(f"Successfully extracted user info for: {user_data.get('email', 'unknown')}")
            return user_data
        else:
            logger.warning("No user info returned from token")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting user info from token: {e}")
        return None
