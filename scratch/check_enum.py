import psycopg2

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def check_enum():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT enumlabel 
                FROM pg_enum 
                JOIN pg_type ON pg_enum.enumtypid = pg_type.oid 
                WHERE pg_type.typname = 'booking_status_enum'
            """)
            values = cur.fetchall()
            print("Valid values for core.booking_status_enum:")
            for v in values:
                print(f"- {v[0]}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_enum()
