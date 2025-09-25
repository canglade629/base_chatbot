import logging
from typing import Dict, Any
import json
import os

logger = logging.getLogger(__name__)

def load_environment_config(environment: str = "development") -> Dict[str, Any]:
    """Load environment configuration from environments.json"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "databricks-setup", "environments.json")
        with open(config_path, 'r') as f:
            configs = json.load(f)
        return configs.get(environment, {})
    except Exception as e:
        logger.error(f"Error loading environment config: {e}")
        return {}

def get_lakebase_connection_config(environment: str = "development") -> Dict[str, Any]:
    """
    Get Lakebase connection configuration for Databricks App environment.
    
    In a Databricks App, the database connection is managed by the platform,
    so we use environment variables that Databricks Apps provide.
    """
    config = load_environment_config(environment)
    
    # Try to get connection details from environment variables first (Databricks App way)
    import os
    
    # Check for Databricks App environment variables
    db_host = os.getenv("DATABRICKS_DATABASE_HOST") or os.getenv("LAKEBASE_HOST")
    db_port = int(os.getenv("DATABRICKS_DATABASE_PORT", os.getenv("LAKEBASE_PORT", "5432")))
    db_name = os.getenv("DATABRICKS_DATABASE_NAME") or os.getenv("LAKEBASE_DATABASE_NAME") or config.get("lakebase_database_name", "onesource-chatbot-pg")
    db_user = os.getenv("DATABRICKS_DATABASE_USER") or os.getenv("LAKEBASE_USERNAME")
    db_password = os.getenv("DATABRICKS_DATABASE_PASSWORD") or os.getenv("LAKEBASE_PASSWORD")
    
    # If no environment variables, try to use the config values
    if not db_host:
        db_host = config.get("postgres_host") or "localhost"
    if not db_user:
        db_user = config.get("postgres_user") or "postgres"
    if not db_password:
        db_password = config.get("postgres_password") or "password"
    
    lakebase_config = {
        "host": db_host,
        "port": db_port,
        "database": db_name,
        "username": db_user,
        "password": db_password,
        "schema": config.get("lakebase_schema", "public"),
        "admin_role": "postgres",
        "lakebase_database_name": db_name,
        "lakebase_schema": config.get("lakebase_schema", "public"),
        "unity_catalog": config.get("unity_catalog"),
        "unity_catalog_schema": config.get("unity_catalog_schema"),
        "unity_catalog_volume": config.get("unity_catalog_volume"),
        "warehouse_name": config.get("warehouse_name"),
        "vector_search_database_name": config.get("vector_search_database_name")
    }
    
    logger.info(f"Lakebase connection config loaded for {environment}")
    logger.info(f"Database: {lakebase_config['database']}, Host: {lakebase_config['host']}, Port: {lakebase_config['port']}")
    logger.info(f"Using environment variables: {bool(os.getenv('DATABRICKS_DATABASE_HOST'))}")
    
    return lakebase_config

def get_databricks_config(environment: str = "development") -> Dict[str, Any]:
    """
    Get Databricks configuration for the app.
    """
    config = load_environment_config(environment)
    
    return {
        "host": config.get("databricks_host"),
        "token": config.get("databricks_token"),
        "app_name": config.get("databricks_app_name"),
        "profile": config.get("databricks_profile"),
        "unity_catalog": config.get("unity_catalog"),
        "unity_catalog_schema": config.get("unity_catalog_schema"),
        "unity_catalog_volume": config.get("unity_catalog_volume"),
        "warehouse_name": config.get("warehouse_name"),
        "vector_search_database_name": config.get("vector_search_database_name")
    }