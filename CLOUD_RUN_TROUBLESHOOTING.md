# Cloud Run Deployment Troubleshooting Guide

## 🚨 Common Issues and Solutions

### 1. App Not Opening / Frontend Not Loading

**Symptoms:**
- API responds with JSON: `{"message":"ICC Legal Research Assistant API","status":"running","version":"1.0.0"}`
- Frontend interface not visible
- Only API endpoints accessible

**Root Cause:**
- Missing frontend route configuration
- Static files not properly mounted

**Solution:**
- The app now includes proper frontend routing
- Root `/` redirects to `/app` which serves the HTML interface
- Static files are mounted at `/static` and `/js`

**Access Points:**
- Main App: `http://your-domain.com/` (redirects to `/app`)
- Direct App: `http://your-domain.com/app`
- Health Check: `http://your-domain.com/health`
- API Info: `http://your-domain.com/api/info`

### 2. Container Failed to Start and Listen on Port 8080

**Symptoms:**
- Error: "The user-provided container failed to start and listen on the port defined provided by the PORT=8080 environment variable within the allocated timeout"
- Container exits before becoming ready

**Root Causes & Solutions:**

#### A. Missing Environment Variables
```bash
# Ensure these environment variables are set in Cloud Run:
PORT=8080
HOST=0.0.0.0
PYTHONPATH=/app
PYTHONUNBUFFERED=1
DATABRICKS_TOKEN=your_token_here
```

#### B. Import Errors During Startup
- **Problem**: Missing dependencies or import failures
- **Solution**: Check the logs for specific import errors
- **Fix**: The app now has fallback mock services for missing dependencies

#### C. Authentication Service Failures
- **Problem**: Firebase credentials not available
- **Solution**: The app now falls back to mock authentication if Firebase fails

#### D. Memory/CPU Issues
- **Problem**: Insufficient resources
- **Solution**: Increase memory to 2Gi and CPU to 2 in Cloud Run configuration

### 2. Health Check Failures

**Symptoms:**
- Container starts but health checks fail
- Service shows as unhealthy

**Solutions:**
- The app now includes a `/health` endpoint
- Health check timeout increased to 30s
- Startup period increased to 10s

### 3. Timeout Issues

**Symptoms:**
- Requests timeout after 30 seconds
- Service becomes unresponsive

**Solutions:**
- Request timeout increased to 900s (15 minutes)
- Container concurrency set to 10
- CPU throttling disabled for better performance

## 🔧 Deployment Steps

### 1. Build and Test Locally
```bash
# Run the test script
python test_startup.py

# Build Docker image
docker build -t icc-chatbot .

# Test locally
docker run -p 8080:8080 -e DATABRICKS_TOKEN=your_token icc-chatbot
```

### 2. Deploy to Cloud Run
```bash
# Use the deployment script
./deploy.sh

# Or manually:
gcloud run deploy icc-chatbot \
    --image gcr.io/PROJECT_ID/icc-chatbot \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --concurrency 10 \
    --port 8080 \
    --set-env-vars "PORT=8080,HOST=0.0.0.0,PYTHONPATH=/app,PYTHONUNBUFFERED=1" \
    --set-secrets "DATABRICKS_TOKEN=databricks-token:latest"
```

### 3. Verify Deployment
```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe icc-chatbot --region=us-central1 --format="value(status.url)")

# Test health endpoint
curl $SERVICE_URL/health

# Test root endpoint
curl $SERVICE_URL/
```

## 📊 Monitoring and Debugging

### 1. Check Logs
```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=icc-chatbot" --limit 50

# Follow logs in real-time
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=icc-chatbot"
```

### 2. Check Service Status
```bash
# Get service details
gcloud run services describe icc-chatbot --region=us-central1

# List revisions
gcloud run revisions list --service=icc-chatbot --region=us-central1
```

### 3. Test Endpoints
```bash
# Health check
curl -f $SERVICE_URL/health

# Root endpoint
curl $SERVICE_URL/

# Chat endpoint (requires authentication)
curl -X POST $SERVICE_URL/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "test"}'
```

## 🛠️ Configuration Files

### 1. Dockerfile
- Multi-stage build for optimization
- Health check on `/health` endpoint
- Proper port exposure (8080)
- Non-root user for security

### 2. Cloud Run Configuration (cloud-run.yaml)
- Memory: 2Gi
- CPU: 2
- Timeout: 900s
- Concurrency: 10
- Health checks configured

### 3. Environment Variables
- `PORT=8080` (required by Cloud Run)
- `HOST=0.0.0.0` (bind to all interfaces)
- `PYTHONPATH=/app` (Python module path)
- `PYTHONUNBUFFERED=1` (immediate output)

## 🚀 Performance Optimizations

### 1. Resource Allocation
- **Memory**: 2Gi (increased from default)
- **CPU**: 2 cores (increased from default)
- **Concurrency**: 10 requests per instance

### 2. Startup Optimizations
- CPU boost enabled during startup
- Execution environment: gen2
- CPU throttling disabled

### 3. Application Optimizations
- Lazy loading of heavy dependencies
- Mock services for missing dependencies
- Comprehensive error handling
- Structured logging

## 🔍 Debugging Checklist

1. **Check Environment Variables**
   - [ ] PORT is set to 8080
   - [ ] HOST is set to 0.0.0.0
   - [ ] DATABRICKS_TOKEN is set
   - [ ] PYTHONPATH is set to /app

2. **Check Resource Limits**
   - [ ] Memory is at least 2Gi
   - [ ] CPU is at least 2 cores
   - [ ] Timeout is at least 900s

3. **Check Health Endpoints**
   - [ ] `/health` returns 200
   - [ ] `/` returns 200
   - [ ] Health check timeout is sufficient

4. **Check Logs**
   - [ ] No import errors
   - [ ] No authentication failures
   - [ ] Server starts successfully
   - [ ] Port 8080 is bound

5. **Check Dependencies**
   - [ ] All Python packages installed
   - [ ] Docker build successful
   - [ ] No missing files

## 📞 Support

If you continue to experience issues:

1. Check the Cloud Run logs for specific error messages
2. Verify all environment variables are set correctly
3. Ensure the Docker image builds and runs locally
4. Test the health endpoints manually
5. Consider increasing resource limits if needed

The application now includes comprehensive error handling and fallback mechanisms to handle common deployment issues.
