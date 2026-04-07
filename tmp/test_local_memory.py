import requests
import json
import uuid
import sys

# Ensure UTF-8 output
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Define LOCAL API URL
URL = "http://127.0.0.1:8000/api/global-chat/"

chat_buffer = []

def send_message(message):
    global chat_buffer
    payload = {
        "message": message,
        "chat_history": chat_buffer 
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(URL, json=payload, headers=headers, timeout=30)
        data = response.json()
        if "answer" in data:
            chat_buffer.append({"role": "user", "content": message})
            chat_buffer.append({"role": "assistant", "content": data["answer"]})
        return data
    except Exception as e:
        return {"error": str(e)}

print("--- STARTING LOCAL MEMORY TEST (Stateless) ---")

# Turn 1
print("Step 1: Saying Name...")
resp1 = send_message("My name is Jakaria Local.")
print(f"AI: {resp1.get('answer', 'ERROR')}")

# Turn 2
print("\nStep 2: Asking identity...")
resp2 = send_message("What is my name?")
print(f"AI: {resp2.get('answer', 'ERROR')}")

if "Jakaria" in resp2.get('answer', ''):
    print("\n✅ LOCAL SUCCESS: AI Remembered (Stateless Mode)!")
else:
    print("\n❌ LOCAL FAILED: AI Forgot.")

print("--- TEST COMPLETED ---")
