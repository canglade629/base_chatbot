"""
Model serving utilities for Databricks serving endpoints.
Uses MLflow deployments client for reliable endpoint communication.
"""

import logging
import os
import requests
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def clean_and_format_content(content: str) -> str:
    """Clean reference markers and format numbered steps in the content."""
    import re
    
    if not isinstance(content, str):
        content = str(content)
    
    # Remove all reference markers (pattern: [^letters-numbers])
    content = re.sub(r'\[\^[A-Za-z0-9-]+\]', '', content)
    
    # Clean up extra whitespace and newlines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Remove excessive newlines
    content = re.sub(r' +', ' ', content)  # Remove extra spaces
    content = content.strip()
    
    # Format numbered steps
    content = format_numbered_steps(content)
    
    # Fix any leading colons at the beginning of paragraphs
    # This addresses the specific issue where colons appear at the start of paragraphs
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # Remove leading colon followed by whitespace at the start of a line
        if line.strip().startswith(':'):
            line = line.strip()[1:].strip()
        fixed_lines.append(line)
    content = '\n'.join(fixed_lines)
    
    return content

def format_numbered_steps(content: str) -> str:
    """Format numbered steps in the content to proper markdown format."""
    import re
    
    # Pattern to match various step formats
    patterns = [
        # Match "1.", "2.", "3." etc. at start of line
        (r'^(\d+)\.\s+', r'\1. '),
        # Match "Step 1:", "Step 2:", etc. - more specific pattern
        (r'^Step\s+(\d+):\s*', r'\1. '),
        # Match "1)", "2)", "3)" etc.
        (r'^(\d+)\)\s+', r'\1. '),
        # Match "• 1.", "• 2.", etc.
        (r'•\s*(\d+)\.\s+', r'\1. '),
        # Match "- 1.", "- 2.", etc.
        (r'-\s*(\d+)\.\s+', r'\1. '),
    ]
    
    lines = content.split('\n')
    formatted_lines = []
    
    for line in lines:
        formatted_line = line
        for pattern, replacement in patterns:
            formatted_line = re.sub(pattern, replacement, formatted_line)
        formatted_lines.append(formatted_line)
    
    return '\n'.join(formatted_lines)

