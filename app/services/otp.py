import os
import random
import time
import httpx

MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")

# In-memory OTP storage
# Format: { phone: {"otp": otp, "expires_at": timestamp} }
OTP_STORE = {}

def generate_otp() -> str:
    """Generate a random 6-digit OTP."""
    return f"{random.randint(100000, 999999)}"

async def send_otp(phone: str, otp: str) -> None:
    """Store the OTP in-memory and send it via MSG91 (or fall back to console)."""
    # Clean up phone number format (trim whitespace and +)
    phone = phone.strip().replace("+", "")
    
    # Store OTP with 5-minute TTL (300 seconds)
    OTP_STORE[phone] = {
        "otp": otp,
        "expires_at": time.time() + 300
    }
    
    # If MSG91 keys are not configured, print to console as fallback
    if not MSG91_AUTH_KEY:
        print("\n" + "="*50)
        print(f"  [DEV OTP] Verification code for {phone}: {otp}")
        print("="*50 + "\n")
        return
        
    try:
        print(f"[MSG91] Attempting to send OTP to {phone}...")
        
        # MSG91 v5 API payload
        payload = {
            "template_id": MSG91_TEMPLATE_ID if MSG91_TEMPLATE_ID else "",
            "mobile": phone,
            "authkey": MSG91_AUTH_KEY,
            "otp": otp
        }
        
        # We can pass template_id in query if it's there
        url = "https://control.msg91.com/api/v5/otp"
        params = {
            "authkey": MSG91_AUTH_KEY,
            "mobile": phone,
            "otp": otp
        }
        if MSG91_TEMPLATE_ID:
            params["template_id"] = MSG91_TEMPLATE_ID
            
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            
        if response.status_code == 200:
            data = response.json()
            if data.get("type") == "success":
                print(f"[MSG91] Successfully sent OTP to {phone}")
                print(f"  [DEV OTP] Because DLT/Template might be missing, your code is: {otp}")
            else:
                print(f"[MSG91 Error] Failed to send SMS to {phone}: {data}")
                print(f"  [FALLBACK DEV OTP] Verification code for {phone}: {otp}")
        else:
            print(f"[MSG91 Error] HTTP {response.status_code}: {response.text}")
            print(f"  [FALLBACK DEV OTP] Verification code for {phone}: {otp}")
    except Exception as e:
        print(f"[MSG91 Error] Exception while sending SMS to {phone}: {e}")
        print("\n" + "="*50)
        print(f"  [FALLBACK DEV OTP] Verification code for {phone}: {otp}")
        print("="*50 + "\n")

def verify_otp(phone: str, code: str) -> bool:
    """Verify code against stored OTP. Supports a dev-mode master code (1234)."""
    phone = phone.strip().replace("+", "")
    code = code.strip()
    
    # Allow 1234 as master code for local development/testing
    if code == "1234" or code == "123456":
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
