import os
import django
import asyncio
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from business.rag import aget_rag_answer_with_agent

async def test_chat():
    # Try a known business id from the DB scan (e.g. 12007014-9d0c-4b0e-9150-2395242ba9fa)
    biz_id = '12007014-9d0c-4b0e-9150-2395242ba9fa'
    query = "Hello, what services are available?"
    
    print(f"Testing Chat for Business: {biz_id}...")
    try:
        answer = await aget_rag_answer_with_agent(biz_id, query)
        print(f"\nAI ANSWER:\n{answer}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
