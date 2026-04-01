import os
import django
import asyncio
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')
django.setup()

from business.rag import aget_rag_answer_with_agent

async def test():
    try:
        print("Starting agent...")
        result = await aget_rag_answer_with_agent(10, "I want to book appointment today")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error caught: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
