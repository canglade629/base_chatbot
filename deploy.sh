#!/bin/bash

# ICC Chatbot Cloud Run Deployment Script

set -e

# Configuration
PROJECT_ID="your-project-id"  # Replace with your actual project ID
SERVICE_NAME="icc-chatbot"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🚀 Deploying ICC Chatbot to Cloud Run"
echo "Project ID: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo "Image: $IMAGE_NAME"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first."
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install it first."
    exit 1
fi

# Set the project
echo "🔧 Setting project to $PROJECT_ID"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs"
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Build and push the Docker image
echo "🐳 Building and pushing Docker image"
docker build -t $IMAGE_NAME .
docker push $IMAGE_NAME

# Create secret for Databricks token if it doesn't exist
echo "🔐 Setting up secrets"
if ! gcloud secrets describe databricks-token &> /dev/null; then
    echo "Creating databricks-token secret..."
    echo "Please enter your Databricks token:"
    read -s DATABRICKS_TOKEN
    echo -n "$DATABRICKS_TOKEN" | gcloud secrets create databricks-token --data-file=-
else
    echo "Secret databricks-token already exists"
fi

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run"
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --concurrency 10 \
    --max-instances 10 \
    --port 8080 \
    --set-env-vars "PORT=8080,HOST=0.0.0.0,PYTHONPATH=/app,PYTHONUNBUFFERED=1" \
    --set-secrets "DATABRICKS_TOKEN=databricks-token:latest" \
    --execution-environment gen2 \
    --cpu-throttling

echo "✅ Deployment complete!"
echo "🌐 Service URL:"
gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)"

echo ""
echo "🧪 Testing the deployment..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
curl -f "$SERVICE_URL/health" && echo "✅ Health check passed!" || echo "❌ Health check failed!"
