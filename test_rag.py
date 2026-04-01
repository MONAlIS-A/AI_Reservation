import os, django, asyncio, json
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')
django.setup()

from business.rag import aget_global_rag_answer

async def test():
    try:
        ans = await aget_global_rag_answer("Hi, list all businesses.")
        print(f"--- ANSWER ---\n{ans}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
