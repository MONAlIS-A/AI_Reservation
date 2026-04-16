import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def check_embedding_tables():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        for table in ['business_embeddings', 'embeddings']:
            print(f"--- Columns for {table} ---")
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_schema = 'core' AND table_name = '{table}'")
            for c in cur.fetchall():
                print(c['column_name'])
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_embedding_tables()
