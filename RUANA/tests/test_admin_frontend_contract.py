from pathlib import Path


def test_admin_fetch_response_destructuring_matches_fetch_order():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "fetch('/api/admin/pagos-en-revision', fetchOpts)" in text
    assert (
        "conflictosData, pagosApoyoData, pagosEnRevisionData, solicitudesData"
        in text
    )


def test_readonly_admin_disables_all_write_actions():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "document.querySelectorAll('.btn-admin-action[data-action]')" in text
    assert "data-action=\"crear-campana-invitacion\"" in text
