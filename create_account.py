"""Run this once to create the test account for Ligtas app testing."""
from werkzeug.security import generate_password_hash
import sqlite3

username = 'testuser'
password = 'test1234'
email = 'test@ligtas.app'

hashed = generate_password_hash(password)
conn = sqlite3.connect('users.db')
c = conn.cursor()

# Remove existing test account if any and recreate
c.execute('DELETE FROM users WHERE username=?', (username,))
c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))

# Ensure user_profile table exists
c.execute('''CREATE TABLE IF NOT EXISTS user_profile (
    username TEXT PRIMARY KEY,
    display_name TEXT,
    email TEXT,
    joined_at TEXT
)''')
c.execute('DELETE FROM user_profile WHERE username=?', (username,))
c.execute(
    'INSERT INTO user_profile (username, display_name, email, joined_at) VALUES (?,?,?,datetime("now"))',
    (username, 'Test User', email)
)

# Ensure sos_contacts table exists
c.execute('''CREATE TABLE IF NOT EXISTS sos_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    name TEXT,
    contact_type TEXT,
    contact_value TEXT
)''')

conn.commit()
conn.close()
print(f'Account created successfully!')
print(f'  Username : {username}')
print(f'  Password : {password}')
print(f'  Email    : {email}')
