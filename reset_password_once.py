import os
import psycopg

email=os.getenv("RESET_USER_EMAIL","").strip().lower()
password_hash=os.getenv("RESET_USER_PASSWORD_HASH","").strip()
db_url=os.getenv("DATABASE_URL","").strip()

if email and password_hash and db_url:
    with psycopg.connect(db_url) as c:
        row=c.execute("SELECT id FROM users WHERE lower(email)=lower(%s)",(email,)).fetchone()
        if row:
            uid=row[0]
            c.execute("UPDATE users SET password_hash=%s WHERE id=%s",(password_hash,uid))
            c.execute("DELETE FROM sessions WHERE user_id=%s",(uid,))
            c.commit()
            print("[reset-password] ok", flush=True)
        else:
            print("[reset-password] user-not-found", flush=True)
