#!/usr/bin/env python3
"""
Local development setup script for ICC Legal Research Assistant
This script helps set up the application for local development without requiring Firebase credentials
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def create_env_file():
    """Create .env file for local development"""
    env_content = """# ICC Legal Research Assistant - Local Development Configuration

# JWT Configuration (REQUIRED)
JWT_SECRET_KEY=local-development-secret-key-change-in-production

# Firestore Configuration (OPTIONAL - will use mock if not available)
# FIREBASE_SERVICE_ACCOUNT_PATH=config/firebase-credentials/icc-project-472009-firebase-adminsdk.json

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Application Settings
MAX_CONVERSATIONS_PER_USER=20
"""
    
    env_file = Path(".env")
    if not env_file.exists():
        with open(env_file, "w") as f:
            f.write(env_content)
        print("✅ Created .env file for local development")
    else:
        print("ℹ️  .env file already exists")

def setup_gcloud_auth():
    """Set up Google Cloud authentication for local development"""
    print("\n🔧 Setting up Google Cloud authentication...")
    
    # Check if gcloud is installed
    try:
        result = subprocess.run(["gcloud", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Google Cloud CLI is installed")
            
            # Check if user is authenticated
            auth_result = subprocess.run(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], 
                                       capture_output=True, text=True)
            if auth_result.returncode == 0 and auth_result.stdout.strip():
                print(f"✅ Authenticated as: {auth_result.stdout.strip()}")
                
                # Set application default credentials
                adc_result = subprocess.run(["gcloud", "auth", "application-default", "login"], 
                                          capture_output=True, text=True)
                if adc_result.returncode == 0:
                    print("✅ Application Default Credentials set up successfully")
                    return True
                else:
                    print("❌ Failed to set up Application Default Credentials")
                    print(f"Error: {adc_result.stderr}")
            else:
                print("❌ Not authenticated with Google Cloud")
                print("Please run: gcloud auth login")
        else:
            print("❌ Google Cloud CLI not found")
            print("Please install Google Cloud CLI: https://cloud.google.com/sdk/docs/install")
    except FileNotFoundError:
        print("❌ Google Cloud CLI not found")
        print("Please install Google Cloud CLI: https://cloud.google.com/sdk/docs/install")
    
    return False

def create_firebase_config_dir():
    """Create Firebase configuration directory structure"""
    config_dir = Path("config/firebase-credentials")
    config_dir.mkdir(parents=True, exist_ok=True)
    
    readme_content = """# Firebase Credentials Directory

This directory should contain your Firebase service account JSON file.

## For Local Development:
1. Download your Firebase service account key from the Firebase Console
2. Place it in this directory as: icc-project-472009-firebase-adminsdk.json
3. Or set the FIREBASE_SERVICE_ACCOUNT_PATH environment variable

## For Production:
- Use Google Cloud's default credentials
- Or set GOOGLE_APPLICATION_CREDENTIALS environment variable

## Alternative (Recommended for Local Development):
- Use `gcloud auth application-default login` to set up credentials
- The app will automatically use these credentials
"""
    
    readme_file = config_dir / "README.md"
    with open(readme_file, "w") as f:
        f.write(readme_content)
    
    print(f"✅ Created Firebase config directory: {config_dir}")

def install_dependencies():
    """Install Python dependencies"""
    print("\n📦 Installing Python dependencies...")
    
    requirements_files = ["requirements.txt", "requirements-web.txt"]
    
    for req_file in requirements_files:
        if Path(req_file).exists():
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)
                print(f"✅ Installed dependencies from {req_file}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install dependencies from {req_file}: {e}")

def main():
    """Main setup function"""
    print("🚀 Setting up ICC Legal Research Assistant for local development...\n")
    
    # Create .env file
    create_env_file()
    
    # Create Firebase config directory
    create_firebase_config_dir()
    
    # Install dependencies
    install_dependencies()
    
    # Try to set up Google Cloud authentication
    gcloud_setup = setup_gcloud_auth()
    
    print("\n" + "="*60)
    print("🎉 Setup Complete!")
    print("="*60)
    
    if gcloud_setup:
        print("✅ Google Cloud authentication is set up")
        print("✅ The app will connect to Firestore using your credentials")
    else:
        print("⚠️  Google Cloud authentication not set up")
        print("✅ The app will use mock authentication for local development")
        print("   To use real Firestore:")
        print("   1. Install Google Cloud CLI")
        print("   2. Run: gcloud auth login")
        print("   3. Run: gcloud auth application-default login")
    
    print("\n🚀 To start the application:")
    print("   python main.py")
    print("\n📱 The app will be available at: http://localhost:8000")

if __name__ == "__main__":
    main()
