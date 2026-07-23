# Deployment Guide (EC2 + Nginx + Gunicorn)

## Gunicorn

Example systemd command:

```bash
gunicorn -w 4 -k gthread -b 127.0.0.1:8000 app:app
```

## Nginx

- Reverse proxy HTTPS traffic to Gunicorn.
- Allow POST to `/payments/webhook`.
- Preserve `X-Forwarded-For` for rate-limit accuracy.

## Security

- Force HTTPS with redirect.
- Keep `.env` out of source control.
- Restrict DB and Redis access to private network.

## Scaling notes

- Current in-memory limiter/replay guard is per-process.
- For multi-instance deployment, implement Redis-based rate-limit and replay stores.

## Docker readiness

- Use env-injected configuration.
- Keep stateless app containers.
- Mount logs to external target.
