class msql:
    def __init__(self):
        self.DB_HOST = "localhost"
        self.DB_USER = "root"
        self.DB_PASSWORD = ""
        self.DB_NAME = "saferoute_db"

    def get_db_connection(self):
        try:
            import mysql.connector
        except ImportError:
            pass
            
        import mysql.connector # Ensure module is available
        conn = mysql.connector.connect(
            host=self.DB_HOST, user=self.DB_USER, password=self.DB_PASSWORD, database=self.DB_NAME)
        return conn, conn.cursor()

    def execute_query(self, cursor, query, params=None):
        query = query.replace('?', '%s')
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

    def init_db(self):
        import mysql.connector
        try:
            temp_conn = mysql.connector.connect(host=self.DB_HOST, user=self.DB_USER, password=self.DB_PASSWORD)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.DB_NAME}")
            temp_cursor.close()
            temp_conn.close()

            conn, c = self.get_db_connection()
            c.execute('CREATE TABLE IF NOT EXISTS users (username VARCHAR(255) PRIMARY KEY, password VARCHAR(255))')
            conn.commit()
            c.close()
            conn.close()
            print("🟢 Using MySQL Database")
        except Exception as e:
            print(f"🔴 MySQL Error: {e}")

class nsql:
    def __init__(self):
        self.SQLITE_DB = "users.db"

    def get_db_connection(self):
        import sqlite3
        conn = sqlite3.connect(self.SQLITE_DB)
        return conn, conn.cursor()

    def execute_query(self, cursor, query, params=None):
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

    def init_db(self):
        conn, c = self.get_db_connection()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
        conn.commit()
        c.close()
        conn.close()
        print("🟢 Using SQLite Database")