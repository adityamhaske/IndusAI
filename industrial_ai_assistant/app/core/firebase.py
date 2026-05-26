import firebase_admin
from firebase_admin import credentials, storage, firestore
import os

_app = None

def get_firebase_app():
    global _app
    if _app is None:
        # On Cloud Run, uses Application Default Credentials automatically.
        # Locally, set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON.
        try:
            cred = credentials.ApplicationDefault()
        except ValueError:
            # Fallback if no ADC found
            cred = None
            
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
        options = {}
        if bucket_name:
            options["storageBucket"] = bucket_name
            
        if cred:
            _app = firebase_admin.initialize_app(cred, options)
        else:
            _app = firebase_admin.initialize_app(options=options)
    return _app

def get_storage_bucket():
    get_firebase_app()
    return storage.bucket()

def get_firestore_client():
    get_firebase_app()
    return firestore.client()
