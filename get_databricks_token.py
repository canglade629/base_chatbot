#!/usr/bin/env python3
"""
Get Databricks Token Helper
Simple script to help you get your Databricks personal access token
"""

def main():
    print("🔑 DATABRICKS TOKEN HELPER")
    print("=" * 50)
    print()
    print("To test your endpoint, you need a Databricks personal access token.")
    print("Here's how to get one:")
    print()
    print("1. 🌐 Go to your Databricks workspace:")
    print("   https://dbc-0619d7f5-0bda.cloud.databricks.com/settings/tokens")
    print()
    print("2. 🔐 Sign in with your Databricks account")
    print()
    print("3. ➕ Click 'Generate new token'")
    print()
    print("4. 📝 Fill in the form:")
    print("   - Comment: 'ICC Chatbot Endpoint Testing'")
    print("   - Lifetime: Choose appropriate duration (e.g., 30 days)")
    print()
    print("5. 📋 Copy the generated token")
    print()
    print("6. 🔧 Update the test scripts:")
    print("   - Replace 'YOUR_TOKEN_HERE' in quick_endpoint_test.py")
    print("   - Replace 'YOUR_TOKEN_HERE' in test_serving_endpoint.py")
    print()
    print("7. 🚀 Run the tests!")
    print()
    print("⚠️  Security Note:")
    print("   - Keep your token secure")
    print("   - Don't commit it to version control")
    print("   - Regenerate it if compromised")
    print()
    print("🔗 Direct link to token page:")
    print("   https://dbc-0619d7f5-0bda.cloud.databricks.com/settings/tokens")

if __name__ == "__main__":
    main()