def get_databricks_token() -> str:
    """Get Databricks token from various sources."""
    try:
        logger.info("🔑 Attempting to get Databricks token...")
        
        # First try to get token from metadata service (for Databricks Apps)
        try:
            logger.info("🔍 Trying metadata service...")
            r = requests.get("http://localhost:8787/api/2.0/app-auth/token", timeout=5.0)
            if r.status_code == 200:
                response_data = r.json()
                if "access_token" in response_data:
                    token = response_data["access_token"]
                    logger.info("✅ Got token from metadata service")
                    return token
                else:
                    logger.warning(f"Metadata service response missing access_token: {response_data}")
            else:
                logger.warning(f"Metadata service returned status {r.status_code}: {r.text}")
        except Exception as e:
            logger.warning(f"Metadata service not available: {e}")
        
        # Try to get token from environment variables (multiple possible names)
        env_vars = ['DATABRICKS_TOKEN', 'DBT_PROFILES_DIR', 'DATABRICKS_HOST']
        for env_var in env_vars:
            token = os.getenv(env_var)
            if token and token != "your-databricks-token-here" and len(token) > 10:
                logger.info(f"✅ Got token from {env_var} environment variable")
                return token
        
        # Try to get token from Databricks SDK with different configurations
        try:
            logger.info("🔍 Trying Databricks SDK...")
            from databricks.sdk import WorkspaceClient
            
            # Try with default configuration
            try:
                w = WorkspaceClient()
                token = w.config.token
                if token and len(token) > 10:
                    logger.info("✅ Got token from Databricks SDK (default config)")
                    return token
            except Exception as e:
                logger.warning(f"Databricks SDK default config failed: {e}")
            
            # Try with explicit configuration
            try:
                w = WorkspaceClient(
                    host=os.getenv('DATABRICKS_HOST', 'https://adb-184869479979522.2.azuredatabricks.net'),
                    token=os.getenv('DATABRICKS_TOKEN')
                )
                token = w.config.token
                if token and len(token) > 10:
                    logger.info("✅ Got token from Databricks SDK (explicit config)")
                    return token
            except Exception as e:
                logger.warning(f"Databricks SDK explicit config failed: {e}")
                
        except Exception as e:
            logger.warning(f"Databricks SDK not available: {e}")
        
        # Try to get token from Databricks CLI
        try:
            logger.info("🔍 Trying Databricks CLI...")
            import subprocess
            result = subprocess.run(['databricks', 'auth', 'token'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
                if len(token) > 10:
                    logger.info("✅ Got token from Databricks CLI")
                    return token
        except Exception as e:
            logger.warning(f"Databricks CLI not available: {e}")
        
        # Last resort: try to get from any environment variable that might contain a token
        logger.info("🔍 Searching all environment variables for potential tokens...")
        for key, value in os.environ.items():
            if 'token' in key.lower() and value and len(value) > 20 and value != "your-databricks-token-here":
                logger.info(f"✅ Found potential token in {key}")
                return value
        
        raise Exception("No valid token found from any source")
        
    except Exception as e:
        logger.error(f"Error getting Databricks token: {e}")
        raise Exception(f"Failed to get Databricks token: {e}")

def _get_endpoint_task_type(endpoint_name: str) -> str:
    """Get the task type of a serving endpoint."""
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        ep = w.serving_endpoints.get(endpoint_name)
        return ep.task
    except Exception as e:
        logger.error(f"Error getting endpoint task type: {e}")
        raise

def is_endpoint_supported(endpoint_name: str) -> bool:
    """Check if the endpoint has a supported task type."""
    try:
        task_type = _get_endpoint_task_type(endpoint_name)
        supported_task_types = ["agent/v1/chat", "agent/v2/chat", "llm/v1/chat", "agent/v1/responses"]
        return task_type in supported_task_types
    except Exception as e:
        logger.error(f"Error checking endpoint support: {e}")
        return False

def _validate_endpoint_task_type(endpoint_name: str) -> None:
    """Validate that the endpoint has a supported task type."""
    if not is_endpoint_supported(endpoint_name):
        raise Exception(
            f"Detected unsupported endpoint type for this basic chatbot template. "
            f"This chatbot template only supports chat completions-compatible endpoints. "
            f"For a richer chatbot template with support for all conversational endpoints on Databricks, "
            f"see https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app"
        )

async def _query_endpoint(endpoint_name: str, messages: List[Dict[str, str]], max_tokens: int = 1000) -> List[Dict[str, str]]:
    """Calls a model serving endpoint using MLflow deployments client."""
    try:
        logger.info(f"🔍 Querying endpoint: {endpoint_name}")
        logger.info(f"📝 Messages: {messages}")
        logger.info(f"🎯 Max tokens: {max_tokens}")
        
        # Get endpoint task type
        task_type = _get_endpoint_task_type(endpoint_name)
        logger.info(f"🎯 Endpoint task type: {task_type}")
        
        # Use Databricks SDK's built-in serving endpoint client
        import asyncio
        
        logger.info("🚀 Using Databricks SDK serving endpoint client...")
        
        # Use Databricks SDK's built-in serving endpoint client
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        
        # Handle different endpoint types using Databricks SDK
        if task_type == "agent/v1/responses":
            # Agent endpoints - use the SDK's serving endpoint client
            logger.info(f"🤖 Using Databricks SDK for agent endpoint")
            
            # Convert messages to the format expected by agent endpoints
            input_messages = []
            for msg in messages:
                if msg.get("role") == "user":
                    input_messages.append({
                        "role": "user",
                        "content": msg.get("content", "")
                    })
            
            if not input_messages:
                # If no user message found, create one from all messages
                combined_content = " ".join([msg.get("content", "") for msg in messages if msg.get("content")])
                input_messages = [{"role": "user", "content": combined_content}]
            
            logger.info(f"🤖 Agent endpoint - input messages: {input_messages}")
            
            # Use Databricks SDK's serving endpoint client
            try:
                res = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: w.serving_endpoints.query(
                            name=endpoint_name,
                            dataframe_records=[{
                                "input": input_messages,
                                "max_output_tokens": min(max_tokens, 500),
                                "temperature": 0.1
                            }]
                        )
                    ),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout calling agent endpoint {endpoint_name}")
                raise Exception(f"Agent endpoint {endpoint_name} timed out after 30 seconds")
        else:
            # Standard chat completion endpoints
            logger.info(f"💬 Using Databricks SDK for chat endpoint")
            
            try:
                res = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: w.serving_endpoints.query(
                            name=endpoint_name,
                            dataframe_records=[{
        "messages": messages,
        "max_tokens": max_tokens
                            }]
                        )
                    ),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout calling chat endpoint {endpoint_name}")
                raise Exception(f"Chat endpoint {endpoint_name} timed out after 30 seconds")
        
        logger.info(f"📡 Raw response type: {type(res)}")
        logger.info(f"📡 Raw response: {res}")
        
        # Handle Databricks SDK responses
        if task_type == "agent/v1/responses":
            # Agent endpoints return responses with output array
            logger.info("🤖 Processing agent response...")
            try:
                # Databricks SDK returns a response object with predictions
                if hasattr(res, 'predictions') and res.predictions:
                    prediction = res.predictions
                    if isinstance(prediction, dict):
                        # Look for the specific structure: predictions['output'][0]['content'][0]['text']
                        if 'output' in prediction and isinstance(prediction['output'], list) and len(prediction['output']) > 0:
                            output_item = prediction['output'][0]
                            if isinstance(output_item, dict) and 'content' in output_item:
                                content_list = output_item['content']
                                if isinstance(content_list, list) and len(content_list) > 0:
                                    # Extract text from content array
                                    text_parts = []
                                    for content_item in content_list:
                                        if isinstance(content_item, dict) and 'text' in content_item:
                                            text_parts.append(content_item['text'])
                                        elif isinstance(content_item, str):
                                            text_parts.append(content_item)
                                    content = " ".join(text_parts) if text_parts else str(output_item)
                                else:
                                    content = str(output_item)
                            else:
                                content = str(output_item)
                        elif 'response' in prediction:
                            content = prediction['response']
                        elif 'content' in prediction:
                            content = prediction['content']
                        else:
                            content = str(prediction)
                    else:
                        content = str(prediction)
                else:
                    # Fallback: try to extract from the response object directly
                    if hasattr(res, 'predictions') and res.predictions:
                        content = str(res.predictions)
                    else:
                        content = str(res)
                
                # Clean up the content
                if isinstance(content, str):
                    # Extract just the text part if it's a long response object string
                    if 'text\': \'' in content:
                        # Try to extract the actual text content
                        import re
                        # More robust pattern that handles escaped quotes
                        text_match = re.search(r"text': '([^']*(?:\\'[^']*)*)'", content)
                        if text_match:
                            content = text_match.group(1)
                    
                    # Clean and format the content
                    content = clean_and_format_content(content)
                
                return [{"role": "assistant", "content": content}]
            except Exception as e:
                logger.error(f"❌ Error processing agent response: {e}")
                return [{"role": "assistant", "content": str(res)}]
        else:
            # Chat completion endpoints
            logger.info("💬 Processing chat completion response...")
            try:
                # Databricks SDK returns a response object with predictions
                if hasattr(res, 'predictions') and res.predictions:
                    prediction = res.predictions[0]
                    if isinstance(prediction, dict):
                        if 'choices' in prediction and isinstance(prediction['choices'], list):
                            choice = prediction['choices'][0]
                            if isinstance(choice, dict) and 'message' in choice:
                                message = choice['message']
                                if isinstance(message, dict) and 'content' in message:
                                    content = clean_and_format_content(message['content'])
                                    return [{"role": "assistant", "content": content}]
                                else:
                                    return [{"role": "assistant", "content": str(message)}]
                            else:
                                return [{"role": "assistant", "content": str(choice)}]
                        elif 'response' in prediction:
                            content = clean_and_format_content(prediction['response'])
                            return [{"role": "assistant", "content": content}]
                        elif 'content' in prediction:
                            content = clean_and_format_content(prediction['content'])
                            return [{"role": "assistant", "content": content}]
                        else:
                            return [{"role": "assistant", "content": str(prediction)}]
                    else:
                        return [{"role": "assistant", "content": str(prediction)}]
                else:
                    return [{"role": "assistant", "content": str(res)}]
            except Exception as e:
                logger.error(f"❌ Error processing chat response: {e}")
                return [{"role": "assistant", "content": str(res)}]
        
        logger.error(f"❌ Unexpected response format: {res} (type: {type(res)})")
        raise Exception(f"Unexpected response format from endpoint: {res}")
                        
    except Exception as e:
        logger.error(f"❌ Error calling serving endpoint: {e}")
        raise Exception(f"Error calling serving endpoint: {e}")

