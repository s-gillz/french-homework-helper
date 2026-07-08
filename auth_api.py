import os
import requests

# Get the Web API Key from Hugging Face Secrets
WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")

def send_verification_email(email):
    """Sends a verification email using Firebase REST API"""
    if not WEB_API_KEY:
        print("Error: FIREBASE_WEB_API_KEY not found in secrets!")
        return False
        
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={WEB_API_KEY}"
    payload = {
        "requestType": "VERIFY_EMAIL",
        "email": email
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending verification email: {e}")
        return False

def send_password_reset_email(email):
    """Sends a password reset email using Firebase REST API"""
    if not WEB_API_KEY:
        return False
        
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={WEB_API_KEY}"
    payload = {
        "requestType": "PASSWORD_RESET",
        "email": email
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending reset email: {e}")
        return False
