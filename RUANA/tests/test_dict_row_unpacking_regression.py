"""Regresión: filas dict_row (CompatRow) no deben desempaquetarse por tupla.

Iterar un CompatRow devuelve las CLAVES; `for (gid, _) in filas` daba gid="id"
y Postgres fallaba con: invalid input syntax for type bigint: "id".
"""
import inspect

from core.postgres_compat import CompatRow
from core.services import admin_service, evaluacion_service


def test_compatrow_unpack_devuelve_claves_y_indice_devuelve_valores():
    row = CompatRow({"id": 7, "codigo_postal": "28001"}, ["id", "codigo_postal"])
    a, _ = row
    assert a == "id"  # por eso no se debe desempaquetar
    assert row[0] == 7 and row[1] == "28001"


def test_health_metrics_no_desempaqueta_filas_de_grupos():
    src = inspect.getsource(admin_service.obtener_health_metrics_admin)
    assert "for (gid, _) in" not in src
    assert "gid = g[0]" in src


def test_admin_service_no_desempaqueta_top_invitadores():
    src = inspect.getsource(admin_service)
    assert "for (codigo_inv, total) in rows" not in src
    assert "for codigo_inv, total in rows" not in src


def test_motor_periodico_select_con_alias_codigo():
    src = inspect.getsource(evaluacion_service.ejecutar_motor_periodico)
    assert "AS codigo FROM aliados" in src
