#!/usr/bin/env python3
"""
Complete Setup Check Script for base-chatbot
============================================

This script checks all components of the base-chatbot setup:
1. Databricks App
2. Unity Catalog (catalog, schema, volume)
3. Lakebase PostgreSQL (database, schema, tables)

Usage:
    python check_complete_setup.py [--environment ENV] [--verbose]

Examples:
    python check_complete_setup.py
    python check_complete_setup.py --environment staging --verbose
"""

import os
import sys
import argparse
import subprocess
import json
from typing import Dict, Any, List
from pathlib import Path
from databricks.vector_search.client import VectorSearchClient

# Add the project root to the path
sys.path.append(str(Path(__file__).parent.parent))

from config_manager import ConfigManager

class CompleteSetupChecker:
    def __init__(self, environment: str = "development", verbose: bool = False):
        self.environment = environment
        self.verbose = verbose
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_environment_config(environment)
        
        self.results = {
            "environment": environment,
            "base_name": self.config.base_name,
            "checks": [],
            "errors": [],
            "warnings": []
        }
    
    def run_cli_command(self, command: List[str], description: str) -> Dict[str, Any]:
        """Run a Databricks CLI command"""
        if self.verbose:
            print(f"🔄 {description}...")
        
        try:
            # Use the correct Databricks CLI version by setting PATH
            env = os.environ.copy()
            env["PATH"] = "/usr/local/bin:" + env.get("PATH", "")
            env["DATABRICKS_CLI_DO_NOT_EXECUTE_NEWER_VERSION"] = "1"
            
            # Add profile if not already specified
            if "-p" not in command and "--profile" not in command:
                # Find the position after 'databricks' command
                databricks_pos = command.index("databricks")
                command.insert(databricks_pos + 1, "-p")
                command.insert(databricks_pos + 2, self.config.databricks_profile)
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            
            if self.verbose:
                print(f"✅ {description} completed")
            
            return {
                "success": True,
                "output": result.stdout,
                "error": None
            }
        except subprocess.CalledProcessError as e:
            if self.verbose:
                print(f"❌ {description} failed: {e.stderr.strip()}")
            return {
                "success": False,
                "output": e.stdout,
                "error": e.stderr
            }
        except FileNotFoundError:
            if self.verbose:
                print(f"❌ {description} failed: Databricks CLI not found.")
            return {
                "success": False,
                "output": "",
                "error": "Databricks CLI not found."
            }
        except Exception as e:
            if self.verbose:
                print(f"❌ {description} failed: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
    
    def check_databricks_app(self) -> bool:
        """Check if the Databricks app exists"""
        print("🔍 Checking Databricks App...")
        
        result = self.run_cli_command([
            "databricks", "apps", "get", self.config.databricks_app_name
        ], "Check Databricks app exists")
        
        if result["success"]:
            self.results["checks"].append({
                "component": "databricks_app",
                "status": "pass",
                "message": f"App '{self.config.databricks_app_name}' exists"
            })
            print(f"✅ Databricks App '{self.config.databricks_app_name}' exists")
            return True
        else:
            self.results["errors"].append(f"Databricks App '{self.config.databricks_app_name}' not found")
            self.results["checks"].append({
                "component": "databricks_app",
                "status": "fail",
                "message": f"App '{self.config.databricks_app_name}' not found"
            })
            print(f"❌ Databricks App '{self.config.databricks_app_name}' not found")
            return False
    
    def check_unity_catalog(self) -> bool:
        """Check if the Unity Catalog exists"""
        print("🔍 Checking Unity Catalog...")
        
        result = self.run_cli_command([
            "databricks", "catalogs", "get", self.config.unity_catalog
        ], "Check Unity Catalog exists")
        
        if result["success"]:
            self.results["checks"].append({
                "component": "unity_catalog",
                "status": "pass",
                "message": f"Catalog '{self.config.unity_catalog}' exists"
            })
            print(f"✅ Unity Catalog '{self.config.unity_catalog}' exists")
            return True
        else:
            self.results["errors"].append(f"Unity Catalog '{self.config.unity_catalog}' not found")
            self.results["checks"].append({
                "component": "unity_catalog",
                "status": "fail",
                "message": f"Catalog '{self.config.unity_catalog}' not found"
            })
            print(f"❌ Unity Catalog '{self.config.unity_catalog}' not found")
            return False
    
    def check_unity_schema(self) -> bool:
        """Check if the Unity Catalog schema exists"""
        print("🔍 Checking Unity Catalog Schema...")
        
        result = self.run_cli_command([
            "databricks", "schemas", "get", 
            f"{self.config.unity_catalog}.{self.config.unity_catalog_schema}"
        ], "Check Unity Catalog schema exists")
        
        if result["success"]:
            self.results["checks"].append({
                "component": "unity_schema",
                "status": "pass",
                "message": f"Schema '{self.config.unity_catalog}.{self.config.unity_catalog_schema}' exists"
            })
            print(f"✅ Unity Catalog Schema '{self.config.unity_catalog}.{self.config.unity_catalog_schema}' exists")
            return True
        else:
            self.results["errors"].append(f"Unity Catalog Schema '{self.config.unity_catalog}.{self.config.unity_catalog_schema}' not found")
            self.results["checks"].append({
                "component": "unity_schema",
                "status": "fail",
                "message": f"Schema '{self.config.unity_catalog}.{self.config.unity_catalog_schema}' not found"
            })
            print(f"❌ Unity Catalog Schema '{self.config.unity_catalog}.{self.config.unity_catalog_schema}' not found")
            return False
    
    def check_unity_volume(self) -> bool:
        """Check if the Unity Catalog volume exists"""
        print("🔍 Checking Unity Catalog Volume...")
        
        result = self.run_cli_command([
            "databricks", "volumes", "read",
            f"{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}"
        ], "Check Unity Catalog volume exists")
        
        if result["success"]:
            self.results["checks"].append({
                "component": "unity_volume",
                "status": "pass",
                "message": f"Volume '{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}' exists"
            })
            print(f"✅ Unity Catalog Volume '{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}' exists")
            return True
        else:
            self.results["errors"].append(f"Unity Catalog Volume '{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}' not found")
            self.results["checks"].append({
                "component": "unity_volume",
                "status": "fail",
                "message": f"Volume '{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}' not found"
            })
            print(f"❌ Unity Catalog Volume '{self.config.unity_catalog}.{self.config.unity_catalog_schema}.{self.config.unity_catalog_volume}' not found")
            return False
    
    def check_lakebase_instance(self) -> bool:
        """Check if the Lakebase instance exists"""
        print("🔍 Checking Lakebase Instance...")
        
        result = self.run_cli_command([
            "databricks", "database", "get-database-instance", self.config.lakebase_database_name
        ], "Check Lakebase instance exists")
        
        if result["success"]:
            self.results["checks"].append({
                "component": "lakebase_instance",
                "status": "pass",
                "message": f"Lakebase instance '{self.config.base_name}' exists"
            })
            print(f"✅ Lakebase Instance '{self.config.base_name}' exists")
            return True
        else:
            self.results["errors"].append(f"Lakebase Instance '{self.config.base_name}' not found")
            self.results["checks"].append({
                "component": "lakebase_instance",
                "status": "fail",
                "message": f"Instance '{self.config.base_name}' not found"
            })
            print(f"❌ Lakebase Instance '{self.config.base_name}' not found")
            return False
    
    def check_lakebase_database(self) -> bool:
        """Check if the Lakebase database exists"""
        print("🔍 Checking Lakebase Database...")
        
        result = self.run_cli_command([
            "databricks", "psql", self.config.lakebase_database_name, "--", "-c",
            f"SELECT datname FROM pg_database WHERE datname = '{self.config.lakebase_database_name}'"
        ], "Check Lakebase database exists")
        
        if result["success"] and self.config.lakebase_database_name in result["output"]:
            self.results["checks"].append({
                "component": "lakebase_database",
                "status": "pass",
                "message": f"Database '{self.config.lakebase_database_name}' exists"
            })
            print(f"✅ Lakebase Database '{self.config.lakebase_database_name}' exists")
            return True
        else:
            self.results["errors"].append(f"Lakebase Database '{self.config.lakebase_database_name}' not found")
            self.results["checks"].append({
                "component": "lakebase_database",
                "status": "fail",
                "message": f"Database '{self.config.lakebase_database_name}' not found"
            })
            print(f"❌ Lakebase Database '{self.config.lakebase_database_name}' not found")
            return False
    
    def check_lakebase_schema(self) -> bool:
        """Check if the Lakebase schema exists"""
        print("🔍 Checking Lakebase Schema...")
        
        result = self.run_cli_command([
            "databricks", "psql", self.config.lakebase_database_name, "--", "-d", self.config.lakebase_database_name, "-c",
            f"SELECT schema_name FROM information_schema.schemata WHERE schema_name = '{self.config.lakebase_schema}'"
        ], "Check Lakebase schema exists")
        
        if result["success"] and self.config.lakebase_schema in result["output"]:
            self.results["checks"].append({
                "component": "lakebase_schema",
                "status": "pass",
                "message": f"Schema '{self.config.lakebase_schema}' exists"
            })
            print(f"✅ Lakebase Schema '{self.config.lakebase_schema}' exists")
            return True
        else:
            self.results["errors"].append(f"Lakebase Schema '{self.config.lakebase_schema}' not found")
            self.results["checks"].append({
                "component": "lakebase_schema",
                "status": "fail",
                "message": f"Schema '{self.config.lakebase_schema}' not found"
            })
            print(f"❌ Lakebase Schema '{self.config.lakebase_schema}' not found")
            return False
    
    def check_lakebase_tables(self) -> bool:
        """Check if the Lakebase tables exist"""
        print("🔍 Checking Lakebase Tables...")
        
        expected_tables = ['users', 'conversations', 'messages', 'user_sessions', 'conversation_analytics', 'system_config']
        
        result = self.run_cli_command([
            "databricks", "psql", self.config.lakebase_database_name, "--", "-d", self.config.lakebase_database_name, "-c",
            f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{self.config.lakebase_schema}' ORDER BY table_name"
        ], "Check Lakebase tables exist")
        
        if result["success"]:
            found_tables = []
            lines = result["output"].split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('(') and not line.startswith('rows') and 'table_name' not in line and '----' not in line:
                    found_tables.append(line)
            
            missing_tables = [table for table in expected_tables if table not in found_tables]
            
            if not missing_tables:
                self.results["checks"].append({
                    "component": "lakebase_tables",
                    "status": "pass",
                    "message": f"All {len(expected_tables)} required tables exist"
                })
                print(f"✅ All {len(expected_tables)} required tables exist")
                return True
            else:
                self.results["errors"].append(f"Missing tables: {', '.join(missing_tables)}")
                self.results["checks"].append({
                    "component": "lakebase_tables",
                    "status": "fail",
                    "message": f"Missing tables: {', '.join(missing_tables)}"
                })
                print(f"❌ Missing tables: {', '.join(missing_tables)}")
                return False
        else:
            self.results["errors"].append("Failed to check tables")
            self.results["checks"].append({
                "component": "lakebase_tables",
                "status": "fail",
                "message": "Failed to check tables"
            })
            print("❌ Failed to check tables")
            return False
    
    def check_vector_search_database(self) -> bool:
        """Check if the vector search database exists using Python SDK"""
        print("🔍 Checking Vector Search Database...")
        
        try:
            # Initialize Vector Search client
            vs_client = VectorSearchClient(
                workspace_url=self.config.databricks_host,
                personal_access_token=self.config.databricks_token
            )
            
            # List endpoints using Python SDK
            endpoints = vs_client.list_endpoints()
            
            # Handle different response formats
            if isinstance(endpoints, str):
                # If it's a string, try to parse it as JSON
                try:
                    import json
                    endpoints = json.loads(endpoints)
                except json.JSONDecodeError:
                    self.results["errors"].append(f"Failed to parse vector search endpoints response: {endpoints}")
                    self.results["checks"].append({
                        "component": "vector_search_database",
                        "status": "fail",
                        "message": f"Failed to parse vector search endpoints response"
                    })
                    print(f"❌ Failed to parse vector search endpoints response")
                    return False
            
            # Handle different response formats
            if isinstance(endpoints, dict):
                # If it's a dictionary, look for endpoints in common keys
                if "endpoints" in endpoints:
                    endpoints = endpoints["endpoints"]
                elif "data" in endpoints:
                    endpoints = endpoints["data"]
                else:
                    # If it's a single endpoint dict, wrap it in a list
                    endpoints = [endpoints]
            elif not isinstance(endpoints, list):
                self.results["errors"].append(f"Unexpected vector search endpoints format: {type(endpoints)}")
                self.results["checks"].append({
                    "component": "vector_search_database",
                    "status": "fail",
                    "message": f"Unexpected vector search endpoints format"
                })
                print(f"❌ Unexpected vector search endpoints format: {type(endpoints)}")
                return False
            
            # Look for the specific endpoint
            existing_endpoints = []
            for ep in endpoints:
                if isinstance(ep, dict) and ep.get("name") == self.config.vector_search_database_name:
                    existing_endpoints.append(ep)
                elif isinstance(ep, str) and ep == self.config.vector_search_database_name:
                    # Handle case where endpoint is just a string name
                    existing_endpoints.append({"name": ep, "endpoint_status": "unknown"})
            
            if existing_endpoints:
                endpoint = existing_endpoints[0]
                status = endpoint.get('endpoint_status', 'unknown') if isinstance(endpoint, dict) else 'unknown'
                self.results["checks"].append({
                    "component": "vector_search_database",
                    "status": "pass",
                    "message": f"Vector search database '{self.config.vector_search_database_name}' exists (status: {status})"
                })
                print(f"✅ Vector search database '{self.config.vector_search_database_name}' exists")
                return True
            else:
                self.results["errors"].append(f"Vector search database '{self.config.vector_search_database_name}' not found")
                self.results["checks"].append({
                    "component": "vector_search_database",
                    "status": "fail",
                    "message": f"Vector search database '{self.config.vector_search_database_name}' not found"
                })
                print(f"❌ Vector search database '{self.config.vector_search_database_name}' not found")
                return False
                
        except Exception as e:
            self.results["errors"].append(f"Failed to check vector search endpoints: {e}")
            self.results["checks"].append({
                "component": "vector_search_database",
                "status": "fail",
                "message": f"Failed to check vector search endpoints: {e}"
            })
            print(f"❌ Failed to check vector search endpoints: {e}")
            return False
    
    def print_configuration(self):
        """Print the configuration being checked"""
        print(f"🔍 Checking complete setup for '{self.config.base_name}'")
        print(f"Environment: {self.environment}")
        print("=" * 60)
        print("📋 Configuration being checked:")
        print(f"  • Databricks App: {self.config.databricks_app_name}")
        print(f"  • Unity Catalog: {self.config.unity_catalog}")
        print(f"  • Unity Schema: {self.config.unity_catalog_schema}")
        print(f"  • Unity Volume: {self.config.unity_catalog_volume}")
        print(f"  • Warehouse: {self.config.warehouse_name}")
        print(f"  • Vector Search Database: {self.config.vector_search_database_name}")
        print(f"  • Lakebase Instance: {self.config.lakebase_database_name}")
        print(f"  • Lakebase Database: {self.config.lakebase_database_name}")
        print(f"  • Lakebase Schema: {self.config.lakebase_schema}")
        print("=" * 60)
    
    def run_all_checks(self):
        """Run all checks"""
        self.print_configuration()
        
        # Run all checks
        self.check_databricks_app()
        self.check_unity_catalog()
        self.check_unity_schema()
        self.check_unity_volume()
        self.check_lakebase_instance()
        self.check_lakebase_database()
        self.check_lakebase_schema()
        self.check_lakebase_tables()
        self.check_vector_search_database()
    
    def print_report(self):
        """Print the comprehensive report"""
        print("\n" + "=" * 60)
        print("📊 COMPLETE SETUP CHECK REPORT")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Base Name: {self.config.base_name}")
        print()
        
        # Count results
        passed_checks = len([c for c in self.results["checks"] if c["status"] == "pass"])
        failed_checks = len([c for c in self.results["checks"] if c["status"] == "fail"])
        
        print(f"Checks: {passed_checks} passed, {failed_checks} failed")
        print()
        
        # Detailed checks
        print("📋 Detailed Checks:")
        for check in self.results["checks"]:
            status_icon = "✅" if check["status"] == "pass" else "❌"
            print(f"  {status_icon} {check['component']}: {check['message']}")
        
        # Errors
        if self.results["errors"]:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for error in self.results["errors"]:
                print(f"  - {error}")
        
        # Warnings
        if self.results["warnings"]:
            print(f"\n⚠️ Warnings ({len(self.results['warnings'])}):")
            for warning in self.results["warnings"]:
                print(f"  - {warning}")
        
        print("\n" + "=" * 60)
        
        # Overall status
        if self.results["errors"]:
            print("❌ Some checks failed")
            return False
        else:
            print("🎉 All checks passed!")
            return True

def main():
    parser = argparse.ArgumentParser(description="Check complete setup for base-chatbot")
    parser.add_argument("--environment", default="development", help="Environment name")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    
    args = parser.parse_args()
    
    checker = CompleteSetupChecker(
        environment=args.environment,
        verbose=args.verbose
    )
    
    checker.run_all_checks()
    success = checker.print_report()
    
    if success:
        print("🎉 Complete setup verification successful!")
        sys.exit(0)
    else:
        print("❌ Complete setup verification failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
