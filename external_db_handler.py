import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import uuid

import os

# Use Render's internal/external DB URL from environment variables, or fallback to the provided one
DB_URL = os.getenv("EXTERNAL_DATABASE_URL") or os.getenv("DATABASE_URL") or "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def get_connection():
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to connect: {e}")
        raise

def check_availability(service_name, target_time_str):
    try:
        # Convert target_time to datetime
        target_time = datetime.datetime.fromisoformat(target_time_str.replace('Z', '+00:00'))
    except Exception as e:
        return {"error": "Invalid time format. Please provide ISO format."}

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Find the service
            cur.execute("""
                SELECT id, business_id, duration_minutes 
                FROM core.services 
                WHERE service_name ILIKE %s AND is_active = true
                LIMIT 1
            """, (f"%{service_name}%",))
            service = cur.fetchone()
            
            if not service:
                return {"error": "Service not found or inactive."}
                
            service_id = service['id']
            business_id = service['business_id']
            duration = service['duration_minutes'] or 60 # default 60 min
            
            end_time = target_time + datetime.timedelta(minutes=duration)
            
            # Check for overlapping bookings
            cur.execute("""
                SELECT id FROM core.bookings 
                WHERE service_id = %s
                AND status NOT IN ('CANCELLED', 'CANCELED', 'FAILED', 'EXPIRED')
                AND (
                    (slot_start <= %s AND slot_end > %s) OR
                    (slot_start < %s AND slot_end >= %s) OR
                    (slot_start >= %s AND slot_end <= %s)
                )
            """, (service_id, target_time, target_time, end_time, end_time, target_time, end_time))
            
            overlapping = cur.fetchone()
            
            if overlapping:
                # Find next available slot on the same day 
                check_time = target_time
                for _ in range(16): # search up to 8 hours
                    check_time += datetime.timedelta(minutes=30)
                    check_end = check_time + datetime.timedelta(minutes=duration)
                    
                    cur.execute("""
                        SELECT id FROM core.bookings 
                        WHERE service_id = %s
                        AND status NOT IN ('CANCELLED', 'CANCELED', 'FAILED', 'EXPIRED')
                        AND (
                            (slot_start <= %s AND slot_end > %s) OR
                            (slot_start < %s AND slot_end >= %s) OR
                            (slot_start >= %s AND slot_end <= %s)
                        )
                    """, (service_id, check_time, check_time, check_end, check_end, check_time, check_end))
                    
                    if not cur.fetchone():
                        return {
                            "available": False, 
                            "message": f"The requested time slot is not available. The next available slot is at {check_time.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
                            "next_available_slot": check_time.isoformat()
                        }
                        
                return {"available": False, "message": "No slots available in the next 8 hours."}
            else:
                return {"available": True, "message": "The time slot is available."}
    finally:
        conn.close()

def create_booking_ext(service_name, target_time_str, customer_name, customer_phone, notes=""):
    try:
        # Convert target_time to datetime
        target_time = datetime.datetime.fromisoformat(target_time_str.replace('Z', '+00:00'))
    except Exception as e:
        return {"error": "Invalid time format. Please provide ISO format."}

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Find the service
            cur.execute("""
                SELECT id, business_id, duration_minutes 
                FROM core.services 
                WHERE service_name ILIKE %s AND is_active = true
                LIMIT 1
            """, (f"%{service_name}%",))
            service = cur.fetchone()
            
            if not service:
                return {"error": "Service not found."}
                
            service_id = service['id']
            business_id = service['business_id']
            duration = service['duration_minutes'] or 60 # default 60 min
            end_time = target_time + datetime.timedelta(minutes=duration)
            
            booking_id = str(uuid.uuid4())
            public_tracking_id = f"BK-{str(uuid.uuid4())[:6].upper()}"
            
            cur.execute("""
                INSERT INTO core.bookings (
                    id, business_id, service_id, public_tracking_id, 
                    status, slot_start, slot_end, 
                    customer_name, customer_phone, notes,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, 
                    'CONFIRMED', %s, %s, 
                    %s, %s, %s,
                    NOW(), NOW()
                ) RETURNING id;
            """, (
                booking_id, business_id, service_id, public_tracking_id,
                target_time, end_time,
                customer_name, customer_phone, notes
            ))
            
            conn.commit()
            return {"status": "success", "booking_id": booking_id, "tracking_id": public_tracking_id}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()
