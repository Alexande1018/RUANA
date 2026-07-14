FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV RUANA_ADMIN_SESSION_EXPIRES=3600
ENV RUANA_ALIADO_SESSION_EXPIRES=3600

WORKDIR /app

COPY RUANA/web/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY RUANA/ /app/

# Verificar que la imagen incluye el código desplegado (evita capas/cachés obsoletas).
RUN grep -q "input-foto-perfil" /app/web/aliado.html && \
    grep -q "ruana-brand-mark" /app/web/index.html

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 0 web.app:app"]
