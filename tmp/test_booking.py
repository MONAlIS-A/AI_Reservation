import os
import django
import asyncio
import json

import sys

# Set up Django environment
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from business.rag import aget_rag_answer_with_agent

async def run_test():
    business_id = 1
    history = [
        {"role": "user", "content": "Hi, I am Jakaria. My email is jakaria@example.com"},
        {"role": "assistant", "content": "Hello Jakaria! How can I help you at rooftop today?"}
    ]
    query = "I would like to book a Dinner for tomorrow at 7:00 PM."
    
    print(f"--- Sending Query ---\nUser: {query}\n")
    
    answer = await aget_rag_answer_with_agent(business_id, query, chat_history=history)
    
    with open('tmp/test_result.txt', 'w', encoding='utf-8') as f:
        f.write(answer)
    print("Test finished. Result saved to tmp/test_result.txt")

if __name__ == "__main__":
    asyncio.run(run_test())
