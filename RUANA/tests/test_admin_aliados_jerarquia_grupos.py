from pathlib import Path


def test_admin_aliados_jerarquia_usa_grupo_red():
    """Control de Aliados: segundo nivel por grupo de red (grupo_id), no por estado."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    host = (root / "static" / "js" / "admin-panel-host.js").read_text(encoding="utf-8")
    # Lógica de jerarquía en host; copy/markup puede estar en HTML o módulos
    text = admin_html + "\n" + host
    assert "getClaveGrupoRed" in host
    assert "getNombreGrupoRed" in host
    assert "aliadosGrupoNombreSeleccionado" in host
    assert (
        "CP → Grupo de red → Tarjetas" in text
        or "grupos de red dentro del CP" in text.lower()
        or "Grupo de red" in text
    )
    # No debe clasificar el nivel 2 por buckets de estado
    assert "ordenGrupos = ['activos'" not in host
    assert "getGrupoAliado" not in host
