# Portal de Seguimiento V9 — despliegue

## 1. Local, sin dependencias externas
Ejecuta `start.bat`. Si `DATABASE_URL` está vacío, la aplicación usa `data/portal.db` (SQLite).

## 2. PostgreSQL / Supabase
1. Crea una base PostgreSQL.
2. Copia `.env.example` a `.env` o configura las variables en tu hosting.
3. Define `DATABASE_URL` con la cadena de conexión de PostgreSQL. Para Supabase puede usarse la cadena PostgreSQL/Pooler que entrega el proyecto; conserva `sslmode=require` cuando corresponda.
4. Instala dependencias: `pip install -r requirements.txt`.
5. Ejecuta `python server.py`.

La V9 crea automáticamente las tablas necesarias. Con `DATABASE_URL` presente, PostgreSQL pasa a ser la fuente de verdad para usuarios, estado, caché OECE/INFO-8UIT, bloqueos de tareas y registro de correos.

## 3. Migrar datos existentes desde SQLite
Con `DATABASE_URL` configurado:

`python migrate_sqlite_to_postgres.py`

Se migran usuarios, hashes de contraseña, favoritos/alertas/búsquedas/preferencias y caché V9. Por seguridad no se migran sesiones activas.

## 4. Sincronización sin PC encendida
En hosting deja:
- `BACKGROUND_SYNC_ENABLED=1`
- `BACKGROUND_SYNC_INTERVAL=900`

El proceso del servidor actualiza OECE e INFO-8UIT y evalúa alertas cada 15 minutos. Un bloqueo en la base evita que dos instancias ejecuten el mismo ciclo simultáneamente.

## 5. Alertas por correo
Configura:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_TLS=1` para STARTTLS, o `SMTP_SSL=1` para SSL directo.

## 6. Docker
`docker compose up --build`

## 7. Producción
Configura:
- `HOST=0.0.0.0`
- `SESSION_SECURE=1`
- `TRUST_PROXY=1`
- `DATABASE_URL=...`
- `BACKGROUND_SYNC_ENABLED=1`

No publiques secretos dentro del repositorio.