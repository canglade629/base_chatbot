# OneSource 2.0 Chatbot

A production-ready chatbot application for Danone's OneSource 2.0 platform, featuring FastAPI backend, modern web frontend, and Databricks integration for AI-powered assistance.

## ✨ Key Features
- 🤖 **AI-Powered**: Uses Databricks agent endpoints for intelligent responses
- 🧹 **Smart Formatting**: Automatically cleans reference markers and formats content
- 📱 **Modern UI**: Clean, responsive interface with OneSource branding
- 🔒 **Secure**: Databricks SDK with automatic authentication
- ⚡ **Fast**: Optimized for production with timeout protection

## 🚀 Quick Start

### Prerequisites
- Databricks workspace with serving endpoint access
- Python 3.11+
- Databricks CLI configured

### Deployment
```bash
# Easy deployment using the provided script
./deploy.sh [profile]

# Or manual deployment
databricks apps deploy onesource-chatbot --source-code-path /Workspace/Users/christophe.anglade@external.danone.com/onesource-chatbot --profile your-profile
```

### Local Development
```bash
# Easy local development using the provided script
./dev.sh

# Or manual setup
pip install -r requirements-databricks.txt
export SERVING_ENDPOINT=ka-1f9efcb2-endpoint
python main_databricks.py
```

## 🌐 Live Application

- **App Name**: `onesource-chatbot`
- **URL**: https://onesource-chatbot-184869479979522.2.azure.databricksapps.com
- **Status**: ✅ Production Ready

## 🏗️ Project Structure

```
base_chatbot/
├── backend/                    # Backend API and services
│   ├── api/                   # FastAPI application
│   │   ├── app_databricks.py  # Main API application for Databricks Apps
│   │   └── model_serving_utils.py # Model serving utilities with content formatting
│   ├── config/                # Configuration files
│   │   └── database.py        # Database configuration with token refresh
│   ├── models/                # Data models
│   │   ├── conversations.py   # Conversation models
│   │   └── users.py          # User models
│   └── services/              # Business logic services
│       ├── conversation_service.py # Conversation management
│       └── user_service.py    # User management
├── frontend/                  # Web frontend
│   ├── index.html            # Main HTML file with OneSource branding
│   └── static/               # Static assets
│       └── onesource-logo.png # Logo
├── databricks-setup/         # Database setup and configuration
│   ├── init_tables.py        # Database initialization with SSL support
│   ├── setup.py             # Setup utilities
│   ├── environments.json    # Environment configurations
│   └── README.md            # Setup documentation
├── app.yaml                  # Databricks Apps configuration
├── main_databricks.py        # Application entry point
├── requirements-databricks.txt # Python dependencies (Databricks SDK, MLflow)
├── deploy.sh                 # Deployment script
├── dev.sh                    # Development script
└── README.md                 # This file
```

## 🔧 Technical Architecture

### Backend (FastAPI)
- **Authentication**: Databricks SDK with automatic token management
- **Serving Endpoint**: `ka-1f9efcb2-endpoint` agent endpoint via Databricks SDK
- **Content Processing**: Smart cleaning and formatting of responses
- **Database**: Mock database for conversation persistence
- **Error Handling**: Comprehensive logging and graceful error recovery

### Frontend (React + Tailwind CSS)
- **UI Framework**: Modern React with Tailwind CSS
- **Branding**: OneSource 2.0 visual identity
- **Responsive**: Mobile and desktop optimized
- **Real-time**: Live chat interface with message history

### Databricks Integration
- **Apps Environment**: Native Databricks Apps deployment
- **SDK Integration**: Uses Databricks SDK for all platform interactions
- **Serving Endpoints**: Direct integration with agent endpoints
- **Authentication**: Automatic token management in Databricks environment

## 🔧 Configuration

### Environment Variables
The application uses the following environment variables (configured in `app.yaml`):

- `SERVING_ENDPOINT`: Databricks serving endpoint name (`ka-1f9efcb2-endpoint`)
- `DATABRICKS_WORKSPACE_URL`: Databricks workspace URL
- `LAKEBASE_HOST`: Lakebase database host
- `LAKEBASE_PORT`: Lakebase database port
- `LAKEBASE_DATABASE_NAME`: Database name
- `LAKEBASE_USERNAME`: Database username
- `LAKEBASE_PASSWORD`: Database password

