PORTAL DE SEGUIMIENTO V9

Producción:
- PostgreSQL mediante DATABASE_URL.
- Sincronización OECE/INFO-8UIT en servidor.
- Alertas evaluadas sin navegador abierto.
- SMTP opcional.
- Caché persistente.
- Autenticación, sesiones HttpOnly, CSRF y rate limit.

Local:
- Ejecuta start.bat.
- Si DATABASE_URL está vacío usa SQLite.

Archivos:
- server.py
- index.html
- requirements.txt
- .env.example
- Dockerfile / Procfile
- DEPLOY.md
- migrate_sqlite_to_postgres.py

PAC permanece marcado como DEMO mientras no exista una integración oficial verificada.