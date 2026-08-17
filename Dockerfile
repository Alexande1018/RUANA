FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV RUANA_ADMIN_SESSION_EXPIRES=3600
ENV RUANA_ALIADO_SESSION_EXPIRES=3600

WORKDIR /app

COPY RUANA/web/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY RUANA/ /app/

EXPOSE 8080

CMD ["sh", "-c", "if [ -z \"${WEB_CONCURRENCY}\" ]; then cpus=$(nproc 2>/dev/null || true); if [ -n \"$cpus\" ] && [ \"$cpus\" -gt 0 ] 2>/dev/null; then WEB_CONCURRENCY=$((2 * cpus + 1)); else WEB_CONCURRENCY=2; fi; fi; exec gunicorn --bind :${PORT:-8080} --workers ${WEB_CONCURRENCY} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-30} --graceful-timeout 30 --keep-alive 5 web.app:app"]
