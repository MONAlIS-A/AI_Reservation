import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def explore():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("--- Tables ---")
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')")
        tables = cur.fetchall()
        for t in tables:
            print(f"{t['table_schema']}.{t['table_name']}")
            
        print("\n--- Searching for API Keys ---")
        # Search for columns that might have api keys
        cur.execute("""
            SELECT table_schema, table_name, column_name 
            FROM information_schema.columns 
            WHERE column_name ILIKE '%api%' OR column_name ILIKE '%key%' OR column_name ILIKE '%openai%'
        """)
        cols = cur.fetchall()
        for c in cols:
            print(f"Candidate: {c['table_schema']}.{c['table_name']}.{c['column_name']}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    explore()
