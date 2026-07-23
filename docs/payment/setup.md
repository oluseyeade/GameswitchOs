# Setup Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Configure environment

Add Paystack values in `.env`:

- PAYSTACK_PUBLIC_KEY
- PAYSTACK_SECRET_KEY
- PAYSTACK_BASE_URL
- PAYSTACK_TIMEOUT_SECONDS

## 3. Verify the existing MySQL database

Run the read-only verification command:

```bash
python database/setup_mysql.py
```

The command checks the configured MySQL connection without creating databases, tables, or modifying existing data. Review and back up the existing schema before applying any migration.

## 4. Configure Paystack dashboard

Set callback URL:

- https://<your-domain>/payments/callback

Set webhook URL:

- https://<your-domain>/payments/webhook

## 5. Test flow

- Login
- Open `/payments/checkout`
- Initialize payment
- Complete payment in Paystack test mode
- Confirm webhook marks status as success
