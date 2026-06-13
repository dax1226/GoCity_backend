import sqlite3

conn = sqlite3.connect('gocity.db')
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE users ADD COLUMN profile_image VARCHAR")
    print("Added profile_image to users")
except Exception as e:
    print("users:", e)

try:
    cursor.execute("ALTER TABLE drivers ADD COLUMN profile_image VARCHAR")
    print("Added profile_image to drivers")
except Exception as e:
    print("drivers:", e)

conn.commit()
conn.close()
print("Done")
