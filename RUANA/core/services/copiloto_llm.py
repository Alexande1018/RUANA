"""Cliente del modelo de lenguaje del Copiloto RUANA.

Diseño deliberado:
  · Solo stdlib (urllib). Cero dependencias nuevas.
  · Apagado por defecto (`RUANA_AI_ENABLED`). Sin clave, el copiloto funciona
    igual en modo determinista.
  · Compatible con cualquier API tipo OpenAI (DeepSeek, OpenAI, Groq,
    OpenRouter, Ollama, LM Studio) y con la API de mensajes de Anthropic.
  · Nunca lanza: si falla o tarda, devuelve None y el servicio cae al motor
    determinista. El copiloto no puede tumbar el panel.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFECTOS = {
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "ollama": ("http://127.0.0.1:11434/v1", "llama3.1"),
    "openai_compatible": ("", ""),
    "anthropic": ("https://api.anthropic.com/v1", "claude-3-5-haiku-latest"),
}


def _env(nombre: str, defecto: str = "") -> str:
    return (os.environ.get(nombre) or defecto).strip()


def _bool_env(nombre: str, defecto: bool = False) -> bool:
    crudo = _env(nombre)
    if not crudo:
        return defecto
    return crudo.lower() in {"1", "true", "yes", "si", "sí", "on"}


def provider() -> str:
    return (_env("RUANA_AI_PROVIDER", "deepseek") or "deepseek").lower()


def modelo() -> str:
    defecto = _DEFECTOS.get(provider(), ("", ""))[1]
    return _env("RUANA_AI_MODEL", defecto)


def base_url() -> str:
    defecto = _DEFECTOS.get(provider(), ("", ""))[0]
    return _env("RUANA_AI_BASE_URL", defecto).rstrip("/")


def api_key() -> str:
    return _env("RUANA_AI_API_KEY")


def disponible() -> bool:
    """El LLM se usa solo si está activado, hay clave y hay destino."""
    if not _bool_env("RUANA_AI_ENABLED", False):
        return False
    if not api_key():
        return False
    if provider() == "openai_compatible" and not base_url():
        return False
    return bool(base_url()) and bool(modelo())


def _timeout() -> float:
    try:
        return max(2.0, min(30.0, float(_env("RUANA_AI_TIMEOUT", "8") or 8)))
    except ValueError:
        return 8.0


def _max_tokens() -> int:
    try:
        return max(120, min(2000, int(_env("RUANA_AI_MAX_TOKENS", "600") or 600)))
    except ValueError:
        return 600


def _temperatura() -> float:
    try:
        return max(0.0, min(1.0, float(_env("RUANA_AI_TEMPERATURE", "0.4") or 0.4)))
    except ValueError:
        return 0.4


def _post_json(url: str, payload: Dict[str, Any], cabeceras: Dict[str, str]) -> Optional[Dict[str, Any]]:
    datos = json.dumps(payload).encode("utf-8")
    base = {"Content-Type": "application/json", "Accept": "application/json"}
    base.update(cabeceras)
    peticion = urllib.request.Request(url, data=datos, headers=base, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=_timeout()) as respuesta:
            cuerpo = respuesta.read().decode("utf-8", errors="replace")
        return json.loads(cuerpo) if cuerpo else None
    except urllib.error.HTTPError as exc:
        detalle = ""
        try:
            detalle = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        logger.warning("Copiloto LLM: HTTP %s · %s", exc.code, detalle)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Copiloto LLM: sin conexión · %s", exc)
        return None
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Copiloto LLM: respuesta ilegible · %s", exc)
        return None


def _llamar_formato_openai(system: str, mensajes: List[Dict[str, str]]) -> Optional[str]:
    payload = {
        "model": modelo(),
        "messages": [{"role": "system", "content": system}] + mensajes,
        "temperature": _temperatura(),
        "max_tokens": _max_tokens(),
        "stream": False,
    }
    datos = _post_json(
        f"{base_url()}/chat/completions",
        payload,
        {"Authorization": f"Bearer {api_key()}"},
    )
    if not datos:
        return None
    try:
        opciones = datos.get("choices") or []
        if not opciones:
            return None
        contenido = (opciones[0].get("message") or {}).get("content")
    except (AttributeError, IndexError, TypeError):
        return None
    return _limpiar(contenido)


def _llamar_formato_anthropic(system: str, mensajes: List[Dict[str, str]]) -> Optional[str]:
    payload = {
        "model": modelo(),
        "system": system,
        "messages": mensajes,
        "max_tokens": _max_tokens(),
        "temperature": _temperatura(),
    }
    datos = _post_json(
        f"{base_url()}/messages",
        payload,
        {
            "x-api-key": api_key(),
            "anthropic-version": "2023-06-01",
        },
    )
    if not datos:
        return None
    try:
        bloques = datos.get("content") or []
        texto = "".join(
            b.get("text", "") for b in bloques if isinstance(b, dict) and b.get("type") == "text"
        )
    except (AttributeError, TypeError):
        return None
    return _limpiar(texto)


def _limpiar(texto: Any) -> Optional[str]:
    if not isinstance(texto, str):
        return None
    limpio = texto.strip()
    if not limpio:
        return None
    # El modelo a veces envuelve todo en ```; aquí no hay código.
    if limpio.startswith("```") and limpio.endswith("```"):
        limpio = limpio.strip("`").strip()
        if limpio.lower().startswith("text\n"):
            limpio = limpio[5:]
    return limpio[:4000]


def responder(system: str, mensajes: List[Dict[str, str]]) -> Optional[str]:
    """Devuelve el texto del modelo o None. Nunca lanza."""
    if not disponible():
        return None
    limpios: List[Dict[str, str]] = []
    for m in mensajes or []:
        rol = str(m.get("role") or "").strip()
        contenido = str(m.get("content") or "").strip()
        if rol in {"user", "assistant"} and contenido:
            limpios.append({"role": rol, "content": contenido[:4000]})
    if not limpios:
        return None
    if provider() == "anthropic":
        return _llamar_formato_anthropic(system, limpios)
    return _llamar_formato_openai(system, limpios)


def estado_publico() -> Dict[str, Any]:
    """Lo que puede saber el frontend: si hay IA y cuál, nunca la clave."""
    activo = disponible()
    return {
        "activa": activo,
        "proveedor": provider() if activo else None,
        "modelo": modelo() if activo else None,
        "modo": "ia" if activo else "asistente",
    }
