import requests
import json
import uuid
import sys

# Ensure UTF-8 output even on Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Define Production API URL
URL = "https://ai-reservation.onrender.com/api/global-chat/"

# Generate a unique User ID for testing
user_id = f"test_jakaria_{uuid.uuid4().hex[:6]}"

def send_message(message):
    payload = {
        "message": message,
        "user_id": user_id
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(URL, json=payload, headers=headers, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

print(f"--- STARTING PRODUCTION MEMORY TEST (User ID: {user_id}) ---")

# 1. State identity
print("Step 1: Telling AI My Name...")
resp1 = send_message("My name is Jakaria. Please remember me.")
# Filter emojis for console safety
answer1 = resp1.get('answer', 'ERROR').encode('ascii', 'ignore').decode('ascii')
print(f"AI Response 1: {answer1}")
print(f"Debug Items Found: {resp1.get('debug_history_items', 0)}")

# 2. Ask identity
print("\nStep 2: Asking AI 'What is my name?'...")
resp2 = send_message("What is my name?")
answer2 = resp2.get('answer', 'ERROR').encode('ascii', 'ignore').decode('ascii')
print(f"AI Response 2: {answer2}")
print(f"Debug Items Found: {resp2.get('debug_history_items', 0)}")

if "Jakaria" in resp2.get('answer', ''):
    print("\n✅ SUCCESS: AI Remembered the Name!")
else:
    print("\n❌ FAILED: AI Did Not Remember the Name.")

print("--- TEST COMPLETED ---")
