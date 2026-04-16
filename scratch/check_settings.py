import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def check_settings():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("--- core.platform_settings ---")
        cur.execute("SELECT * FROM core.platform_settings")
        for row in cur.fetchall():
            print(row)
            
        print("\n--- core.business_ai_settings ---")
        cur.execute("SELECT * FROM core.business_ai_settings LIMIT 5")
        for row in cur.fetchall():
            print(row)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_settings()
