import os
import firebase_admin
from firebase_admin import credentials, messaging

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-adminsdk.json")

def init_firebase():
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_CREDENTIALS_PATH):
            try:
                cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
                print(f"[Firebase] Initialized with {FIREBASE_CREDENTIALS_PATH}")
            except Exception as e:
                print(f"[Firebase] Failed to initialize: {e}")
        else:
            print(f"[Firebase] Credentials file not found at {FIREBASE_CREDENTIALS_PATH}")

def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None):
    if not firebase_admin._apps:
        print(f"[Firebase] App not initialized. Skipping push notification to {fcm_token}.")
        return False
        
    if not fcm_token:
        print("[Firebase] No FCM token provided. Skipping.")
        return False
        
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data or {},
            token=fcm_token,
        )
        response = messaging.send(message)
        print(f"[Firebase] Successfully sent message: {response}")
        return True
    except Exception as e:
        print(f"[Firebase Error] Failed to send push notification: {e}")
        return False