def _parse_agent_response(res) -> List[Dict[str, str]]:
    """Parse agent endpoint response format."""
    try:
        logger.info(f"🤖 Parsing agent response: {res}")
        
        # Agent responses typically have different structures
        if isinstance(res, dict):
            # Look for common agent response fields
            if "response" in res:
                content = res["response"]
            elif "content" in res:
                content = res["content"]
            elif "message" in res:
                content = res["message"]
            elif "text" in res:
                content = res["text"]
            elif "answer" in res:
                content = res["answer"]
            elif "output" in res and isinstance(res["output"], list) and len(res["output"]) > 0:
                # Handle complex agent response with output array
                output_item = res["output"][0]
                if isinstance(output_item, dict) and "content" in output_item:
                    content_list = output_item["content"]
                    if isinstance(content_list, list) and len(content_list) > 0:
                        # Extract text from content array
                        text_parts = []
                        for content_item in content_list:
                            if isinstance(content_item, dict) and "text" in content_item:
                                text_parts.append(content_item["text"])
                            elif isinstance(content_item, str):
                                text_parts.append(content_item)
                        content = " ".join(text_parts) if text_parts else str(output_item)
                    else:
                        content = str(output_item)
                else:
                    content = str(output_item)
            else:
                # Try to extract text from any string field
                content = str(res)
            
            # Clean up the content - remove any unwanted characters
            if isinstance(content, str):
                # Remove the [^FdJd-1] references that appear in the response
                content = content.replace('[^FdJd-1]', '').strip()
            
            return [{"role": "assistant", "content": str(content)}]
        
        elif isinstance(res, str):
            return [{"role": "assistant", "content": res}]
        
        else:
            # Convert to string as fallback
            return [{"role": "assistant", "content": str(res)}]
                
    except Exception as e:
        logger.error(f"❌ Error parsing agent response: {e}")
        return [{"role": "assistant", "content": str(res)}]

