import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import uuid
import time
import os

# --- Dynamic API Key Cache (TTL = 60 seconds) ---
_api_key_cache = {"key": None, "fetched_at": 0}
_API_KEY_TTL = 60  # seconds

# List of all possible DB URLs to try for the API key
DB_URL_OPTIONS = [
    os.getenv("EXTERNAL_DATABASE_URL"),
    os.getenv("DATABASE_URL"),
    "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"
]

def get_openai_api_key():
    """
    Dynamically fetches the OpenAI API key.
    Tries all available DB URLs in sequence until a valid key is found.
    Caches the result for 60 seconds.
    """
    global _api_key_cache
    now = time.time()

    # Return cached key if still fresh
    if _api_key_cache["key"] and (now - _api_key_cache["fetched_at"]) < _API_KEY_TTL:
        return _api_key_cache["key"]

    # Try each DB URL until we find the key
    for url in DB_URL_OPTIONS:
        if not url: continue
        try:
            conn = psycopg2.connect(url, connect_timeout=5)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT value FROM core.platform_settings WHERE key = 'openai_api_key' LIMIT 1")
                row = cur.fetchone()
                if row and row['value']:
                    _api_key_cache["key"] = row['value']
                    _api_key_cache["fetched_at"] = now
                    print(f"[API KEY] Successfully fetched key from DB: {url[:30]}...")
                    conn.close()
                    return _api_key_cache["key"]
            conn.close()
        except Exception as e:
            # Silently try next URL
            continue

    # Fallback to local environment variable (last resort)
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key

    print("[API KEY ERROR] Could not find OpenAI API key in any database or environment!")
    return None

# Primary URL for bookings/services (External has highest priority)
EXTERNAL_FALLBACK_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"
DB_URL = os.getenv("EXTERNAL_DATABASE_URL") or EXTERNAL_FALLBACK_URL

# Note: We intentionally ignore Render's internal DATABASE_URL for bookings 
# because it usually points to an empty DB. 

def get_connection():
    """
    Connects to the database. Always tries the External/Fallback DB first 
    to ensure we have access to 'core' schema and bookings data.
    """
    try:
        # Try primary DB_URL
        conn = psycopg2.connect(DB_URL, connect_timeout=5)
        # Verify if 'core' schema exists (quick check)
        with conn.cursor() as cur:
            cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'core'")
            if cur.fetchone():
                return conn
        conn.close()
    except Exception:
        pass

    # If primary fails, try Render's internal DATABASE_URL as last resort
    int_url = os.getenv("DATABASE_URL")
    if int_url:
        try:
            return psycopg2.connect(int_url, connect_timeout=5)
        except Exception:
            pass
            
    # Final fallback to hardcoded external
    return psycopg2.connect(EXTERNAL_FALLBACK_URL)

def get_business_data_for_rag():
    """
    Fetches all businesses and their services to build the RAG knowledge base.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Fetch businesses
            cur.execute("SELECT id, business_name, description FROM core.businesses WHERE is_active = true")
            businesses = cur.fetchall()
            
            # Fetch services per business
            for biz in businesses:
                cur.execute("""
                    SELECT service_name, description, base_price, currency, duration_minutes 
                    FROM core.services 
                    WHERE business_id = %s AND is_active = true
                """, (biz['id'],))
                biz['services'] = cur.fetchall()
            
            return businesses
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch RAG data: {e}")
        return []
    finally:
        conn.close()

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
