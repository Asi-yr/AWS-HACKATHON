try: # Try to import MySQL, but don't crash if it's not installed yet
    import mysql.connector
except ImportError:
    pass

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "saferoute_db"

def get_db_connection():
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    return conn, conn.cursor()

def execute_query(cursor, query, params=None):
    query = query.replace('?', '%s')

def init_db():
    try:
        temp_conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        temp_cursor = temp_conn.cursor()
        temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        temp_cursor.close()
        temp_conn.close()
        conn, c = get_db_connection()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                    (username VARCHAR(255) PRIMARY KEY, password VARCHAR(255))''')
        conn.commit()
        c.close()
        conn.close()
        print("🟢 Using MySQL Database")
    except Exception as e:
        print(f"🔴 MySQL Error: {e}")