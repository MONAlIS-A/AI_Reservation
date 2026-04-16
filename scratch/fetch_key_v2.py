import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def fetch_openai_key_v2():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT key, value FROM core.platform_settings WHERE key ILIKE '%openai%'")
        rows = cur.fetchall()
        if rows:
            for row in rows:
                print(f"FOUND: {row['key']} = {row['value'][:10]}...")
        else:
            print("NOT FOUND AT ALL")
            cur.execute("SELECT * FROM core.platform_settings")
            all_rows = cur.fetchall()
            print(f"Total rows in platform_settings: {len(all_rows)}")
            for r in all_rows:
                print(f"Key: '{r['key']}'")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_openai_key_v2()
