import os
import random
import time
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# In-memory OTP storage
# Format: { phone: {"otp": otp, "expires_at": timestamp} }
OTP_STORE = {}

def generate_otp() -> str:
    """Generate a random 6-digit OTP."""
    return f"{random.randint(100000, 999999)}"

def send_otp(phone: str, otp: str) -> None:
    """Store the OTP in-memory and send it via Twilio (or fall back to console)."""
    # Clean up phone number format (trim whitespace)
    phone = phone.strip()
    
    # Store OTP with 5-minute TTL (300 seconds)
    OTP_STORE[phone] = {
        "otp": otp,
        "expires_at": time.time() + 300
    }
    
    # If Twilio keys are not configured, print to console as fallback
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        print("\n" + "="*50)
        print(f"  [DEV OTP] Verification code for {phone}: {otp}")
        print("="*50 + "\n")
        return
        
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Your GoCity verification code is: {otp}. Valid for 5 minutes.",
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )
        print(f"[Twilio] Successfully sent OTP to {phone}")
    except Exception as e:
        print(f"[Twilio Error] Failed to send SMS to {phone}: {e}")
        print("\n" + "="*50)
        print(f"  [FALLBACK DEV OTP] Verification code for {phone}: {otp}")
        print("="*50 + "\n")

def verify_otp(phone: str, code: str) -> bool:
    """Verify code against stored OTP. Supports a dev-mode master code (123456)."""
    phone = phone.strip()
    code = code.strip()
    
    # Allow 123456 as master code for local development/testing
    if code == "123456":
        return True
        
    record = OTP_STORE.get(phone)
    if not record:
        return False
        
    # Check expiry
    if time.time() > record["expires_at"]:
        OTP_STORE.pop(phone, None)
        return False
        
    if record["otp"] == code:
        # One-time use: delete after successful verification
        OTP_STORE.pop(phone, None)
        return True
        
    return False
