# Firebase Credentials Directory

This directory should contain your Firebase service account JSON file.

## For Local Development (RECOMMENDED):
### Option 1: Using gcloud CLI (Easiest)
1. Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install
2. Authenticate: `gcloud auth application-default login`
3. Set project: `gcloud config set project icc-project-472009`
4. The app will automatically use these credentials - no additional setup needed!

### Option 2: Service Account Key File
1. Download your Firebase service account key from the Firebase Console
2. Place it in this directory as: icc-project-472009-firebase-adminsdk.json
3. Or set the FIREBASE_SERVICE_ACCOUNT_PATH environment variable

## For Production:
- Use Google Cloud's default credentials
- Or set GOOGLE_APPLICATION_CREDENTIALS environment variable

## Verification:
Run `python -c "from backend.services.firestore_auth import firestore_auth; print('✅ Connected!' if firestore_auth.db else '❌ Failed')"` to test your connection.