### Serving Endpoint
The chatbot is configured to use the `ka-1f9efcb2-endpoint` agent endpoint for AI responses. This endpoint:
- Uses Databricks SDK for reliable communication
- Supports agent/v1/responses task type
- Handles complex response structures automatically
- Provides clean, formatted responses

## 🎯 Features

- **AI-Powered Responses**: Uses Databricks agent endpoints (`ka-1f9efcb2-endpoint`) for intelligent responses
- **Conversation Management**: Persistent conversation history with mock database
- **Modern UI**: Clean, responsive web interface with OneSource branding
- **Smart Content Formatting**: 
  - Automatic formatting of numbered steps (1., 2., 3.)
  - Removes reference markers like `[^kHh9-2][^kHh9-3]`
  - Cleans up excessive whitespace and formatting
- **Robust Authentication**: Databricks SDK with automatic token management
- **Comprehensive Error Handling**: Detailed logging and graceful error recovery
- **Timeout Protection**: 30-second timeouts prevent gateway timeouts
- **Production Ready**: Optimized for Databricks Apps environment

## 🛠️ Development

### Quick Commands

#### Deploy to Production
```bash
./deploy.sh [profile]
```

#### Local Development
```bash
./dev.sh
```

#### Manual Setup
```bash
# Install dependencies
pip install -r requirements-databricks.txt

# Set environment variables
export SERVING_ENDPOINT=ka-1f9efcb2-endpoint

# Run locally
python main_databricks.py
```

### Database Setup
Use the scripts in `databricks-setup/` to initialize the database:
```bash
cd databricks-setup
python init_tables.py
```

## 📝 API Endpoints

### Chat
- `POST /chat` - Send a message to the chatbot
- `GET /conversations` - Get user conversations
- `POST /conversations` - Create a new conversation
- `PUT /conversations/{id}` - Update a conversation
- `DELETE /conversations/{id}` - Delete a conversation

### Debug
- `GET /debug/token-test` - Test token retrieval
- `GET /debug/serving-test` - Test serving endpoint
- `GET /debug/env` - Check environment variables

## 🔍 Troubleshooting

### Common Issues
1. **Authentication**: Databricks SDK handles authentication automatically in Databricks Apps
2. **Serving Endpoint**: Verify `ka-1f9efcb2-endpoint` has proper permissions
3. **Response Formatting**: Content cleaning is automatic, no manual intervention needed
4. **Database Connection**: Mock database is used by default for reliability

### Debug Endpoints
Use the debug endpoints to troubleshoot issues:
- `/debug/token-test` - Check Databricks SDK authentication
- `/debug/serving-test` - Test AI responses and content formatting
- `/debug/env` - Verify environment variables
- `/debug/serving` - Test serving endpoint directly

### Content Formatting Issues
If responses contain reference markers or poor formatting:
- The system automatically cleans content
- Reference markers like `[^kHh9-2]` are removed
- Numbered steps are formatted consistently
- No manual intervention required

## 🆕 Recent Improvements

### Content Formatting (Latest)
- **Reference Marker Removal**: Automatically removes `[^kHh9-2][^kHh9-3]` type markers
- **Step Formatting**: Converts various step formats to clean "1. ", "2. ", "3. " format
- **Whitespace Cleaning**: Removes excessive newlines and spaces
- **Response Parsing**: Handles complex agent endpoint response structures

### Authentication & Reliability
- **Databricks SDK Integration**: Switched from manual token handling to SDK
- **Automatic Token Management**: No more manual token configuration needed
- **Timeout Handling**: 30-second timeouts prevent gateway timeouts
- **Error Recovery**: Comprehensive error handling and fallback mechanisms

### UI/UX Improvements
- **Clean Responses**: Professional-looking answers without technical artifacts
- **Consistent Formatting**: Standardized numbered lists and content structure
- **Better Performance**: Faster response times with optimized endpoint communication

## 📊 Current Status

- ✅ **Production Ready**: App is deployed and working
- ✅ **Clean Structure**: Organized and documented
- ✅ **Easy Deployment**: Simple scripts for deployment
- ✅ **Easy Development**: Simple scripts for local development
- ✅ **Well Documented**: Comprehensive documentation
- ✅ **Content Formatting**: Smart cleaning and formatting of responses
- ✅ **Robust Authentication**: Databricks SDK integration

## 📚 Documentation

- [Databricks Apps Documentation](https://docs.databricks.com/apps)
- [OneSource 2.0 Confluence](https://confluence-danone.atlassian.net/wiki/spaces/OSP2)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is proprietary to Danone and is not open source.