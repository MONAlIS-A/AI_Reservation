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
    business_id = 1 
    
    # Query 1: Only Inquiry
    query_inquiry = "Is Eau de Parfum - Floral Scent available?"
    print(f"Testing Inquiry: {query_inquiry}")
    answer_inquiry = await aget_rag_answer_with_agent(business_id, query_inquiry, chat_history=[])
    print(f"RES 1: {answer_inquiry}\n")
    
    # Query 2: Only Booking
    query_booking = "I want to book Eau de Parfum - Floral Scent."
    print(f"Testing Booking: {query_booking}")
    answer_booking = await aget_rag_answer_with_agent(business_id, query_booking, chat_history=[])
    print(f"RES 2: {answer_booking}")

if __name__ == "__main__":
    asyncio.run(run_test())
