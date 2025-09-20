"""
Configuration Manager for base-chatbot
Handles environment-specific configurations and parameterized base names
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class EnvironmentConfig:
    """Configuration for a specific environment"""
    name: str
    base_name: str
    databricks_app_name: str
    databricks_profile: str
    databricks_host: str
    databricks_token: str
    lakebase_database_name: str
    unity_catalog: str
    unity_catalog_schema: str
    unity_catalog_volume: str
    warehouse_name: str
    vector_search_database_name: str
    lakebase_schema: str
    postgres_host: Optional[str] = None
    postgres_port: Optional[int] = None
    postgres_db: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_schema: Optional[str] = None
    postgres_admin_role: Optional[str] = None

class ConfigManager:
    """Manages configuration across different environments"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            # Use the same directory as this script
            self.config_dir = Path(__file__).parent
        else:
            self.config_dir = Path(config_dir)
        self.environments_file = self.config_dir / "environments.json"
        self.current_env = os.getenv("ENVIRONMENT", "development")
        
    def load_environment_config(self, env_name: str = None) -> EnvironmentConfig:
        """Load configuration for a specific environment"""
        if env_name is None:
            env_name = self.current_env
            
        # Try to load from environments.json first
        if self.environments_file.exists():
            with open(self.environments_file, 'r') as f:
                environments = json.load(f)
                if env_name in environments:
                    env_data = environments[env_name]
                    return EnvironmentConfig(**env_data)
        
        # Fallback to environment variables
        return self._load_from_env_vars(env_name)
    
    def _load_from_env_vars(self, env_name: str) -> EnvironmentConfig:
        """Load configuration from environment variables"""
        base_name = os.getenv("BASE_NAME", "base-chatbot")
        
        return EnvironmentConfig(
            name=env_name,
            base_name=base_name,
            databricks_profile=os.getenv("DATABRICKS_PROFILE", "dbxworkspace"),
            databricks_host=os.getenv("DATABRICKS_HOST", ""),
            databricks_token=os.getenv("DATABRICKS_TOKEN", ""),
            lakebase_database_name=os.getenv("LAKEBASE_DATABASE", base_name),
            lakebase_catalog=os.getenv("LAKEBASE_CATALOG", base_name),
            lakebase_schema=os.getenv("LAKEBASE_SCHEMA", base_name),
            postgres_host=os.getenv("POSTGRES_HOST"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")) if os.getenv("POSTGRES_PORT") else None,
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_schema=os.getenv("POSTGRES_SCHEMA"),
            postgres_admin_role=os.getenv("POSTGRES_ADMIN_ROLE")
        )
    
    def save_environment_config(self, config: EnvironmentConfig):
        """Save configuration for an environment"""
        environments = {}
        if self.environments_file.exists():
            with open(self.environments_file, 'r') as f:
                environments = json.load(f)
        
        environments[config.name] = {
            "name": config.name,
            "base_name": config.base_name,
            "databricks_app_name": config.databricks_app_name,
            "databricks_profile": config.databricks_profile,
            "databricks_host": config.databricks_host,
            "databricks_token": config.databricks_token,
            "lakebase_database_name": config.lakebase_database_name,
            "unity_catalog": config.unity_catalog,
            "unity_catalog_schema": config.unity_catalog_schema,
            "unity_catalog_volume": config.unity_catalog_volume,
            "warehouse_name": config.warehouse_name,
            "vector_search_database_name": config.vector_search_database_name,
            "lakebase_schema": config.lakebase_schema,
            "postgres_host": config.postgres_host,
            "postgres_port": config.postgres_port,
            "postgres_db": config.postgres_db,
            "postgres_user": config.postgres_user,
            "postgres_password": config.postgres_password,
            "postgres_schema": config.postgres_schema,
            "postgres_admin_role": config.postgres_admin_role
        }
        
        with open(self.environments_file, 'w') as f:
            json.dump(environments, f, indent=2)
    
    def create_env_file(self, config: EnvironmentConfig, output_file: str = ".env"):
        """Create a .env file from configuration"""
        env_content = f"""# Environment: {config.name}
# Base Name: {config.base_name}
# Generated by config_manager.py

# Environment Configuration
ENVIRONMENT={config.name}
BASE_NAME={config.base_name}

# Database Type (choose one: 'firestore', 'postgresql', 'lakebase_postgres')
DATABASE_TYPE=lakebase_postgres

# Databricks Configuration
DATABRICKS_PROFILE={config.databricks_profile}
DATABRICKS_HOST={config.databricks_host}
DATABRICKS_TOKEN={config.databricks_token}

# Databricks App Configuration (will be retrieved if not set)
DATABRICKS_APP_NAME={config.base_name}
DATABRICKS_APP_URL=
DATABRICKS_APP_ID=
DATABRICKS_OAUTH2_CLIENT_ID=
DATABRICKS_SERVICE_PRINCIPAL_ID=
DATABRICKS_SERVICE_PRINCIPAL_NAME=

# Databricks Lakebase Configuration
LAKEBASE_SCHEMA={config.lakebase_schema}
LAKEBASE_DATABASE={config.lakebase_database_name}

# Databricks Unity Catalog Configuration
UNITY_CATALOG={config.unity_catalog}
UNITY_CATALOG_SCHEMA={config.unity_catalog_schema}
UNITY_CATALOG_VOLUME={config.unity_catalog_volume}

# PostgreSQL Configuration (if using local PostgreSQL)
POSTGRES_HOST={config.postgres_host or 'localhost'}
POSTGRES_PORT={config.postgres_port or 5432}
POSTGRES_DB={config.postgres_db or config.base_name}
POSTGRES_USER={config.postgres_user or f'{config.base_name}_admin_user'}
POSTGRES_PASSWORD={config.postgres_password or f'{config.base_name}_admin_2024!'}
POSTGRES_SCHEMA={config.postgres_schema or config.base_name}
POSTGRES_ADMIN_ROLE={config.postgres_admin_role or f'{config.base_name}_admin'}

# Firestore Configuration (if using Firestore)
FIREBASE_SERVICE_ACCOUNT_PATH=config/firebase-credentials/icc-project-472009-firebase-adminsdk.json

# JWT Configuration
JWT_SECRET_KEY=your-jwt-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application Configuration
DEBUG=true
LOG_LEVEL=INFO
"""
        
        with open(output_file, 'w') as f:
            f.write(env_content)
        
        print(f"✅ Created {output_file} for environment '{config.name}' with base name '{config.base_name}'")
    
    def list_environments(self) -> Dict[str, Dict[str, Any]]:
        """List all configured environments"""
        if not self.environments_file.exists():
            return {}
        
        with open(self.environments_file, 'r') as f:
            return json.load(f)
    
    def validate_config(self, config: EnvironmentConfig) -> Dict[str, Any]:
        """Validate a configuration"""
        errors = []
        warnings = []
        
        # Required fields
        if not config.databricks_host:
            errors.append("DATABRICKS_HOST is required")
        if not config.databricks_token:
            errors.append("DATABRICKS_TOKEN is required")
        if not config.base_name:
            errors.append("BASE_NAME is required")
        
        # Validate base name format
        if config.base_name and not config.base_name.replace('-', '').replace('_', '').isalnum():
            errors.append("BASE_NAME should only contain letters, numbers, hyphens, and underscores")
        
        # Check for common issues
        if config.databricks_host and not config.databricks_host.startswith('https://'):
            warnings.append("DATABRICKS_HOST should start with https://")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

# Global instance
config_manager = ConfigManager()
