#!/usr/bin/env python3
"""
Lakebase Schema and Tables Initialization Script

This script creates the superuser role, schema, and necessary tables in the Lakebase PostgreSQL database.
It can be run independently after the main setup is complete.

Features:
- Creates superuser role for the app's service principal
- Creates database schema and tables
- Verifies table creation and accessibility

Usage:
    python init_tables.py --environment <env_name>
    python init_tables.py --environment development
"""

import argparse
import json
import sys
from pathlib import Path
from config_manager import ConfigManager, EnvironmentConfig
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    DatabaseInstanceRole,
    DatabaseInstanceRoleIdentityType,
    DatabaseInstanceRoleMembershipRole,
    DatabaseInstanceRoleAttributes
)


class LakebaseTableInitializer:
    """Initialize tables in Lakebase PostgreSQL database"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.results = {
            "steps_completed": [],
            "errors": [],
            "warnings": []
        }
    
    def run_cli_command(self, command, description):
        """Run a CLI command and return the result"""
        import subprocess
        import os
        
        print(f"🔄 {description}...")
        
        # Set SSL environment variables for psql
        env = os.environ.copy()
        env['PGSSLMODE'] = 'require'
        env['PGSSLROOTCERT'] = ''
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            return {
                "success": True,
                "output": result.stdout,
                "error": result.stderr
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "output": e.stdout,
                "error": e.stderr
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
    
    def create_superuser_role(self) -> bool:
        """Create superuser role for the app's service principal"""
        print(f"🔧 Creating superuser role for Lakebase database...")
        
        try:
            # Initialize Databricks SDK client
            workspace_client = WorkspaceClient()
            
            # Get the current user (service principal) name
            current_user = workspace_client.current_user.me()
            service_principal_name = current_user.user_name
            
            print(f"📋 Service principal: {service_principal_name}")
            
            # Create superuser role
            superuser_role = DatabaseInstanceRole(
                name=service_principal_name,
                identity_type=DatabaseInstanceRoleIdentityType.USER,
                membership_role=DatabaseInstanceRoleMembershipRole.DATABRICKS_SUPERUSER,
                attributes=DatabaseInstanceRoleAttributes(
                    bypassrls=True, 
                    createdb=True, 
                    createrole=True
                ),
            )
            
            # Create the role in the database instance
            # Use the instance name from config (which should be the Lakebase instance name)
            instance_name = self.config.lakebase_database_name  # This is "onesource-chatbot-pg"
            workspace_client.database.create_database_instance_role(
                instance_name=instance_name,
                database_instance_role=superuser_role
            )
            
            print(f"✅ Superuser role created successfully for {service_principal_name}")
            self.results["steps_completed"].append("superuser_role_created")
            return True
            
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"✅ Superuser role already exists for {service_principal_name}")
                self.results["steps_completed"].append("superuser_role_exists")
                return True
            else:
                print(f"❌ Failed to create superuser role: {e}")
                self.results["errors"].append(f"Superuser role creation failed: {e}")
                return False

    def check_lakebase_connection(self) -> bool:
        """Check if Lakebase database instance is accessible"""
        print(f"🔍 Checking Lakebase database connection...")
        
        # Test connection by listing databases
        # Use instance name for psql command, but actual database name for -d flag
        instance_name = self.config.lakebase_database_name  # Instance name from config
        database_name = getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')  # PostgreSQL database name from config
        
        test_result = self.run_cli_command([
            "databricks", "psql", "-p", self.config.databricks_profile, instance_name, "--",
            "-d", database_name,
            "-c", "SELECT current_database();"
        ], "Test Lakebase connection")
        
        if test_result["success"]:
            print(f"✅ Lakebase database '{database_name}' on instance '{instance_name}' is accessible")
            self.results["steps_completed"].append("connection_verified")
            return True
        else:
            print(f"❌ Cannot connect to Lakebase database '{database_name}' on instance '{instance_name}': {test_result['error']}")
            self.results["errors"].append(f"Lakebase connection failed: {test_result['error']}")
            return False
    
    def create_schema(self) -> bool:
        """Create the Lakebase schema"""
        print(f"🔄 Create Lakebase schema...")
        
        # Use the public schema instead of creating a custom schema
        # This matches the app's configuration which uses the default schema
        instance_name = self.config.lakebase_database_name  # Instance name from config
        database_name = getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')  # PostgreSQL database name from config
        
        schema_result = self.run_cli_command([
            "databricks", "psql", "-p", self.config.databricks_profile, instance_name, "--",
            "-d", database_name,
            "-c", "SELECT current_schema();"
        ], "Check current schema")
        
        if schema_result["success"]:
            print(f"✅ Using public schema (default)")
            self.results["steps_completed"].append("schema_verified")
            return True
        else:
            print(f"❌ Schema check failed: {schema_result['error']}")
            self.results["errors"].append(f"Schema check failed: {schema_result['error']}")
            return False
    
    def create_tables(self) -> bool:
        """Create all necessary tables in the Lakebase schema"""
        print(f"📋 Creating tables in public schema...")
        
        # Define table creation SQL - Updated to match app's SQLAlchemy models
        # Using public schema (default) instead of custom schema
        tables_sql = [
            """
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                display_name VARCHAR(255),
                username VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP WITH TIME ZONE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
            """
        ]
        
        # Create tables
        instance_name = self.config.lakebase_database_name  # Instance name from config
        database_name = getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')  # PostgreSQL database name from config
        
        success_count = 0
        for i, sql in enumerate(tables_sql, 1):
            result = self.run_cli_command([
                "databricks", "psql", "-p", self.config.databricks_profile, instance_name, "--",
                "-d", database_name,
                "-c", sql.strip()
            ], f"Create table {i}/{len(tables_sql)}")
            
            if result["success"]:
                print(f"✅ Table {i}/{len(tables_sql)} created successfully")
                success_count += 1
            else:
                # Check if table already exists
                if "already exists" in result.get("error", "").lower():
                    print(f"✅ Table {i}/{len(tables_sql)} already exists")
                    success_count += 1
                else:
                    print(f"❌ Table {i}/{len(tables_sql)} creation failed: {result['error']}")
                    self.results["errors"].append(f"Table {i} creation failed: {result['error']}")
        
        if success_count == len(tables_sql):
            print(f"✅ All {len(tables_sql)} tables created successfully")
            self.results["steps_completed"].append("tables_created")
            return True
        else:
            print(f"⚠️ {success_count}/{len(tables_sql)} tables created successfully")
            self.results["warnings"].append(f"Only {success_count}/{len(tables_sql)} tables created")
            return success_count > 0
    
    def verify_tables(self) -> bool:
        """Verify that all tables exist and are accessible"""
        print(f"🔍 Verifying tables in public schema...")
        
        # List tables in the public schema
        instance_name = self.config.lakebase_database_name  # Instance name from config
        database_name = getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')  # PostgreSQL database name from config
        
        verify_result = self.run_cli_command([
            "databricks", "psql", "-p", self.config.databricks_profile, instance_name, "--",
            "-d", database_name,
            "-c", "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('users', 'conversations');"
        ], "Verify tables exist")
        
        if verify_result["success"]:
            print(f"✅ Tables verification successful")
            print(f"📋 Tables in public schema:")
            print(verify_result["output"])
            self.results["steps_completed"].append("tables_verified")
            return True
        else:
            print(f"❌ Tables verification failed: {verify_result['error']}")
            self.results["errors"].append(f"Tables verification failed: {verify_result['error']}")
            return False
    
    def run_initialization(self) -> bool:
        """Run the complete Lakebase schema and tables initialization process"""
        print("🚀 Starting Lakebase schema and tables initialization")
        print(f"Environment: {self.config.name}")
        print(f"Base Name: {self.config.base_name}")
        print(f"Databricks Profile: {self.config.databricks_profile}")
        print(f"Lakebase Instance: {self.config.lakebase_database_name}")
        print(f"Lakebase Database: {getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')}")
        print(f"Lakebase Schema: {self.config.lakebase_schema}")
        print("=" * 60)
        
        success = True
        
        # Step 1: Check Lakebase connection
        print("\n📋 STEP 1: Checking Lakebase Connection")
        print("-" * 40)
        if not self.check_lakebase_connection():
            success = False
            print("❌ Cannot proceed without Lakebase connection")
            return False
        
        # Step 2: Create superuser role
        print("\n📋 STEP 2: Creating Superuser Role")
        print("-" * 40)
        if not self.create_superuser_role():
            success = False
            print("⚠️ Superuser role creation failed, but continuing with table creation")
        
        # Step 3: Verify schema
        print("\n📋 STEP 3: Verifying Schema")
        print("-" * 40)
        if not self.create_schema():
            success = False
        
        # Step 4: Create tables
        print("\n📋 STEP 4: Creating Tables")
        print("-" * 40)
        if not self.create_tables():
            success = False
        
        # Step 5: Verify tables
        print("\n📋 STEP 5: Verifying Tables")
        print("-" * 40)
        if not self.verify_tables():
            success = False
        
        # Print results
        print("\n" + "=" * 60)
        print("📊 INITIALIZATION RESULTS")
        print("=" * 60)
        print(f"Environment: {self.config.name}")
        print(f"Base Name: {self.config.base_name}")
        print(f"Databricks Profile: {self.config.databricks_profile}")
        print(f"Lakebase Instance: {self.config.lakebase_database_name}")
        print(f"Lakebase Database: {getattr(self.config, 'lakebase_postgres_database', 'databricks_postgres')}")
        print(f"Lakebase Schema: {self.config.lakebase_schema}")
        
        if self.results["steps_completed"]:
            print(f"\n✅ Completed Steps ({len(self.results['steps_completed'])}):")
            for step in self.results["steps_completed"]:
                print(f"  • {step}")
        
        if self.results["warnings"]:
            print(f"\n⚠️ Warnings ({len(self.results['warnings'])}):")
            for warning in self.results["warnings"]:
                print(f"  • {warning}")
        
        if self.results["errors"]:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for error in self.results["errors"]:
                print(f"  • {error}")
            success = False
        
        if success:
            print("\n🎉 Tables initialization completed successfully!")
        else:
            print("\n❌ Tables initialization completed with errors!")
        
        return success


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Initialize Lakebase tables")
    parser.add_argument(
        "--environment", 
        required=True,
        help="Environment name (e.g., development, production)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        manager = ConfigManager()
        config = manager.load_environment_config(args.environment)
        
        if not config:
            print(f"❌ Environment '{args.environment}' not found")
            print("Available environments:")
            for env_name in manager.list_environments():
                print(f"  - {env_name}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize tables
    initializer = LakebaseTableInitializer(config)
    success = initializer.run_initialization()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
