import os
import django
import asyncio
import sys

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)
django.setup()

from business.rag import aget_rag_answer_with_agent

async def run_test():
    business_id = 1 # rooftop
    query = "Eau de Parfum - Floral Scent is available."
    print(f"Testing Exact Query: {query}")
    
    answer = await aget_rag_answer_with_agent(business_id, query, chat_history=[])
    
    with open('tmp/test_parfum_exact.txt', 'w', encoding='utf-8') as f:
        f.write(answer)
    print("Done. Saved to tmp/test_parfum_exact.txt")

if __name__ == "__main__":
    asyncio.run(run_test())
