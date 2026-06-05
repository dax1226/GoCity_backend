import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
  cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', 'your_cloud_name'),
  api_key = os.getenv('CLOUDINARY_API_KEY', 'your_api_key'),
  api_secret = os.getenv('CLOUDINARY_API_SECRET', 'your_api_secret')
)

def upload_image(file_bytes: bytes, folder: str = "profiles") -> str:
    """Uploads an image to Cloudinary and returns the secure URL."""
    try:
        response = cloudinary.uploader.upload(
            file_bytes,
            folder=folder,
            resource_type="image"
        )
        return response.get("secure_url")
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None
