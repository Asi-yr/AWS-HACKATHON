import sqlite3

SQLITE_DB = "users.db"
def get_db_connection():
    conn = sqlite3.connect(SQLITE_DB)
    return conn, conn.cursor()

def execute_query(cursor, query, params=None):
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

def init_db():
    conn, c = get_db_connection()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                    (username TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    c.close()
    conn.close()
    print("🟢 Using SQLite Database")