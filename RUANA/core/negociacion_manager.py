"""
Negociación guiada RUANA — sustituye el chat libre.
Cada contacto avanza por pasos: servicio, fecha, hora, dirección, precio, observaciones.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CAMPOS_ORDEN = ['servicio', 'fecha', 'hora', 'direccion', 'precio', 'observaciones']

CAMPOS_LABELS = {
    'servicio': 'Servicio',
    'fecha': 'Fecha',
    'hora': 'Hora',
    'direccion': 'Dirección',
    'precio': 'Precio final',
    'observaciones': 'Observaciones adicionales',
}

ESTADO_PENDIENTE = 'pendiente'
ESTADO_EN_NEGOCIACION = 'en_negociacion'
ESTADO_CONFIRMADO = 'confirmado'

TIPO_SISTEMA = 'sistema'
TIPO_PROPUESTA = 'propuesta'
TIPO_ACEPTACION = 'aceptacion'
TIPO_CONTRAOFERTA = 'contraoferta'


def _campo_vacio() -> Dict[str, Any]:
    return {
        'valor': '',
        'estado': ESTADO_PENDIENTE,
        'propuesto_por': None,
        'confirmado_en': None,
    }


def estado_inicial(servicio_inicial: str = '') -> Dict[str, Any]:
    estado = {
        'paso_actual': 'servicio',
        'campos': {c: _campo_vacio() for c in CAMPOS_ORDEN},
        'observaciones_profesional': {'valor': '', 'estado': ESTADO_PENDIENTE, 'confirmado_en': None},
        'completo': False,
    }
    servicio = (servicio_inicial or '').strip()
    if servicio:
        estado['campos']['servicio'] = {
            'valor': servicio,
            'estado': ESTADO_EN_NEGOCIACION,
            'propuesto_por': 'solicitante',
            'confirmado_en': None,
        }
    return estado


def parse_negociacion(raw: Any) -> Dict[str, Any]:
    if not raw:
        return estado_inicial()
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return estado_inicial()


def serializar_negociacion(estado: Dict[str, Any]) -> str:
    return json.dumps(estado, ensure_ascii=False)


def _rol_en_contacto(codigo: str, solicitante: str, profesional: str) -> Optional[str]:
    c = (codigo or '').strip()
    if c == (solicitante or '').strip():
        return 'solicitante'
    if c == (profesional or '').strip():
        return 'profesional'
    return None


def _nombre_rol(rol: str) -> str:
    return 'contratante' if rol == 'solicitante' else 'profesional'


def _siguiente_paso(estado: Dict[str, Any]) -> Optional[str]:
    for campo in CAMPOS_ORDEN:
        if estado['campos'][campo]['estado'] != ESTADO_CONFIRMADO:
            return campo
    return None


def _todos_campos_confirmados(estado: Dict[str, Any]) -> bool:
    return all(estado['campos'][c]['estado'] == ESTADO_CONFIRMADO for c in CAMPOS_ORDEN)


def _mensaje_evento(tipo: str, campo: str, rol: str, valor: str = '', extra: str = '') -> str:
    label = CAMPOS_LABELS.get(campo, campo)
    quien = _nombre_rol(rol)
    if tipo == TIPO_SISTEMA:
        return extra or f'RUANA ha iniciado la negociación guiada.'
    if tipo == TIPO_PROPUESTA:
        return f'El {quien} propone {label.lower()}: «{valor}».'
    if tipo == TIPO_CONTRAOFERTA:
        return f'El {quien} propone cambiar {label.lower()} a: «{valor}».'
    if tipo == TIPO_ACEPTACION:
        return f'El {quien} acepta {label.lower()}: «{valor}».'
    return extra or ''


def resumen_acuerdo(estado: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for campo in CAMPOS_ORDEN:
        c = estado['campos'][campo]
        items.append({
            'campo': campo,
            'label': CAMPOS_LABELS[campo],
            'valor': c.get('valor') or '',
            'estado': c.get('estado') or ESTADO_PENDIENTE,
            'propuesto_por': c.get('propuesto_por'),
            'confirmado_en': c.get('confirmado_en'),
        })
    obs_prof = estado.get('observaciones_profesional') or {}
    items.append({
        'campo': 'observaciones_profesional',
        'label': 'Observaciones del profesional',
        'valor': obs_prof.get('valor') or '',
        'estado': obs_prof.get('estado') or ESTADO_PENDIENTE,
        'propuesto_por': 'profesional' if obs_prof.get('valor') else None,
        'confirmado_en': obs_prof.get('confirmado_en'),
    })
    return items


def accion_disponible(estado: Dict[str, Any], rol: str, contacto_estado: str) -> Dict[str, Any]:
    """Indica qué puede hacer el usuario en el paso actual."""
    if contacto_estado in ('cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado'):
        return {'tipo': 'cerrado', 'mensaje': 'Esta negociación está cerrada.'}
    if contacto_estado == 'acuerdo_alcanzado':
        return {'tipo': 'resumen', 'mensaje': 'Acuerdo alcanzado. Cuando se realice el servicio, usa el seguimiento del contacto.'}
    if estado.get('completo'):
        return {'tipo': 'resumen', 'mensaje': 'Negociación completa pendiente de cierre automático.'}

    paso = estado.get('paso_actual') or _siguiente_paso(estado) or 'servicio'
    campo_data = estado['campos'].get(paso, _campo_vacio())
    campo_estado = campo_data.get('estado', ESTADO_PENDIENTE)
    propuesto_por = campo_data.get('propuesto_por')

    if campo_estado == ESTADO_PENDIENTE:
        if paso == 'servicio' and rol == 'solicitante':
            return {'tipo': 'proponer', 'campo': paso, 'label': CAMPOS_LABELS[paso]}
        if paso != 'servicio' and rol == 'solicitante':
            return {'tipo': 'proponer', 'campo': paso, 'label': CAMPOS_LABELS[paso]}
        return {'tipo': 'esperar', 'campo': paso, 'mensaje': f'Esperando propuesta de {CAMPOS_LABELS[paso].lower()}.'}

    if campo_estado == ESTADO_EN_NEGOCIACION:
        if propuesto_por == rol:
            return {'tipo': 'esperar', 'campo': paso, 'mensaje': f'Esperando respuesta sobre {CAMPOS_LABELS[paso].lower()}.'}
        return {
            'tipo': 'responder',
            'campo': paso,
            'label': CAMPOS_LABELS[paso],
            'valor_actual': campo_data.get('valor') or '',
            'propuesto_por': propuesto_por,
        }

    return {'tipo': 'esperar', 'campo': paso, 'mensaje': 'Negociación en curso.'}


def proponer_campo(
    estado: Dict[str, Any],
    rol: str,
    campo: str,
    valor: str,
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    valor = (valor or '').strip()
    if not valor:
        raise ValueError('El valor es obligatorio')
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    paso_permitido = estado.get('paso_actual') or _siguiente_paso(estado)
    if campo != paso_permitido:
        # Solo se negocia el punto en disputa si ya fue confirmado parcialmente
        c = estado['campos'][campo]
        if c['estado'] == ESTADO_CONFIRMADO:
            raise ValueError(f'Solo puedes negociar el punto actual ({CAMPOS_LABELS.get(paso_permitido, paso_permitido)})')
        if c['estado'] != ESTADO_EN_NEGOCIACION:
            raise ValueError(f'El campo {CAMPOS_LABELS[campo]} no está en negociación')

    if rol != 'solicitante':
        raise ValueError('Solo el contratante puede iniciar o proponer un nuevo valor en el paso actual')

    if estado['campos'][campo]['estado'] == ESTADO_PENDIENTE and campo == paso_permitido:
        estado['campos'][campo] = {
            'valor': valor,
            'estado': ESTADO_EN_NEGOCIACION,
            'propuesto_por': rol,
            'confirmado_en': None,
        }
        estado['paso_actual'] = campo
        msg = _mensaje_evento(TIPO_PROPUESTA, campo, rol, valor)
        return estado, msg, TIPO_PROPUESTA

    raise ValueError('Usa contraoferta si necesitas cambiar una propuesta en curso')


def contraoferta_campo(
    estado: Dict[str, Any],
    rol: str,
    campo: str,
    valor: str,
) -> Tuple[Dict[str, Any], str, str]:
    valor = (valor or '').strip()
    if not valor:
        raise ValueError('El valor es obligatorio')
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    c = estado['campos'][campo]
    if c['estado'] != ESTADO_EN_NEGOCIACION:
        raise ValueError(f'{CAMPOS_LABELS[campo]} no está en negociación')

    propuesto_por = c.get('propuesto_por')
    if propuesto_por == rol:
        raise ValueError('No puedes contraofertar tu propia propuesta; espera la respuesta de la otra parte')

    estado['campos'][campo] = {
        'valor': valor,
        'estado': ESTADO_EN_NEGOCIACION,
        'propuesto_por': rol,
        'confirmado_en': None,
    }
    estado['paso_actual'] = campo
    msg = _mensaje_evento(TIPO_CONTRAOFERTA, campo, rol, valor)
    return estado, msg, TIPO_CONTRAOFERTA


def aceptar_campo(
    estado: Dict[str, Any],
    rol: str,
    campo: str,
    observaciones_profesional: str = '',
) -> Tuple[Dict[str, Any], str, str, bool]:
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    c = estado['campos'][campo]
    if c['estado'] != ESTADO_EN_NEGOCIACION:
        raise ValueError(f'{CAMPOS_LABELS[campo]} no tiene una propuesta pendiente de aceptación')

    propuesto_por = c.get('propuesto_por')
    if propuesto_por == rol:
        raise ValueError('No puedes aceptar tu propia propuesta')

    valor = c.get('valor') or ''
    ahora = datetime.now(timezone.utc).isoformat()
    estado['campos'][campo] = {
        'valor': valor,
        'estado': ESTADO_CONFIRMADO,
        'propuesto_por': propuesto_por,
        'confirmado_en': ahora,
    }

    if campo == 'observaciones' and rol == 'profesional':
        obs = (observaciones_profesional or '').strip()
        if obs:
            estado['observaciones_profesional'] = {
                'valor': obs,
                'estado': ESTADO_CONFIRMADO,
                'confirmado_en': ahora,
            }

    siguiente = _siguiente_paso(estado)
    estado['paso_actual'] = siguiente or campo
    completo = _todos_campos_confirmados(estado)
    if completo:
        obs_prof = estado.get('observaciones_profesional') or {}
        if not obs_prof.get('valor') and rol == 'profesional' and (observaciones_profesional or '').strip():
            estado['observaciones_profesional'] = {
                'valor': observaciones_profesional.strip(),
                'estado': ESTADO_CONFIRMADO,
                'confirmado_en': ahora,
            }
        elif obs_prof.get('valor') and obs_prof.get('estado') != ESTADO_CONFIRMADO:
            estado['observaciones_profesional']['estado'] = ESTADO_CONFIRMADO
            estado['observaciones_profesional']['confirmado_en'] = ahora
        estado['completo'] = True

    msg = _mensaje_evento(TIPO_ACEPTACION, campo, rol, valor)
    return estado, msg, TIPO_ACEPTACION, completo


def reabrir_campo_negociacion(estado: Dict[str, Any], rol: str, campo: str, valor: str) -> Tuple[Dict[str, Any], str]:
    """Reabre un campo ya confirmado para negociarlo de nuevo (contraoferta sobre punto acordado)."""
    valor = (valor or '').strip()
    if not valor:
        raise ValueError('El valor es obligatorio')
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    c = estado['campos'][campo]
    if c['estado'] != ESTADO_CONFIRMADO:
        raise ValueError('Solo se puede renegociar un punto ya confirmado mediante contraoferta')

    # Desconfirmar este y posteriores
    idx = CAMPOS_ORDEN.index(campo)
    for i in range(idx, len(CAMPOS_ORDEN)):
        cf = CAMPOS_ORDEN[i]
        estado['campos'][cf] = _campo_vacio()
    estado['observaciones_profesional'] = {'valor': '', 'estado': ESTADO_PENDIENTE, 'confirmado_en': None}
    estado['completo'] = False
    estado['campos'][campo] = {
        'valor': valor,
        'estado': ESTADO_EN_NEGOCIACION,
        'propuesto_por': rol,
        'confirmado_en': None,
    }
    estado['paso_actual'] = campo
    msg = _mensaje_evento(TIPO_CONTRAOFERTA, campo, rol, valor)
    return estado, msg


def construir_payload(
    contacto: Dict[str, Any],
    eventos: List[Dict[str, Any]],
    rol: str,
) -> Dict[str, Any]:
    estado = parse_negociacion(contacto.get('negociacion_json'))
    contacto_estado = contacto.get('estado') or ''
    return {
        'contacto_id': contacto.get('id'),
        'estado_contacto': contacto_estado,
        'solicitante_codigo': contacto.get('solicitante_codigo'),
        'profesional_codigo': contacto.get('profesional_codigo'),
        'acuerdo_alcanzado': contacto_estado == 'acuerdo_alcanzado' or bool(estado.get('completo')),
        'negociacion': estado,
        'resumen': resumen_acuerdo(estado),
        'paso_actual': estado.get('paso_actual'),
        'eventos': eventos,
        'accion': accion_disponible(estado, rol, contacto_estado),
        'campos_labels': CAMPOS_LABELS,
        'campos_orden': CAMPOS_ORDEN,
    }
