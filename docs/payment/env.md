# Environment Variables

## Required

- SECRET_KEY
- DATABASE_DRIVER=mysql+pymysql
- MYSQL_HOST
- MYSQL_PORT
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD
- PAYSTACK_SECRET_KEY

## Recommended

- PAYSTACK_PUBLIC_KEY
- PAYSTACK_BASE_URL
- PAYSTACK_TIMEOUT_SECONDS
- JWT_SECRET_KEY
- REDIS_URL

## Tuya integration

- TUYA_BASE_URL
- TUYA_CLIENT_ID
- TUYA_CLIENT_SECRET
- TUYA_DEVICE_ID
- TUYA_TIMEOUT_SECONDS
- TUYA_MAX_RETRIES

## Operational guidance

- MySQL is the only supported runtime database. Configure only the `MYSQL_*` settings above.
- Never expose `PAYSTACK_SECRET_KEY` to frontend.
- Rotate secrets periodically.
- Keep prod and staging secrets separate.
