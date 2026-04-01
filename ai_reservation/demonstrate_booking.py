import os
import django
import asyncio
import sys
from datetime import datetime
from dotenv import load_dotenv
from asgiref.sync import sync_to_async

# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')
load_dotenv('.env')
django.setup()

from business.rag import aget_rag_answer_with_agent
from business.models import Appointment, Business

async def test_appointment_flow():
    # 1. Choose a business
    biz = await sync_to_async(lambda: Business.objects.filter(id=10).first())()
    if not biz:
        print("Business not found.")
        return
    
    # 2. Clear existing appointments for this test date
    test_date = "2024-12-01"
    await sync_to_async(lambda: Appointment.objects.filter(business=biz, start_time__date=test_date).delete())()
    print(f"\n--- Testing Appointment Flow for '{biz.name}' on {test_date} ---")

    # Scenario A: First user books a slot
    query1 = f"Hi! I am Rahim. I want to book an appointment for {test_date} at 10:00 AM."
    print(f"\nUser 1 (Rahim): '{query1}'")
    resp1 = await aget_rag_answer_with_agent(biz.id, query1)
    print(f"Agent Response 1:\n{resp1}")

    # Verify in DB
    count = await sync_to_async(lambda: Appointment.objects.filter(business=biz, start_time__date=test_date).count())()
    print(f"Appointments in DB: {count}")

    # Scenario B: Second user tries to book the SAME slot
    query2 = f"Hello! I am Karim. Can I also book for {test_date} at 10:00 AM?"
    print(f"\nUser 2 (Karim): '{query2}'")
    resp2 = await aget_rag_answer_with_agent(biz.id, query2)
    print(f"Agent Response 2:\n{resp2}")

    # Scenario C: User 2 asks for another time
    query3 = f"Oh no! Then book me for 12:30 PM on the same day."
    print(f"\nUser 2 (Karim): '{query3}'")
    resp3 = await aget_rag_answer_with_agent(biz.id, query3)
    print(f"Agent Response 3:\n{resp3}")

    # Finale: Show all bookings
    print("\n--- Final Bookings List in Database ---")
    def get_all():
        return list(Appointment.objects.filter(business=biz, start_time__date=test_date).order_by('start_time'))
    
    all_appts = await sync_to_async(get_all)()
    for a in all_appts:
        print(f"Confirmed Slot: {a.customer_name} at {a.start_time.strftime('%H:%M')} (Business: {biz.name})")

if __name__ == "__main__":
    asyncio.run(test_appointment_flow())
