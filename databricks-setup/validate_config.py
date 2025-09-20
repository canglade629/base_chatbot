#!/usr/bin/env python3
"""
Configuration Validation Script
==============================

Validates the current configuration and environment setup.
Checks all required settings and provides detailed feedback.

Usage:
    python config/validate_config.py [--environment ENV] [--verbose]

Examples:
    python config/validate_config.py
    python config/validate_config.py --environment staging --verbose
"""

import argparse
import sys
import os
from pathlib import Path

# Add the current directory to the path
sys.path.append(str(Path(__file__).parent))

from config_manager import ConfigManager, EnvironmentConfig

class ConfigurationValidator:
    def __init__(self, environment: str = "development", verbose: bool = False):
        self.environment = environment
        self.verbose = verbose
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_environment_config(environment)
        self.validation_results = {
            "environment": environment,
            "base_name": self.config.base_name,
            "overall_status": "PASS",
            "checks": [],
            "warnings": [],
            "errors": []
        }
    
    def check_required_fields(self):
        """Check that all required fields are present"""
        print("🔍 Checking required fields...")
        
        required_fields = [
            ("base_name", self.config.base_name, "Base name for resource naming"),
            ("databricks_host", self.config.databricks_host, "Databricks workspace host"),
            ("databricks_token", self.config.databricks_token, "Databricks authentication token"),
            ("unity_catalog", self.config.unity_catalog, "Unity catalog name"),
            ("lakebase_schema", self.config.lakebase_schema, "Lakebase schema name"),
            ("lakebase_database_name", self.config.lakebase_database_name, "Lakebase database name")
        ]
        
        for field_name, field_value, description in required_fields:
            if field_value:
                self.validation_results["checks"].append({
                    "check": f"Required field: {field_name}",
                    "status": "PASS",
                    "message": f"{description} is set"
                })
                if self.verbose:
                    print(f"  ✅ {field_name}: {field_value}")
            else:
                self.validation_results["checks"].append({
                    "check": f"Required field: {field_name}",
                    "status": "FAIL",
                    "message": f"{description} is missing"
                })
                self.validation_results["errors"].append(f"Missing required field: {field_name}")
                print(f"  ❌ {field_name}: Missing")
    
    def check_base_name_format(self):
        """Check that base name follows naming conventions"""
        print("🔍 Checking base name format...")
        
        base_name = self.config.base_name
        if not base_name:
            self.validation_results["errors"].append("Base name is empty")
            return
        
        # Check for valid characters (letters, numbers, hyphens, underscores)
        if not base_name.replace('-', '').replace('_', '').isalnum():
            self.validation_results["errors"].append("Base name contains invalid characters")
            self.validation_results["checks"].append({
                "check": "Base name format",
                "status": "FAIL",
                "message": "Base name should only contain letters, numbers, hyphens, and underscores"
            })
            print(f"  ❌ Base name format: '{base_name}' contains invalid characters")
        else:
            self.validation_results["checks"].append({
                "check": "Base name format",
                "status": "PASS",
                "message": f"Base name '{base_name}' follows naming conventions"
            })
            print(f"  ✅ Base name format: '{base_name}' is valid")
    
    def check_databricks_config(self):
        """Check Databricks configuration"""
        print("🔍 Checking Databricks configuration...")
        
        # Check host format
        if self.config.databricks_host:
            if self.config.databricks_host.startswith('https://'):
                self.validation_results["checks"].append({
                    "check": "Databricks host format",
                    "status": "PASS",
                    "message": "Host URL starts with https://"
                })
                if self.verbose:
                    print(f"  ✅ Databricks host: {self.config.databricks_host}")
            else:
                self.validation_results["warnings"].append("Databricks host should start with https://")
                self.validation_results["checks"].append({
                    "check": "Databricks host format",
                    "status": "WARN",
                    "message": "Host URL should start with https://"
                })
                print(f"  ⚠️ Databricks host format: Should start with https://")
        
        # Check token format
        if self.config.databricks_token:
            if self.config.databricks_token.startswith('dapi'):
                self.validation_results["checks"].append({
                    "check": "Databricks token format",
                    "status": "PASS",
                    "message": "Token appears to be a valid Databricks token"
                })
                if self.verbose:
                    print(f"  ✅ Databricks token: {self.config.databricks_token[:10]}...")
            else:
                self.validation_results["warnings"].append("Databricks token doesn't start with 'dapi'")
                self.validation_results["checks"].append({
                    "check": "Databricks token format",
                    "status": "WARN",
                    "message": "Token doesn't appear to be a standard Databricks token"
                })
                print(f"  ⚠️ Databricks token format: Doesn't start with 'dapi'")
    
    def check_naming_consistency(self):
        """Check that naming is consistent across resources"""
        print("🔍 Checking naming consistency...")
        
        base_name = self.config.base_name
        catalog = self.config.unity_catalog
        schema = self.config.lakebase_schema
        database = self.config.lakebase_database_name
        
        # Check if all names are derived from base_name
        expected_catalog = base_name.replace('-', '_')
        expected_schema = base_name.replace('-', '_')
        expected_database = base_name
        
        naming_checks = [
            ("catalog", catalog, expected_catalog),
            ("schema", schema, expected_schema),
            ("database", database, expected_database)
        ]
        
        for resource_type, actual, expected in naming_checks:
            if actual == expected:
                self.validation_results["checks"].append({
                    "check": f"Naming consistency: {resource_type}",
                    "status": "PASS",
                    "message": f"{resource_type} name '{actual}' matches expected pattern"
                })
                if self.verbose:
                    print(f"  ✅ {resource_type.title()}: '{actual}' (consistent)")
            else:
                self.validation_results["warnings"].append(f"{resource_type.title()} name doesn't follow base name pattern")
                self.validation_results["checks"].append({
                    "check": f"Naming consistency: {resource_type}",
                    "status": "WARN",
                    "message": f"{resource_type} name '{actual}' doesn't match expected '{expected}'"
                })
                print(f"  ⚠️ {resource_type.title()}: '{actual}' (expected: '{expected}')")
    
    def check_environment_files(self):
        """Check if environment files exist and are properly configured"""
        print("🔍 Checking environment files...")
        
        # Check for .env file
        env_file = ".env"
        if os.path.exists(env_file):
            self.validation_results["checks"].append({
                "check": "Environment file",
                "status": "PASS",
                "message": f"Found {env_file} file"
            })
            print(f"  ✅ Environment file: {env_file} exists")
        else:
            self.validation_results["warnings"].append("No .env file found")
            self.validation_results["checks"].append({
                "check": "Environment file",
                "status": "WARN",
                "message": f"No {env_file} file found"
            })
            print(f"  ⚠️ Environment file: {env_file} not found")
        
        # Check for environment-specific .env file
        env_specific_file = f".env.{self.environment}"
        if self.environment != "development" and os.path.exists(env_specific_file):
            self.validation_results["checks"].append({
                "check": "Environment-specific file",
                "status": "PASS",
                "message": f"Found {env_specific_file} file"
            })
            print(f"  ✅ Environment-specific file: {env_specific_file} exists")
        elif self.environment != "development":
            self.validation_results["warnings"].append(f"No environment-specific file found for {self.environment}")
            self.validation_results["checks"].append({
                "check": "Environment-specific file",
                "status": "WARN",
                "message": f"No {env_specific_file} file found"
            })
            print(f"  ⚠️ Environment-specific file: {env_specific_file} not found")
    
    def check_databricks_cli(self):
        """Check if Databricks CLI is available and configured"""
        print("🔍 Checking Databricks CLI...")
        
        try:
            import subprocess
            result = subprocess.run(['databricks', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                self.validation_results["checks"].append({
                    "check": "Databricks CLI",
                    "status": "PASS",
                    "message": f"Databricks CLI is available: {version}"
                })
                print(f"  ✅ Databricks CLI: {version}")
            else:
                self.validation_results["errors"].append("Databricks CLI not working properly")
                self.validation_results["checks"].append({
                    "check": "Databricks CLI",
                    "status": "FAIL",
                    "message": "Databricks CLI command failed"
                })
                print(f"  ❌ Databricks CLI: Command failed")
        except FileNotFoundError:
            self.validation_results["errors"].append("Databricks CLI not found")
            self.validation_results["checks"].append({
                "check": "Databricks CLI",
                "status": "FAIL",
                "message": "Databricks CLI not found in PATH"
            })
            print(f"  ❌ Databricks CLI: Not found in PATH")
    
    def check_profile_config(self):
        """Check if Databricks profile is configured"""
        print("🔍 Checking Databricks profile...")
        
        profile = self.config.databricks_profile
        config_file = os.path.expanduser("~/.databrickscfg")
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    content = f.read()
                    if f"[{profile}]" in content:
                        self.validation_results["checks"].append({
                            "check": "Databricks profile",
                            "status": "PASS",
                            "message": f"Profile '{profile}' found in ~/.databrickscfg"
                        })
                        print(f"  ✅ Databricks profile: '{profile}' configured")
                    else:
                        self.validation_results["errors"].append(f"Profile '{profile}' not found in ~/.databrickscfg")
                        self.validation_results["checks"].append({
                            "check": "Databricks profile",
                            "status": "FAIL",
                            "message": f"Profile '{profile}' not found in ~/.databrickscfg"
                        })
                        print(f"  ❌ Databricks profile: '{profile}' not found in ~/.databrickscfg")
            except Exception as e:
                self.validation_results["errors"].append(f"Error reading ~/.databrickscfg: {e}")
                print(f"  ❌ Databricks profile: Error reading config file")
        else:
            self.validation_results["errors"].append("~/.databrickscfg file not found")
            self.validation_results["checks"].append({
                "check": "Databricks profile",
                "status": "FAIL",
                "message": "~/.databrickscfg file not found"
            })
            print(f"  ❌ Databricks profile: ~/.databrickscfg not found")
    
    def validate(self):
        """Run all validation checks"""
        print(f"🔍 Validating configuration for environment '{self.environment}'")
        print(f"Base name: {self.config.base_name}")
        print("=" * 60)
        
        self.check_required_fields()
        self.check_base_name_format()
        self.check_databricks_config()
        self.check_naming_consistency()
        self.check_environment_files()
        self.check_databricks_cli()
        self.check_profile_config()
        
        # Determine overall status
        if self.validation_results["errors"]:
            self.validation_results["overall_status"] = "FAIL"
        elif self.validation_results["warnings"]:
            self.validation_results["overall_status"] = "WARN"
        else:
            self.validation_results["overall_status"] = "PASS"
    
    def print_report(self):
        """Print validation report"""
        print("\n" + "=" * 60)
        print("📊 VALIDATION REPORT")
        print("=" * 60)
        print(f"Environment: {self.validation_results['environment']}")
        print(f"Base Name: {self.validation_results['base_name']}")
        print(f"Overall Status: {self.validation_results['overall_status']}")
        
        # Summary
        total_checks = len(self.validation_results["checks"])
        passed_checks = len([c for c in self.validation_results["checks"] if c["status"] == "PASS"])
        failed_checks = len([c for c in self.validation_results["checks"] if c["status"] == "FAIL"])
        warning_checks = len([c for c in self.validation_results["checks"] if c["status"] == "WARN"])
        
        print(f"\nChecks: {passed_checks} passed, {warning_checks} warnings, {failed_checks} failed")
        
        # Errors
        if self.validation_results["errors"]:
            print("\n❌ Errors:")
            for error in self.validation_results["errors"]:
                print(f"  - {error}")
        
        # Warnings
        if self.validation_results["warnings"]:
            print("\n⚠️ Warnings:")
            for warning in self.validation_results["warnings"]:
                print(f"  - {warning}")
        
        # Detailed checks
        if self.verbose:
            print("\n📋 Detailed Checks:")
            for check in self.validation_results["checks"]:
                status_icon = "✅" if check["status"] == "PASS" else "⚠️" if check["status"] == "WARN" else "❌"
                print(f"  {status_icon} {check['check']}: {check['message']}")
        
        print("\n" + "=" * 60)
        
        # Recommendations
        if self.validation_results["overall_status"] != "PASS":
            print("\n💡 Recommendations:")
            if self.validation_results["errors"]:
                print("  1. Fix all errors before proceeding")
            if self.validation_results["warnings"]:
                print("  2. Review warnings and update configuration if needed")
            print("  3. Run 'python config/setup_config.py setup' to configure a new environment")
            print("  4. Run 'python config/setup_config.py generate' to create .env file")
        else:
            print("\n🎉 Configuration is valid and ready to use!")

def main():
    parser = argparse.ArgumentParser(description="Validate configuration for base-chatbot")
    parser.add_argument("--environment", default="development", help="Environment to validate")
    parser.add_argument("--verbose", action="store_true", help="Show detailed check results")
    
    args = parser.parse_args()
    
    validator = ConfigurationValidator(
        environment=args.environment,
        verbose=args.verbose
    )
    
    validator.validate()
    validator.print_report()
    
    if validator.validation_results["overall_status"] == "FAIL":
        sys.exit(1)

if __name__ == "__main__":
    main()
