import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def check_schema():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'core' AND table_name = 'bookings'
            """)
            columns = cur.fetchall()
            print("Schema for core.bookings:")
            for col in columns:
                print(f"- {col['column_name']} ({col['data_type']}, Nullable: {col['is_nullable']})")
    finally:
        conn.close()

if __name__ == "__main__":
    check_schema()
