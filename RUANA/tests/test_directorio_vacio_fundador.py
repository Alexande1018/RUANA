"""Directorio vacío: mensaje de fundador e invitar; la búsqueda no invita."""
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_directorio_vacio_reutiliza_el_mensaje_de_fundador():
    inicio = (ROOT / "web/static/js/aliado-inicio-module.js").read_text(encoding="utf-8")
    directorio = (ROOT / "web/static/js/aliado-directorio-module.js").read_text(encoding="utf-8")
    mensaje = (
        "Todavía no hay más profesionales en tu grupo. Invita a 2 o 3 profesionales "
        "de confianza de otros oficios: cuantos más seamos, más encargos nos podremos pasar."
    )
    assert mensaje in inicio
    assert mensaje in directorio
    assert "Eres el primero de tu zona" in directorio
    assert "Ampliar mi red" in directorio
    assert "setAttribute('data-action', 'invitar-aliado')" in directorio
    assert "generarCodigoInvitacionPerfil" in directorio
    assert "No hay profesionales disponibles en este momento" not in directorio
    assert "Ningún profesional de tu grupo coincide con la búsqueda." in directorio

    script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/static/js/aliado-directorio-module.js', 'utf8');
const context = {};
vm.createContext(context);
vm.runInContext(code, context);
const estado = context.RuanaAliadoModules.directorio.estadoDirectorioVacio;
process.stdout.write(JSON.stringify({
  vacio: estado(''),
  espacios: estado('   '),
  busqueda: estado('fontanero'),
}));
"""
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["vacio"]["invitar"] is True
    assert data["vacio"]["titulo"] == "Eres el primero de tu zona"
    assert data["vacio"]["mensaje"] == mensaje
    assert data["espacios"]["invitar"] is True
    assert data["busqueda"]["invitar"] is False
    assert data["busqueda"]["mensaje"] == "Ningún profesional de tu grupo coincide con la búsqueda."
    assert data["busqueda"]["titulo"] == ""


def test_este_cambio_no_reescribe_los_puntos_de_invitar():
    """Alexander decide después los textos de +3/+5. Este PR no los toca."""
    grupo = (ROOT / "web/static/js/aliado-grupo-module.js").read_text(encoding="utf-8")
    modal = (ROOT / "web/static/js/aliado-invitaciones-module.js").read_text(encoding="utf-8")
    html = (ROOT / "web/aliado.html").read_text(encoding="utf-8")
    assert (
        "recibirás +5 puntos de Score. Puedes conseguir hasta 50 puntos."
    ) in grupo
    assert "Con este código son +3 cuando se registra." in modal
    assert "Con este código son +5 cuando se registra (hasta " in modal
    assert "Con este código son +3 cuando se registra." in html
