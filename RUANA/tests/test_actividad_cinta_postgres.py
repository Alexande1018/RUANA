"""Compatibilidad Postgres de la cinta de actividad RUANA."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.postgres_compat import PostgresCompatCursor, _translate_sql


def test_translate_sql_strftime_anio_mes():
    sql = "SELECT COUNT(*) FROM t WHERE strftime('%Y-%m', creado_en) = ?"
    translated = _translate_sql(sql)
    assert "to_char" in translated
    assert "YYYY-MM" in translated
    assert "strftime" not in translated.lower()


def test_translate_sql_datetime_ventana_30_dias():
    sql = "SELECT 1 WHERE created_at >= datetime('now', '-30 days')"
    translated = _translate_sql(sql)
    assert "now()" in translated
    assert "interval '30 days'" in translated


def test_actividad_repo_contar_aliados_sql_sin_placeholders_ventana():
    from core.repositories.actividad_repo import ActividadRepo

    repo = ActividadRepo()
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = (2,)

    repo.contar_aliados_activos_grupo(cur, 1)

    sql = inner.execute.call_args[0][0]
    assert "grupo_id" in sql
    assert "datetime('now', ?)" not in sql


def test_actividad_repo_listar_solicitudes_usa_datetime_literal():
    from core.repositories.actividad_repo import ActividadRepo

    repo = ActividadRepo()
    cur, inner = _compat_cursor()
    inner.fetchall.return_value = []

    repo.listar_solicitudes_nuevas_grupo(cur, 1, "X001")

    sql = inner.execute.call_args[0][0]
    assert "created_at >=" in sql
    assert "now()" in sql
    assert "interval '30 days'" in sql


def _compat_cursor():
    conn = MagicMock()
    conn._conn = MagicMock()
    inner = MagicMock()
    conn._conn.cursor.return_value = inner
    return PostgresCompatCursor(conn), inner
