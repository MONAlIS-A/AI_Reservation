import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def list_all_v2():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'core'
            ORDER BY table_name, ordinal_position
        """)
        results = cur.fetchall()
        
        current_table = ""
        for r in results:
            if r['table_name'] != current_table:
                current_table = r['table_name']
                print(f"\n--- {current_table} ---")
            print(f"  {r['column_name']}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_all_v2()
