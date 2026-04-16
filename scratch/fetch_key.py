import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def fetch_openai_key():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT key, value FROM core.platform_settings WHERE key = 'openai_api_key'")
        row = cur.fetchone()
        if row:
            print(f"FOUND: {row['key']} = {row['value'][:10]}...")
        else:
            print("NOT FOUND")
            # Print everything in platform_settings again to be 100% sure
            cur.execute("SELECT key FROM core.platform_settings")
            print(f"Current keys in table: {[r['key'] for r in cur.fetchall()]}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_openai_key()
