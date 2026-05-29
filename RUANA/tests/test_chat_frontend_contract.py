from pathlib import Path


def test_chat_modal_surfaces_remaining_time_from_api():
    text = (Path(__file__).resolve().parents[1] / "web" / "aliado.html").read_text(
        encoding="utf-8"
    )

    assert "chat_horas_restantes" in text
    assert "this.chatHorasRestantes" in text
    assert "Disponible menos de 1 h" in text
