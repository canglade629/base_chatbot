#!/usr/bin/env python3
"""
Configuration Setup Tool for base-chatbot
Allows easy management of environment-specific configurations
"""

import argparse
import sys
import os
from pathlib import Path

# Add the current directory to the path
sys.path.append(str(Path(__file__).parent))

from config_manager import ConfigManager, EnvironmentConfig

def setup_environment():
    """Interactive setup for a new environment"""
    print("🚀 Setting up a new environment configuration")
    print("=" * 50)
    
    # Get environment name
    env_name = input("Environment name (e.g., development, staging, production): ").strip()
    if not env_name:
        print("❌ Environment name is required")
        return False
    
    # Get base name
    base_name = input(f"Base name (e.g., base-chatbot, my-app): ").strip()
    if not base_name:
        print("❌ Base name is required")
        return False
    
    # Get Databricks configuration
    print("\n📊 Databricks Configuration:")
    databricks_profile = input(f"Databricks profile [{env_name}]: ").strip() or env_name
    databricks_host = input("Databricks host (e.g., https://your-workspace.cloud.databricks.com): ").strip()
    databricks_token = input("Databricks token: ").strip()
    
    # Get Lakebase configuration
    print("\n🏞️ Lakebase Configuration:")
    lakebase_database = input(f"Lakebase database name [{base_name}-pg-db]: ").strip() or f"{base_name}-pg-db"
    lakebase_schema = input(f"Lakebase schema [{base_name}_pg_schema]: ").strip() or f"{base_name}_pg_schema"
    
    # Get Unity Catalog configuration
    print("\n📚 Unity Catalog Configuration:")
    unity_catalog = input(f"Unity Catalog name [{base_name}_uc]: ").strip() or f"{base_name}_uc"
    unity_catalog_schema = input(f"Unity Catalog schema [{base_name}_uc_schema]: ").strip() or f"{base_name}_uc_schema"
    unity_catalog_volume = input(f"Unity Catalog volume [{base_name}_uc_volume]: ").strip() or f"{base_name}_uc_volume"
    
    # Get Warehouse configuration
    print("\n🏭 Warehouse Configuration:")
    warehouse_name = input(f"Warehouse name [{base_name}_wh]: ").strip() or f"{base_name}_wh"
    
    # Get Vector Search configuration
    print("\n🔍 Vector Search Configuration:")
    vector_search_database_name = input(f"Vector Search database name [{base_name}-vs]: ").strip() or f"{base_name}-vs"
    
    
    # Create configuration
    config = EnvironmentConfig(
        name=env_name,
        base_name=base_name,
        databricks_app_name=f"{base_name}-app",
        databricks_profile=databricks_profile,
        databricks_host=databricks_host,
        databricks_token=databricks_token,
        lakebase_database_name=lakebase_database,
        unity_catalog=unity_catalog,
        unity_catalog_schema=unity_catalog_schema,
        unity_catalog_volume=unity_catalog_volume,
        warehouse_name=warehouse_name,
        vector_search_database_name=vector_search_database_name,
        lakebase_schema=lakebase_schema
    )
    
    # Validate configuration
    manager = ConfigManager()
    validation = manager.validate_config(config)
    
    if not validation["valid"]:
        print("\n❌ Configuration validation failed:")
        for error in validation["errors"]:
            print(f"  - {error}")
        return False
    
    if validation["warnings"]:
        print("\n⚠️ Configuration warnings:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")
    
    # Save configuration
    manager.save_environment_config(config)
    print(f"\n✅ Configuration saved for environment '{env_name}'")
    
    return True

def list_environments():
    """List all configured environments"""
    manager = ConfigManager()
    environments = manager.list_environments()
    
    if not environments:
        print("No environments configured")
        return
    
    print("📋 Configured Environments:")
    print("=" * 50)
    for env_name, env_data in environments.items():
        print(f"Environment: {env_name}")
        print(f"  Base Name: {env_data['base_name']}")
        print(f"  Databricks Profile: {env_data['databricks_profile']}")
        print(f"  Databricks Host: {env_data['databricks_host']}")
        print(f"  Lakebase Database: {env_data['lakebase_database_name']}")
        print(f"  Unity Catalog: {env_data['unity_catalog']}")
        print(f"  Warehouse: {env_data.get('warehouse_name', 'Not set')}")
        print(f"  Vector Search DB: {env_data.get('vector_search_database_name', 'Not set')}")
        print(f"  Lakebase Schema: {env_data['lakebase_schema']}")
        if env_data.get('postgres_host'):
            print(f"  PostgreSQL Host: {env_data['postgres_host']}")
        print()

def main():
    parser = argparse.ArgumentParser(description="Configuration management for base-chatbot")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Setup command
    subparsers.add_parser("setup", help="Interactive setup for a new environment")
    
    # List command
    subparsers.add_parser("list", help="List all configured environments")
    
    
    args = parser.parse_args()
    
    if args.command == "setup":
        setup_environment()
    elif args.command == "list":
        list_environments()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
