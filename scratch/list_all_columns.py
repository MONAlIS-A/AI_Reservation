import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://reservation_user:VYKmw4eCXKoKb7UzujL7JjRs8bekMS4m@dpg-d7ct9p0sfn5c73fvdbdg-a.oregon-postgres.render.com/reservation_dev_mffn"

def list_all():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'core'")
        results = cur.fetchall()
        
        tables = {}
        for r in results:
            t = r['table_name']
            c = r['column_name']
            if t not in tables:
                tables[t] = []
            tables[t].append(c)
            
        for t, cols in tables.items():
            print(f"Table: {t}")
            print(f"  Columns: {', '.join(cols)}")
            print("-" * 20)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_all()
