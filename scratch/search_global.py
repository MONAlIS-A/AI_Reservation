import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def search_global():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Search all tables in all schemas for the key 'openai_api_key'
        cur.execute("""
            SELECT table_schema, table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            AND (column_name ILIKE '%key%' OR column_name ILIKE '%openai%')
        """)
        columns = cur.fetchall()
        
        for col in columns:
            s = col['table_schema']
            t = col['table_name']
            c = col['column_name']
            
            try:
                # Search for 'openai_api_key' in ANY column named 'key' or similar
                cur.execute(f"SELECT * FROM {s}.{t} WHERE {c} = 'openai_api_key'")
                res = cur.fetchone()
                if res:
                    print(f"FOUND in {s}.{t} row: {res}")
            except Exception:
                conn.rollback()
                continue

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_global()
