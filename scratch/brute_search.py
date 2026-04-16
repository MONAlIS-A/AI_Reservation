import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def brute_force_search():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all text columns in 'core' schema
        cur.execute("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'core' 
            AND data_type IN ('text', 'character varying')
        """)
        columns = cur.fetchall()
        
        print(f"Searching {len(columns)} columns...")
        
        for col in columns:
            t = col['table_name']
            c = col['column_name']
            
            # Use LIKE 'sk-%' to find OpenAI keys
            query = f"SELECT {c} FROM core.{t} WHERE {c} LIKE 'sk-%%' LIMIT 1"
            try:
                cur.execute(query)
                res = cur.fetchone()
                if res:
                    print(f"FOUND in {t}.{c}: {res[c]}")
            except Exception:
                # Some columns might not be searchable this way or throw errors (like id)
                conn.rollback()
                continue

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    brute_force_search()
