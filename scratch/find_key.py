import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def find_key():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Search all columns in 'core' schema
        cur.execute("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'core' 
            AND (column_name ILIKE '%secret%' 
                 OR column_name ILIKE '%api%' 
                 OR column_name ILIKE '%token%' 
                 OR column_name ILIKE '%openai%')
        """)
        results = cur.fetchall()
        print("--- Search Results ---")
        for r in results:
            print(f"{r['table_name']}.{r['column_name']}")
            
        # Also check and print ALL rows from platform_settings just in case
        print("\n--- core.platform_settings ALL ---")
        cur.execute("SELECT * FROM core.platform_settings")
        for row in cur.fetchall():
            print(row)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_key()
