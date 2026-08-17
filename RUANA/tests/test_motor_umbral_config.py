"""Umbrales del motor de evaluación desde ruana_reglas_v1.json."""

from engines.motor_evaluacion import MotorEvaluacion


def test_motor_umbral_meses_sin_trabajo_desde_config():
    metrics = {
        "tasa_respuesta": 0.90,
        "tasa_confirmacion": 0.90,
        "meses_sin_trabajo": 8,
    }
    motor_relajado = MotorEvaluacion(
        config={
            "motor_umbral_tasa_respuesta": 0.70,
            "motor_umbral_tasa_confirmacion": 0.80,
            "motor_umbral_meses_sin_trabajo": 12,
        }
    )
    assert motor_relajado._evaluar_aliado("90001", metrics)["estado"] == "verde"

    motor_estricto = MotorEvaluacion(
        config={
            "motor_umbral_tasa_respuesta": 0.70,
            "motor_umbral_tasa_confirmacion": 0.80,
            "motor_umbral_meses_sin_trabajo": 6,
        }
    )
    assert motor_estricto._evaluar_aliado("90001", metrics)["estado"] == "amarillo"
