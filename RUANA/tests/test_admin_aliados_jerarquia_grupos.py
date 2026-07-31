from pathlib import Path


def test_admin_aliados_jerarquia_usa_grupo_red():
    """Control de Aliados: segundo nivel por grupo de red (grupo_id), no por estado."""
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert "getClaveGrupoRed" in text
    assert "getNombreGrupoRed" in text
    assert "aliadosGrupoNombreSeleccionado" in text
    assert "CP → Grupo de red → Tarjetas" in text or "grupos de red dentro del CP" in text.lower() or "Grupo de red" in text
    # No debe clasificar el nivel 2 por buckets de estado
    assert "ordenGrupos = ['activos'" not in text
    assert "getGrupoAliado" not in text
