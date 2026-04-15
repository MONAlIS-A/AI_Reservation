import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def list_services():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, service_name, business_id, is_active FROM core.services")
            services = cur.fetchall()
            print("Found Services:")
            for s in services:
                print(f"- {s['service_name']} (ID: {s['id']}, Active: {s['is_active']})")
    finally:
        conn.close()

if __name__ == "__main__":
    list_services()