async def query_endpoint(endpoint_name: str, messages: List[Dict[str, str]], max_tokens: int = 1000) -> Dict[str, str]:
    """
    Query a serving endpoint and return the last message.
    This matches the interface expected by the working Gradio app.
    
    Args:
        endpoint_name: Name of the serving endpoint
        messages: List of message dictionaries with 'role' and 'content' keys
        max_tokens: Maximum number of tokens to generate
        
    Returns:
        The last message from the endpoint response (dict with 'role' and 'content' keys)
    """
    try:
        logger.info(f"🎯 Querying endpoint {endpoint_name} with {len(messages)} messages")
        
        # Clean messages to remove any leading underscores from field names
        cleaned_messages = []
        for msg in messages:
            cleaned_msg = {}
            for key, value in msg.items():
                # Remove leading underscores from field names
                clean_key = key.lstrip('_') if key.startswith('_') else key
                cleaned_msg[clean_key] = value
            cleaned_messages.append(cleaned_msg)
        
        logger.info(f"🧹 Cleaned messages: {cleaned_messages}")
        
        # Call the endpoint
        response_messages = await _query_endpoint(endpoint_name, cleaned_messages, max_tokens)
        
        if not response_messages:
            raise Exception("No response messages received from endpoint")
        
        # Return the last message (should have 'role' and 'content' keys)
        last_message = response_messages[-1]
        logger.info(f"✅ Endpoint response: {last_message}")
        
        # Ensure the response has the expected format
        if not isinstance(last_message, dict):
            raise Exception(f"Unexpected response format: {last_message}")
        
        if 'content' not in last_message:
            raise Exception(f"Response missing 'content' field: {last_message}")
            
        return last_message
        
    except Exception as e:
        logger.error(f"❌ Error in query_endpoint: {e}")
        raise Exception(f"Error querying endpoint: {e}")

def get_serving_endpoint_name() -> str:
    """Get the serving endpoint name from environment variables."""
    endpoint_name = os.getenv("SERVING_ENDPOINT")
    if not endpoint_name:
        raise Exception("SERVING_ENDPOINT environment variable not set")
    return endpoint_name