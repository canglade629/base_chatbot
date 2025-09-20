#!/usr/bin/env python3
"""
Debug script to check Lakebase instance status
"""

import json
import subprocess

def run_cli_command(command, description):
    """Run a CLI command and return the result"""
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

def main():
    print("🔍 Debugging Lakebase instance status...")
    
    # Check if Lakebase instance already exists
    list_result = run_cli_command([
        "databricks", "database", "list-database-instances", "-o", "json"
    ], "List Lakebase instances")
    
    print(f"List result success: {list_result['success']}")
    print(f"List result output: {list_result['output']}")
    print(f"List result error: {list_result['error']}")
    
    if list_result["success"]:
        try:
            instances = json.loads(list_result["output"])
            print(f"Parsed instances: {instances}")
            print(f"Is list: {isinstance(instances, list)}")
            
            if isinstance(instances, list):
                instance_list = instances
            else:
                instance_list = instances.get("database_instances", [])
            
            print(f"Instance list: {instance_list}")
            print(f"Instance list length: {len(instance_list)}")
            
            existing_instances = [inst for inst in instance_list 
                                if inst.get("name") == "danone-pg-db"]
            print(f"Existing instances with name 'danone-pg-db': {existing_instances}")
            print(f"Should create instance: {len(existing_instances) == 0}")
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
    
    # Try to create the instance
    print("\n🔄 Attempting to create Lakebase instance...")
    create_result = run_cli_command([
        "databricks", "database", "create-database-instance",
        "danone-pg-db",
        "--capacity", "CU_1"
    ], "Create Lakebase database")
    
    print(f"Create result success: {create_result['success']}")
    print(f"Create result output: {create_result['output']}")
    print(f"Create result error: {create_result['error']}")

if __name__ == "__main__":
    main()
