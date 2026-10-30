"""Hooks de gunicorn para RUANA (se carga solo: gunicorn lee ./gunicorn.conf.py).

Solo añade hooks de apagado; los parámetros (workers, threads, timeout…) siguen
viniendo de la línea de comandos del Dockerfile.
"""


def worker_exit(server, worker):  # noqa: ARG001 - firma de gunicorn
    """Cierra el pool de Postgres del worker al apagarse (SIGTERM de Cloud Run)."""
    try:
        from core.postgres_compat import close_pool

        close_pool()
    except Exception:
        pass
