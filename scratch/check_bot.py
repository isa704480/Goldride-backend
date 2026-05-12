import requests

TOKEN = "8502417199:AAG2Uaw1arTgiln-pKxCAOSFuTNpeotwfZ0"
# Note: For local development, we'd use ngrok. 
# For now, I'll set it to a placeholder or just check the token.
url = f"https://api.telegram.org/bot{TOKEN}/getMe"
try:
    resp = requests.get(url)
    print(f"Bot Status: {resp.json()}")
except Exception as e:
    print(f"Error: {e}")
