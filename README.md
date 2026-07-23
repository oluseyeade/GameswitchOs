# GameSwitchOS (Two-Branch Working System)

This project now runs as a complete two-branch workflow:

1. Welcome page
2. User register/login
3. Game selection
4. Payment checkout (successful or declined simulation)
5. Successful payment starts timed gaming session
6. Timer ticks via AJAX + JSON
7. Smart switch off at timer end
8. Branch dashboards for Admin 1, Admin 2, and Superadmin

## Tech Stack

- Flask (backend + routing + API)
- AJAX (`fetch`) + JSON for timer API
- Bootstrap 5 + Font Awesome (CDN)
- External CSS and JavaScript
- MySQL 8+ with PyMySQL
- Flask-SQLAlchemy and Flask-Migrate

## Project Structure

- `app.py`: Flask app, auth, roles, branch-aware APIs, timer logic, smart switch placeholder
- `templates/`: All HTML pages (`admin1.html`, `admin2.html`, `superadmin.html`, etc.)
- `static/css/styles.css`: External styling
- `static/js/app.js`: Timer settings + AJAX logic
- `database/schema.sql`: MySQL schema
- `.env.example`: Environment config template

## Seeded Accounts

These are are the login details of the admin and superadmin::

- Admin 1: `admin1@gameswitch.local` / `Admin123!`
- Admin 2: `admin2@gameswitch.local` / `Admin123!`
- Superadmin: `superadmin@gameswitch.local` / `Admin123!`

## Tuya Smart Switch Workflow

1. User chooses branch/game/duration at checkout.
2. Frontend sends `POST /api/user/session/start` (or `POST /api/user/payment/checkout`).
3. Backend records payment in selected branch.
4. If successful: backend discovers device switch capabilities and turns selected station ON.
5. Frontend sends `POST /api/user/session/<id>/tick` every second.
6. At zero: backend ends session and turns selected station OFF.
7. Frontend subscribes to `GET /api/user/session/events` (SSE) for live updates.
8. Device state can be refreshed from `GET /api/user/device/status`.
7. Branch and superadmin dashboards read live summary APIs.

## Paystack Payment Module

New production-oriented payment domain is available under `app/payment` and `app/models`.

Primary endpoints:

- `POST /payments/initialize`
- `GET /payments/callback`
- `POST /payments/webhook`
- `GET /payments/history`
- `GET /payments/status/<reference>`
- `GET /payments/invoice/<reference>`

Frontend entry points:

- `GET /payments/checkout`
- `GET /payments/dashboard`

Security highlights:

- Webhook signature verification (`X-Paystack-Signature`)
- Callback data is not treated as source of truth
- Verification API amount/currency checks
- Replay guard for webhook events
- Basic rate limiting for initialize/status polling

## Setup

1. Create virtual environment and install requirements:

```bash
pip install -r requirements.txt
```

2. Copy environment file:

```bash
copy .env.example .env
```

3. Update `.env` with the existing MySQL target:

- `DATABASE_DRIVER=mysql+pymysql`
- `MYSQL_HOST=127.0.0.1`
- `MYSQL_PORT=3306`
- `MYSQL_DATABASE=gameswitchos_demo`
- `MYSQL_USER=root`
- `MYSQL_PASSWORD=...`

4. Verify the existing MySQL database before starting the app:

```bash
python database/setup_mysql.py
```

This performs a read-only connection check by default. It does not create databases, tables, or modify data. Use `python database/setup_mysql.py --provision` only for an explicitly approved new environment.

5. Start app:

```bash
python app.py
```

6. Open browser:

- `http://127.0.0.1:5000/welcome`

## Notes

- Tuya credentials are backend-only environment variables and are never exposed in templates or browser JavaScript.
- Use reviewed Flask-Migrate or SQL migration scripts to change an existing database; application startup never creates or alters tables.
- Admin pages now load live JSON branch metrics and activity data.

Thank  you for taking your time to read this , note that this is the mvpv1 ... as time goes on  ,we will  improve on the functionality , be able to add some intresting  new features . 
