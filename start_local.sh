#!/bin/bash

# Start the ICC Chatbot locally for testing

echo "🚀 Starting ICC Legal Research Assistant locally..."
echo "================================================"

# Kill any existing processes
pkill -f "python main.py" 2>/dev/null || true
pkill -f uvicorn 2>/dev/null || true

# Set environment variables
export PORT=8000
export HOST=0.0.0.0
export PYTHONPATH=/Users/christophe.anglade/Documents/icc_chatbot
export PYTHONUNBUFFERED=1

# Optional: Set Databricks token if available
if [ -n "$DATABRICKS_TOKEN" ]; then
    echo "✅ Using provided DATABRICKS_TOKEN"
else
    echo "⚠️  No DATABRICKS_TOKEN set - chat functionality will be limited"
fi

echo ""
echo "🌐 Application will be available at:"
echo "   http://localhost:8000/"
echo "   http://localhost:8000/app"
echo ""
echo "🔍 Health check:"
echo "   http://localhost:8000/health"
echo ""
echo "📊 API info:"
echo "   http://localhost:8000/api/info"
echo ""

# Start the application
python main.py
