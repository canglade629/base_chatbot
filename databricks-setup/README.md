# Databricks Setup

Essential scripts for setting up and managing the base-chatbot Databricks environment.

## Quick Start

### 1. Setup Resources
```bash
# Create all Databricks resources
python setup.py --environment development

# Two-step setup (recommended)
python setup.py --environment development --step resources
python init_tables.py --environment development
```

### 2. Verify Setup
```bash
# Check all components
python check_complete_setup.py --environment development --verbose
```

### 3. Configure New Environment
```bash
# Interactive setup
python setup_config.py
```

## What Gets Created

**Databricks Resources:**
- App (`basename-app`)
- Unity Catalog (`basename_uc`) with schema and volume
- SQL Warehouse (`basename_wh`)
- Vector Search Database (`basename-vs`)

**Lakebase PostgreSQL:**
- Database Instance (`basename-pg-db`)
- Schema (`basename_pg_schema`)
- Tables: users, conversations, messages, user_sessions, conversation_analytics, system_config

## Files

- `setup.py` - Main setup script
- `check_complete_setup.py` - Verification script
- `init_tables.py` - Lakebase schema/tables creation
- `setup_config.py` - Interactive configuration
- `config_manager.py` - Configuration management
- `environments.json` - Environment settings

## Configuration

All resources use configurable names based on `base_name`:
- App: `{base_name}-app`
- Unity Catalog: `{base_name}_uc`
- Lakebase DB: `{base_name}-pg-db`
- Vector Search: `{base_name}-vs`

## Troubleshooting

**Common Issues:**
- Ensure Databricks CLI is installed: `pip install databricks-cli`
- Check your `~/.databrickscfg` profile
- Use `--verbose` for detailed output
- Existing resources are skipped automatically