import os
import django
import asyncio
import time
from dotenv import load_dotenv

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')

# Explicitly load .env
load_dotenv(os.path.join(os.getcwd(), '.env'))

django.setup()

from business.rag import aget_rag_answer_with_agent
from business.models import Business

async def simulate_user(user_id, business_id, query):
    print(f"User {user_id} sending query: '{query}' for Business ID: {business_id}...")
    start_time = time.time()
    try:
        response = await aget_rag_answer_with_agent(business_id, query)
        end_time = time.time()
        print(f"\n--- [User {user_id} Response ({end_time - start_time:.2f}s)] ---\n{response}\n")
    except Exception as e:
        print(f"User {user_id} error: {e}")

async def main():
    # Test queries
    queries = [
        (10, "Hello! Can you tell me what services you offer?"),
        (11, "Hi! I want to book an appointment for tomorrow at 2 PM. Is it available?"),
        (10, "What is your website URL?"),
    ]
    
    # Run them concurrently
    print("Starting concurrent agent requests...\n")
    tasks = []
    for i, (biz_id, query) in enumerate(queries):
        tasks.append(simulate_user(i+1, biz_id, query))
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
