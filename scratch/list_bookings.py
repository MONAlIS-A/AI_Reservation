import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def list_bookings():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, service_id, slot_start, slot_end, status, customer_name FROM core.bookings ORDER BY slot_start DESC LIMIT 10")
            bookings = cur.fetchall()
            print("Recent Bookings:")
            for b in bookings:
                print(f"- {b['customer_name']} | {b['slot_start']} to {b['slot_end']} | Status: {b['status']}")
    finally:
        conn.close()

if __name__ == "__main__":
    list_bookings()
