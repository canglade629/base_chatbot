#!/usr/bin/env python3
"""
Complete Setup Script for base-chatbot
=====================================

This script provides a complete setup for the base-chatbot project:
1. Configuration management
2. Databricks App creation
3. Unity Catalog setup
4. Lakebase setup
5. Validation

Usage:
    python setup.py [--environment ENV] [--dry-run] [--skip-steps STEPS]

Examples:
    python setup.py
    python setup.py --environment staging --dry-run
    python setup.py --skip-steps lakebase,validation
"""

import os
import sys
import json
import argparse
import subprocess
import requests
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from databricks.vector_search.client import VectorSearchClient

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
    """Manages environment-specific configurations"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent
        self.environments_file = self.config_dir / "environments.json"
    
    def load_environment_config(self, environment: str) -> EnvironmentConfig:
        """Load configuration for a specific environment"""
        if not self.environments_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.environments_file}")
        
        with open(self.environments_file, 'r') as f:
            configs = json.load(f)
        
        if environment not in configs:
            raise ValueError(f"Environment '{environment}' not found in configuration")
        
        config_data = configs[environment]
        return EnvironmentConfig(**config_data)

class CompleteSetup:
    def __init__(self, environment: str = "development", dry_run: bool = False, skip_steps: list = None):
        self.environment = environment
        self.dry_run = dry_run
        self.skip_steps = skip_steps or []
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_environment_config(environment)
        
        self.results = {
            "environment": environment,
            "base_name": self.config.base_name,
            "dry_run": dry_run,
            "steps_completed": [],
            "steps_skipped": [],
            "errors": []
        }
    
    def run_cli_command(self, command: List[str], description: str) -> Dict[str, Any]:
        """Run a CLI command and return the result"""
        print(f"🔄 {description}...")
        
        if self.dry_run:
            print(f"🔍 DRY RUN: Would run: {' '.join(command)}")
            return {"success": True, "output": "DRY RUN", "error": None}
        
        try:
            # Use the correct Databricks CLI version by setting PATH
            env = os.environ.copy()
            env["PATH"] = "/usr/local/bin:" + env.get("PATH", "")
            env["DATABRICKS_CLI_DO_NOT_EXECUTE_NEWER_VERSION"] = "1"
            
            # Add profile if not already specified
            if "-p" not in command and "--profile" not in command:
                databricks_pos = command.index("databricks")
                command.insert(databricks_pos + 1, "-p")
                command.insert(databricks_pos + 2, self.config.databricks_profile)
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=env,
                timeout=300
            )
            
            if result.returncode == 0:
                return {"success": True, "output": result.stdout, "error": None}
            else:
                return {"success": False, "output": result.stdout, "error": result.stderr}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "error": "Command timed out"}
        except FileNotFoundError:
            return {"success": False, "output": "", "error": "Command not found"}
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}
    
    def get_or_create_serverless_warehouse(self) -> str:
        """Get or create the configured warehouse"""
        warehouse_name = self.config.warehouse_name
        print(f"🔍 Looking for warehouse '{warehouse_name}'...")
        
        # List existing warehouses
        result = self.run_cli_command([
            "databricks", "warehouses", "list", "-o", "json"
        ], "List SQL warehouses")
        
        if result["success"]:
            try:
                warehouses = json.loads(result["output"])
                for warehouse in warehouses:
                    if warehouse.get("name") == warehouse_name:
                        print(f"✅ Found existing warehouse '{warehouse_name}': {warehouse['id']}")
                        return warehouse["id"]
            except json.JSONDecodeError:
                pass
        
        # Create the warehouse if not found
        print(f"🔄 Creating warehouse '{warehouse_name}'...")
        create_result = self.run_cli_command([
            "databricks", "warehouses", "create",
            "--name", warehouse_name,
            "--cluster-size", "Small",
            "--max-num-clusters", "1",
            "--min-num-clusters", "1",
            "--enable-photon",
            "--enable-serverless-compute",
            "--warehouse-type", "PRO",
            "--auto-stop-mins", "10",
            "--no-wait"
        ], f"Create warehouse '{warehouse_name}'")
        
        if create_result["success"]:
            # Extract warehouse ID from the output
            output = create_result["output"]
            # The output should contain the warehouse ID
            import re
            match = re.search(r'"id":\s*"([^"]+)"', output)
            if match:
                warehouse_id = match.group(1)
                print(f"✅ Created warehouse '{warehouse_name}': {warehouse_id}")
                return warehouse_id
        
        print(f"❌ Failed to create warehouse '{warehouse_name}'")
        return None
    
    def create_catalog_via_warehouse(self, warehouse_id: str) -> bool:
        """Create Unity Catalog using SQL execution via warehouse"""
        print(f"📊 Creating catalog using warehouse {warehouse_id}...")
        
        # Use the SQL execution API via REST
        import requests
        
        sql_url = f"{self.config.databricks_host}/api/2.0/sql/statements"
        headers = {
            "Authorization": f"Bearer {self.config.databricks_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "warehouse_id": warehouse_id,
            "statement": f"CREATE CATALOG IF NOT EXISTS {self.config.unity_catalog}",
            "wait_timeout": "30s"
        }
        
        try:
            response = requests.post(sql_url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                if result.get('status', {}).get('state') == 'SUCCEEDED':
                    return True
                else:
                    print(f"❌ SQL execution failed: {result.get('error', 'Unknown error')}")
                    return False
            else:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error executing SQL: {e}")
            return False
    
    def setup_databricks_app(self) -> bool:
        """Create Databricks app if it doesn't exist"""
        if "app" in self.skip_steps:
            self.results["steps_skipped"].append("app")
            return True
        
        print(f"🚀 Setting up Databricks App: {self.config.databricks_app_name}")
        
        # Check if app exists
        check_result = self.run_cli_command([
            "databricks", "apps", "get", self.config.databricks_app_name
        ], "Check if app exists")
        
        if check_result["success"]:
            print(f"✅ App '{self.config.databricks_app_name}' already exists")
            self.results["steps_completed"].append("app_exists")
            return True
        
        # Create app
        create_result = self.run_cli_command([
            "databricks", "apps", "create",
            self.config.databricks_app_name,
            "--description", f"App for {self.config.databricks_app_name}",
            "--no-wait"
        ], "Create Databricks app")
        
        if create_result["success"]:
            print(f"✅ Successfully created app '{self.config.databricks_app_name}'")
            self.results["steps_completed"].append("app_created")
            return True
        else:
            print(f"❌ Failed to create app: {create_result['error']}")
            self.results["errors"].append(f"App creation failed: {create_result['error']}")
            return False
    
    def setup_unity_catalog(self) -> bool:
        """Create Unity Catalog if it doesn't exist"""
        if "catalog" in self.skip_steps:
            self.results["steps_skipped"].append("catalog")
            return True
        
        print(f"🚀 Setting up Unity Catalog: {self.config.unity_catalog}")
        
        # Check if catalog exists
        check_result = self.run_cli_command([
            "databricks", "catalogs", "get", self.config.unity_catalog
        ], "Check if catalog exists")
        
        if check_result["success"]:
            print(f"✅ Catalog '{self.config.unity_catalog}' already exists")
            self.results["steps_completed"].append("catalog_exists")
        else:
            # Catalog doesn't exist - create it using SQL warehouse
            print(f"⚠️ Catalog '{self.config.unity_catalog}' not found. Creating...")
            
            # Get or create "Serverless Starter Warehouse"
            warehouse_id = self.get_or_create_serverless_warehouse()
            if not warehouse_id:
                print("❌ Failed to get or create Serverless Starter Warehouse")
                self.results["errors"].append("Failed to get or create Serverless Starter Warehouse")
                return False
            
            # Create catalog using SQL execution via warehouse
            catalog_created = self.create_catalog_via_warehouse(warehouse_id)
            if catalog_created:
                print(f"✅ Successfully created catalog '{self.config.unity_catalog}'")
                self.results["steps_completed"].append("catalog_created")
            else:
                print(f"❌ Failed to create catalog '{self.config.unity_catalog}'")
                self.results["errors"].append("Failed to create Unity Catalog")
                return False
        
        # Create schema
        schema_result = self.run_cli_command([
            "databricks", "schemas", "create",
            self.config.unity_catalog_schema,
            self.config.unity_catalog
        ], "Create Unity Catalog schema")
        
        if schema_result["success"]:
            print(f"✅ Successfully created schema '{self.config.unity_catalog_schema}'")
            self.results["steps_completed"].append("schema_created")
        else:
            # Check if schema already exists
            if "already exists" in schema_result.get("error", "").lower():
                print(f"✅ Schema '{self.config.unity_catalog_schema}' already exists")
                self.results["steps_completed"].append("schema_exists")
            else:
                print(f"❌ Schema creation failed: {schema_result['error']}")
                self.results["errors"].append(f"Schema creation failed: {schema_result['error']}")
                return False
        
        # Create volume
        volume_result = self.run_cli_command([
            "databricks", "volumes", "create",
            self.config.unity_catalog,
            self.config.unity_catalog_schema,
            self.config.unity_catalog_volume,
            "MANAGED"
        ], "Create Unity Catalog volume")
        
        if volume_result["success"]:
            print(f"✅ Successfully created volume '{self.config.unity_catalog_volume}'")
            self.results["steps_completed"].append("volume_created")
        else:
            # Check if volume already exists
            if "already exists" in volume_result.get("error", "").lower():
                print(f"✅ Volume '{self.config.unity_catalog_volume}' already exists")
                self.results["steps_completed"].append("volume_exists")
            else:
                print(f"❌ Volume creation failed: {volume_result['error']}")
                self.results["errors"].append(f"Volume creation failed: {volume_result['error']}")
                return False
        
        return True
    
    def setup_lakebase(self) -> bool:
        """Create Lakebase instance and database"""
        if "lakebase" in self.skip_steps:
            self.results["steps_skipped"].append("lakebase")
            return True
        
        print(f"🚀 Setting up Lakebase: {self.config.base_name}")
        
        # Check if instance exists
        check_result = self.run_cli_command([
            "databricks", "database", "list-database-instances", "-o", "json"
        ], "Check if Lakebase instance exists")
        
        if not check_result["success"]:
            print(f"❌ Failed to check instances: {check_result['error']}")
            self.results["errors"].append(f"Instance check failed: {check_result['error']}")
            return False
        
        try:
            instances = json.loads(check_result["output"])
            instance_exists = any(inst["name"] == self.config.lakebase_database_name for inst in instances)
        except json.JSONDecodeError:
            print("❌ Failed to parse instances list")
            self.results["errors"].append("Failed to parse instances list")
            return False
        
        if not instance_exists:
            # Create instance
            create_result = self.run_cli_command([
                "databricks", "database", "create-database-instance",
                self.config.lakebase_database_name,
                "--capacity", "CU_1",
                "--no-wait"
            ], "Create Lakebase instance")
            
            if not create_result["success"]:
                print(f"❌ Failed to create instance: {create_result['error']}")
                self.results["errors"].append(f"Instance creation failed: {create_result['error']}")
                return False
            
            print(f"✅ Successfully created instance '{self.config.lakebase_database_name}'")
            self.results["steps_completed"].append("instance_created")
        else:
            print(f"✅ Instance '{self.config.lakebase_database_name}' already exists")
            self.results["steps_completed"].append("instance_exists")
        
        # Create database
        db_result = self.run_cli_command([
            "databricks", "database", "create-database-catalog",
            self.config.lakebase_database_name,
            self.config.base_name,
            self.config.lakebase_database_name,
            "--create-database-if-not-exists",
            "--no-wait"
        ], "Create Lakebase database")
        
        if db_result["success"]:
            print(f"✅ Successfully created database '{self.config.lakebase_database_name}'")
            self.results["steps_completed"].append("database_created")
        else:
            print(f"⚠️ Database creation failed or already exists: {db_result['error']}")
            self.results["steps_completed"].append("database_exists")
        
        return True
    
    def setup_lakebase_instance_only(self) -> bool:
        """Create Lakebase database instance only (without schema/tables)"""
        print(f"🗄️ Setting up Lakebase database instance '{self.config.lakebase_database_name}'...")
        
        # Check if Lakebase instance already exists
        list_result = self.run_cli_command([
            "databricks", "database", "list-database-instances", "-o", "json"
        ], "List Lakebase instances")
        
        if list_result["success"]:
            try:
                instances = json.loads(list_result["output"])
                # Handle both list and dict responses
                if isinstance(instances, list):
                    instance_list = instances
                else:
                    instance_list = instances.get("database_instances", [])
                
                existing_instances = [inst for inst in instance_list 
                                    if inst.get("name") == self.config.lakebase_database_name]
                if existing_instances:
                    print(f"✅ Lakebase database '{self.config.lakebase_database_name}' already exists")
                    self.results["steps_completed"].append("lakebase_database")
                    return True
            except json.JSONDecodeError:
                pass
        
        # Create Lakebase instance
        create_result = self.run_cli_command([
            "databricks", "database", "create-database-instance",
            self.config.lakebase_database_name,
            "--capacity", "CU_1",
            "--no-wait"
        ], f"Create Lakebase database '{self.config.lakebase_database_name}'")
        
        if create_result["success"]:
            print(f"✅ Lakebase database '{self.config.lakebase_database_name}' created successfully")
            self.results["steps_completed"].append("lakebase_database")
            return True
        else:
            print(f"❌ Lakebase database creation failed: {create_result['error']}")
            self.results["errors"].append(f"Lakebase database creation failed: {create_result['error']}")
            return False
    
    
    def setup_vector_search_database(self) -> bool:
        """Create vector search database using Python SDK"""
        print(f"🔍 Setting up vector search database '{self.config.vector_search_database_name}'...")
        
        try:
            # Initialize Vector Search client
            vs_client = VectorSearchClient(
                workspace_url=self.config.databricks_host,
                personal_access_token=self.config.databricks_token
            )
            
            # Check if vector search database already exists
            try:
                existing_endpoints = vs_client.list_endpoints()
                endpoint_exists = any(ep.get("name") == self.config.vector_search_database_name 
                                   for ep in existing_endpoints)
                
                if endpoint_exists:
                    print(f"✅ Vector search database '{self.config.vector_search_database_name}' already exists")
                    self.results["steps_completed"].append("vector_search_database")
                    return True
            except Exception as e:
                print(f"⚠️ Could not check existing endpoints: {e}")
                # Continue with creation attempt
            
            # Create vector search database using Python SDK
            if self.dry_run:
                print(f"🔍 [DRY RUN] Would create vector search database '{self.config.vector_search_database_name}'")
                self.results["steps_completed"].append("vector_search_database")
                return True
            
            vs_client.create_endpoint(
                name=self.config.vector_search_database_name,
                endpoint_type="STANDARD"
            )
            
            print(f"✅ Vector search database '{self.config.vector_search_database_name}' created successfully")
            self.results["steps_completed"].append("vector_search_database")
            return True
            
        except Exception as e:
            # Check if the error is "ALREADY_EXISTS" - this is not an error
            error_str = str(e)
            if "ALREADY_EXISTS" in error_str or "already exists" in error_str.lower():
                print(f"✅ Vector search database '{self.config.vector_search_database_name}' already exists")
                self.results["steps_completed"].append("vector_search_database")
                return True
            else:
                print(f"❌ Vector search database creation failed: {e}")
                self.results["errors"].append(f"Vector search database creation failed: {e}")
                return False
    
    def check_and_extract_config(self) -> bool:
        """Check all resources and extract configuration (IDs, endpoints, etc.)"""
        print("🔍 Checking resources and extracting configuration...")
        
        config_data = {
            "databricks_app": {},
            "unity_catalog": {},
            "warehouse": {},
            "vector_search": {},
            "lakebase": {}
        }
        
        # Check Databricks App
        app_result = self.run_cli_command([
            "databricks", "apps", "list", "-o", "json"
        ], "List Databricks apps")
        
        if app_result["success"]:
            try:
                apps = json.loads(app_result["output"])
                # Handle both list and dict responses
                if isinstance(apps, list):
                    app_list = apps
                else:
                    app_list = apps.get("apps", [])
                
                matching_apps = [app for app in app_list 
                               if app.get("name") == self.config.databricks_app_name]
                if matching_apps:
                    config_data["databricks_app"] = matching_apps[0]
                    print(f"✅ Found Databricks app: {matching_apps[0].get('id', 'unknown')}")
            except json.JSONDecodeError:
                pass
        
        # Check Unity Catalog
        catalog_result = self.run_cli_command([
            "databricks", "catalogs", "list", "-o", "json"
        ], "List Unity catalogs")
        
        if catalog_result["success"]:
            try:
                catalogs = json.loads(catalog_result["output"])
                # Handle both list and dict responses
                if isinstance(catalogs, list):
                    catalog_list = catalogs
                else:
                    catalog_list = catalogs.get("catalogs", [])
                
                matching_catalogs = [cat for cat in catalog_list 
                                   if cat.get("name") == self.config.unity_catalog]
                if matching_catalogs:
                    config_data["unity_catalog"] = matching_catalogs[0]
                    print(f"✅ Found Unity catalog: {matching_catalogs[0].get('name', 'unknown')}")
            except json.JSONDecodeError:
                pass
        
        # Check Warehouse
        warehouse_result = self.run_cli_command([
            "databricks", "warehouses", "list", "-o", "json"
        ], "List warehouses")
        
        if warehouse_result["success"]:
            try:
                warehouses = json.loads(warehouse_result["output"])
                # Handle both list and dict responses
                if isinstance(warehouses, list):
                    warehouse_list = warehouses
                else:
                    warehouse_list = warehouses.get("warehouses", [])
                
                matching_warehouses = [wh for wh in warehouse_list 
                                     if wh.get("name") == self.config.warehouse_name]
                if matching_warehouses:
                    config_data["warehouse"] = matching_warehouses[0]
                    print(f"✅ Found warehouse: {matching_warehouses[0].get('id', 'unknown')}")
            except json.JSONDecodeError:
                pass
        
        # Check Vector Search Database using Python SDK
        try:
            vs_client = VectorSearchClient(
                workspace_url=self.config.databricks_host,
                personal_access_token=self.config.databricks_token
            )
            endpoints = vs_client.list_endpoints()
            matching_endpoints = [ep for ep in endpoints 
                                if ep.get("name") == self.config.vector_search_database_name]
            if matching_endpoints:
                config_data["vector_search"] = matching_endpoints[0]
                print(f"✅ Found vector search database: {matching_endpoints[0].get('id', 'unknown')}")
        except Exception as e:
            print(f"⚠️ Could not check vector search endpoints: {e}")
        
        # Check Lakebase Instance
        lakebase_result = self.run_cli_command([
            "databricks", "database", "list-database-instances", "-o", "json"
        ], "List Lakebase instances")
        
        if lakebase_result["success"]:
            try:
                instances = json.loads(lakebase_result["output"])
                # Handle both list and dict responses
                if isinstance(instances, list):
                    instance_list = instances
                else:
                    instance_list = instances.get("database_instances", [])
                
                matching_instances = [inst for inst in instance_list 
                                    if inst.get("name") == self.config.lakebase_database_name]
                if matching_instances:
                    config_data["lakebase"] = matching_instances[0]
                    print(f"✅ Found Lakebase instance: {matching_instances[0].get('id', 'unknown')}")
            except json.JSONDecodeError:
                pass
        
        # Save configuration to file
        config_file = Path(__file__).parent / f"{self.environment}_config.json"
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"💾 Configuration saved to {config_file}")
        self.results["steps_completed"].append("config_extraction")
        return True
    
    def run_setup(self, step: str = "all") -> bool:
        """Run the setup process
        
        Args:
            step: "resources" (step 1), "schema" (step 2), or "all" (both steps)
        """
        print(f"🚀 Starting setup for '{self.config.base_name}'")
        print(f"Environment: {self.environment}")
        print(f"Step: {step}")
        print(f"Dry Run: {self.dry_run}")
        print("=" * 60)
        
        success = True
        
        if step in ["resources", "all"]:
            print("\n📦 STEP 1: Creating Resources")
            print("-" * 40)
        
        # Step 1: Databricks App
        if not self.setup_databricks_app():
            success = False
        
        # Step 2: Unity Catalog
        if not self.setup_unity_catalog():
            success = False
        
        # Step 3: Vector Search Database
        if not self.setup_vector_search_database():
            success = False
        
        # Step 4: Lakebase Instance (without schema/tables)
        if not self.setup_lakebase_instance_only():
            success = False
        
        if step in ["schema", "all"]:
            print("\n📋 STEP 2: Configuration Extraction")
            print("-" * 40)
            
            # Step 5: Check all resources and extract configuration
            if not self.check_and_extract_config():
                success = False
        
        # Print results
        self.print_results()
        
        return success
    
    def print_results(self):
        """Print setup results"""
        print("\n" + "=" * 60)
        print("📊 SETUP RESULTS")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Base Name: {self.config.base_name}")
        print(f"Dry Run: {self.dry_run}")
        
        if self.results["steps_completed"]:
            print(f"\n✅ Completed Steps ({len(self.results['steps_completed'])}):")
            for step in self.results["steps_completed"]:
                print(f"  • {step}")
        
        if self.results["steps_skipped"]:
            print(f"\n⏭️ Skipped Steps ({len(self.results['steps_skipped'])}):")
            for step in self.results["steps_skipped"]:
                print(f"  • {step}")
        
        if self.results["errors"]:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for error in self.results["errors"]:
                print(f"  • {error}")
        
        print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Complete setup for base-chatbot")
    parser.add_argument("--environment", "-e", default="development", 
                       choices=["development", "staging", "production"],
                       help="Environment to setup")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be done without making changes")
    parser.add_argument("--step", choices=["resources", "schema", "all"], 
                       default="all", help="Setup step to run")
    parser.add_argument("--skip-steps", "-s", 
                       help="Comma-separated list of steps to skip (app,catalog,lakebase)")
    
    args = parser.parse_args()
    
    skip_steps = []
    if args.skip_steps:
        skip_steps = [step.strip() for step in args.skip_steps.split(",")]
    
    setup = CompleteSetup(
        environment=args.environment,
        dry_run=args.dry_run,
        skip_steps=skip_steps
    )
    
    success = setup.run_setup(step=args.step)
    
    if success:
        print("🎉 Setup completed successfully!")
        sys.exit(0)
    else:
        print("❌ Setup completed with errors!")
        sys.exit(1)

if __name__ == "__main__":
    main()
