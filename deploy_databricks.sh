#!/bin/bash

# Databricks Apps Deployment Script
# This script deploys the ICC Legal Research Assistant to Databricks Apps

set -e

echo "🚀 Starting Databricks Apps deployment..."

# Check if Databricks CLI is installed
if ! command -v databricks &> /dev/null; then
    echo "❌ Databricks CLI is not installed. Please install it first:"
    echo "   pip install databricks-cli"
    exit 1
fi

# Check if user is authenticated
if ! databricks workspace ls &> /dev/null; then
    echo "❌ Not authenticated with Databricks. Please run:"
    echo "   databricks configure"
    exit 1
fi

# Set variables
APP_NAME="icc-legal-research-assistant"
WORKSPACE_PATH="/Workspace/Users/$(databricks workspace ls | head -1 | cut -d'/' -f4)/$APP_NAME"

echo "📁 App name: $APP_NAME"
echo "📁 Workspace path: $WORKSPACE_PATH"

# Create app directory in workspace
echo "📂 Creating app directory..."
databricks workspace mkdirs "$WORKSPACE_PATH" || true

# Sync app files to workspace
echo "📤 Syncing app files to workspace..."
databricks workspace import_dir . "$WORKSPACE_PATH" --overwrite

# Create the app
echo "🔧 Creating Databricks app..."
databricks apps create "$APP_NAME" --source-code-path "$WORKSPACE_PATH" || echo "App may already exist"

# Deploy the app
echo "🚀 Deploying app..."
databricks apps deploy "$APP_NAME" --source-code-path "$WORKSPACE_PATH"

echo "✅ Deployment completed!"
echo ""
echo "📋 Next steps:"
echo "1. Go to your Databricks workspace"
echo "2. Navigate to Compute > Apps"
echo "3. Find '$APP_NAME' and click on it"
echo "4. Click 'Start' to run the app"
echo "5. Access the app using the provided URL"
echo ""
echo "🔧 Configuration:"
echo "- Make sure to set the DATABRICKS_TOKEN environment variable"
echo "- The app will use mock authentication in Databricks Apps"
echo "- All database operations will be mocked for compatibility"
