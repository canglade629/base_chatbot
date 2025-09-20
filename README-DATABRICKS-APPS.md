# ICC Legal Research Assistant - Databricks Apps Deployment

This document provides instructions for deploying the ICC Legal Research Assistant as a Databricks App.

## Overview

The ICC Legal Research Assistant is an AI-powered legal research tool that provides intelligent responses to legal queries using ICC documentation. This version has been optimized for deployment on Databricks Apps.

## Prerequisites

### 1. Databricks CLI Setup

Install the Databricks CLI:
```bash
pip install databricks-cli
```

Configure authentication:
```bash
databricks configure
```

### 2. Environment Variables

Set the following environment variables:
```bash
export DATABRICKS_TOKEN="your_databricks_token_here"
```

### 3. Python Requirements

- Python 3.11 or later
- All dependencies are listed in `requirements-databricks.txt`

## Files Structure

```
base_chatbot/
├── app.yaml                          # Databricks Apps configuration
├── main_databricks.py                # Databricks-optimized entry point
├── requirements-databricks.txt       # Databricks-compatible dependencies
├── deploy_databricks.sh              # Deployment script
├── backend/
│   └── api/
│       └── app_databricks.py         # Databricks-optimized FastAPI app
└── frontend/                         # Static frontend files
```

## Key Modifications for Databricks Apps

### 1. Simplified Authentication
- Uses mock authentication instead of PostgreSQL
- All user operations are mocked for compatibility
- No database dependencies required

### 2. Optimized Dependencies
- Removed PostgreSQL dependencies (`asyncpg`, `psycopg2-binary`)
- Kept only essential packages for Databricks Apps
- Compatible with pre-installed Databricks libraries

### 3. Resource Optimization
- Configured for Databricks Apps resource limits (2 vCPUs, 6GB RAM)
- Optimized for serverless execution
- Health check endpoints for monitoring

## Deployment Instructions

### Option 1: Using the Deployment Script

1. Make sure you're authenticated with Databricks:
   ```bash
   databricks configure
   ```

2. Set your Databricks token:
   ```bash
   export DATABRICKS_TOKEN="your_token_here"
   ```

3. Run the deployment script:
   ```bash
   ./deploy_databricks.sh
   ```

### Option 2: Manual Deployment

1. Upload files to Databricks workspace:
   ```bash
   databricks workspace import_dir . /Workspace/Users/your-email@databricks.com/icc-legal-research-assistant
   ```

2. Create the app:
   ```bash
   databricks apps create icc-legal-research-assistant --source-code-path /Workspace/Users/your-email@databricks.com/icc-legal-research-assistant
   ```

3. Deploy the app:
   ```bash
   databricks apps deploy icc-legal-research-assistant --source-code-path /Workspace/Users/your-email@databricks.com/icc-legal-research-assistant
   ```

## Configuration

### App Configuration (app.yaml)

The app is configured with:
- **Entry Point**: `python main_databricks.py`
- **Port**: 8000 (configurable via PORT environment variable)
- **Host**: 0.0.0.0 (required for Databricks Apps)
- **Resources**: 2 vCPUs, 6GB RAM
- **Health Check**: `/health` endpoint

### Environment Variables

Set these in your Databricks workspace or app configuration:

```yaml
DATABRICKS_HOST: "https://dbc-0619d7f5-0bda.cloud.databricks.com"
DATABRICKS_ENDPOINT: "https://fe-vm-vdm-serverless-nmmvdg.cloud.databricks.com/serving-endpoints/databricks-gpt-oss-20b/invocations"
DATABRICKS_TOKEN: "your_token_here"
DATABASE_TYPE: "mock"
HOST: "0.0.0.0"
PORT: "8000"
LOG_LEVEL: "INFO"
```

## Running the App

1. Go to your Databricks workspace
2. Navigate to **Compute** > **Apps**
3. Find your app and click on it
4. Click **Start** to run the app
5. Access the app using the provided URL

## API Endpoints

### Health Check
- `GET /health` - App health status

### Authentication (Mock)
- `POST /auth/login` - User login
- `POST /auth/signup` - User registration
- `GET /auth/me` - Current user info

### Chat
- `POST /chat` - Send chat message and get AI response

### Frontend
- `GET /` - Main application interface
- `GET /app` - Alternative app route

## Monitoring and Logs

- View logs in the Databricks Apps interface
- Health check endpoint provides app status
- All operations are logged for debugging

## Troubleshooting

### Common Issues

1. **App won't start**
   - Check that all required environment variables are set
   - Verify the Databricks token is valid
   - Check the logs for specific error messages

2. **Authentication errors**
   - The app uses mock authentication in Databricks Apps
   - All user operations are mocked for compatibility

3. **Database errors**
   - The app is configured to use mock mode
   - No actual database connections are made

4. **Resource limits**
   - App is configured for 2 vCPUs and 6GB RAM
   - Monitor resource usage in Databricks Apps interface

### Debug Mode

To enable debug logging, set:
```bash
export LOG_LEVEL="DEBUG"
```

## Features

### ✅ Compatible with Databricks Apps
- Optimized for serverless execution
- Mock authentication system
- Resource-constrained environment

### ✅ AI-Powered Legal Research
- Integration with Databricks model serving endpoints
- Intelligent legal document analysis
- Structured response formatting

### ✅ Modern Web Interface
- Responsive design
- Real-time chat interface
- Markdown-formatted responses

### ✅ Health Monitoring
- Health check endpoints
- Comprehensive logging
- Error handling and fallbacks

## Limitations

- **Authentication**: Uses mock authentication (no real user management)
- **Database**: No persistent data storage (conversations not saved)
- **Resources**: Limited to 2 vCPUs and 6GB RAM
- **File Size**: Individual files must be < 10MB

## Support

For issues or questions:
1. Check the Databricks Apps logs
2. Verify environment variables
3. Test the health check endpoint
4. Review the troubleshooting section

## Version History

- **v1.0.0**: Initial Databricks Apps deployment
  - Mock authentication system
  - Optimized dependencies
  - Health monitoring
  - Resource constraints compliance
