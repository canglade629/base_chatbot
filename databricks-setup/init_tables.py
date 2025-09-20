#!/usr/bin/env python3
"""
Lakebase Schema and Tables Initialization Script

This script creates the schema and necessary tables in the Lakebase PostgreSQL database.
It can be run independently after the main setup is complete.

Usage:
    python init_tables.py --environment <env_name>
    python init_tables.py --environment development
"""

import argparse
import json
import sys
from pathlib import Path
from config_manager import ConfigManager, EnvironmentConfig


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
        
        print(f"🔄 {description}...")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
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
    
    def check_lakebase_connection(self) -> bool:
        """Check if Lakebase database instance is accessible"""
        print(f"🔍 Checking Lakebase database connection...")
        
        # Test connection by listing databases
        test_result = self.run_cli_command([
            "databricks", "psql", "-p", "dbxworkspace", self.config.lakebase_database_name, "--",
            "-d", self.config.lakebase_database_name,
            "-c", "SELECT current_database();"
        ], "Test Lakebase connection")
        
        if test_result["success"]:
            print(f"✅ Lakebase database '{self.config.lakebase_database_name}' is accessible")
            self.results["steps_completed"].append("connection_verified")
            return True
        else:
            print(f"❌ Cannot connect to Lakebase database '{self.config.lakebase_database_name}': {test_result['error']}")
            self.results["errors"].append(f"Lakebase connection failed: {test_result['error']}")
            return False
    
    def create_schema(self) -> bool:
        """Create the Lakebase schema"""
        print(f"🔄 Create Lakebase schema...")
        
        schema_result = self.run_cli_command([
            "databricks", "psql", "-p", "dbxworkspace", self.config.lakebase_database_name, "--",
            "-d", self.config.lakebase_database_name,
            "-c", f"CREATE SCHEMA IF NOT EXISTS {self.config.lakebase_schema};"
        ], "Create Lakebase schema")
        
        if schema_result["success"]:
            print(f"✅ Successfully created schema '{self.config.lakebase_schema}'")
            self.results["steps_completed"].append("schema_created")
            return True
        else:
            # Check if schema already exists
            if "already exists" in schema_result.get("error", "").lower():
                print(f"✅ Schema '{self.config.lakebase_schema}' already exists")
                self.results["steps_completed"].append("schema_exists")
                return True
            else:
                print(f"❌ Schema creation failed: {schema_result['error']}")
                self.results["errors"].append(f"Schema creation failed: {schema_result['error']}")
                return False
    
    def create_tables(self) -> bool:
        """Create all necessary tables in the Lakebase schema"""
        print(f"📋 Creating tables in Lakebase schema '{self.config.lakebase_schema}'...")
        
        # Define table creation SQL
        tables_sql = [
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.users (
                uid VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                display_name VARCHAR(255),
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.conversations (
                id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                title VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES {self.config.lakebase_schema}.users(uid)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.messages (
                id VARCHAR(255) PRIMARY KEY,
                conversation_id VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES {self.config.lakebase_schema}.conversations(id)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.user_sessions (
                id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                session_token VARCHAR(500) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES {self.config.lakebase_schema}.users(uid)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.conversation_analytics (
                id VARCHAR(255) PRIMARY KEY,
                conversation_id VARCHAR(255) NOT NULL,
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                avg_response_time FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES {self.config.lakebase_schema}.conversations(id)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.config.lakebase_schema}.system_config (
                key VARCHAR(255) PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        ]
        
        # Create tables
        success_count = 0
        for i, sql in enumerate(tables_sql, 1):
            result = self.run_cli_command([
                "databricks", "psql", "-p", "dbxworkspace", self.config.lakebase_database_name, "--",
                "-d", self.config.lakebase_database_name,
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
        print(f"🔍 Verifying tables in schema '{self.config.lakebase_schema}'...")
        
        # List tables in the schema
        verify_result = self.run_cli_command([
            "databricks", "psql", "-p", "dbxworkspace", self.config.lakebase_database_name, "--",
            "-d", self.config.lakebase_database_name,
            "-c", f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{self.config.lakebase_schema}';"
        ], "Verify tables exist")
        
        if verify_result["success"]:
            print(f"✅ Tables verification successful")
            print(f"📋 Tables in schema '{self.config.lakebase_schema}':")
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
        print(f"Lakebase Database: {self.config.lakebase_database_name}")
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
        
        # Step 2: Create schema
        print("\n📋 STEP 2: Creating Schema")
        print("-" * 40)
        if not self.create_schema():
            success = False
        
        # Step 3: Create tables
        print("\n📋 STEP 3: Creating Tables")
        print("-" * 40)
        if not self.create_tables():
            success = False
        
        # Step 4: Verify tables
        print("\n📋 STEP 4: Verifying Tables")
        print("-" * 40)
        if not self.verify_tables():
            success = False
        
        # Print results
        print("\n" + "=" * 60)
        print("📊 INITIALIZATION RESULTS")
        print("=" * 60)
        print(f"Environment: {self.config.name}")
        print(f"Base Name: {self.config.base_name}")
        print(f"Lakebase Database: {self.config.lakebase_database_name}")
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
