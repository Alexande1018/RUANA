"""Alinea score-estado.js con score_service.score_a_estado."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from core.services.score_service import score_a_estado

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js" / "score-estado.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_score_estado_js_coincide_con_motor_python():
    samples = [500, 350, 349, 200, 199, 50, 49, 15, 14, 0]
    script = """
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.env.SCORE_ESTADO_JS, 'utf8');
const ctx = {};
ctx.window = ctx;
ctx.globalThis = ctx;
vm.runInNewContext(code, ctx);
const S = ctx.RuanaScoreEstado;
const samples = JSON.parse(process.env.SCORE_SAMPLES);
const buckets = S.bucketsFromAliados([
  {score: 400}, {score: 50}, {score: 50}, {score: 20}, {score: 10}, {score: 220}
]);
process.stdout.write(JSON.stringify({
  estados: samples.map((s) => S.scoreAEstado(s)),
  estableDefault: S.scoreAEstado(50),
  buckets: buckets
}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SCORE_ESTADO_JS": str(JS),
            "SCORE_SAMPLES": json.dumps(samples),
        },
    )
    payload = json.loads(result.stdout)
    assert payload["estados"] == [score_a_estado(s) for s in samples]
    assert payload["estableDefault"] == "ESTABLE"
    assert payload["buckets"] == {
        "elite": 1,
        "destacado": 1,
        "estable": 2,
        "en_riesgo": 1,
        "competencia": 1,
    }
