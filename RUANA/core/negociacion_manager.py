"""
Negociación guiada RUANA — sustituye el chat libre.
Cada contacto avanza por pasos: servicio, fecha, hora, dirección, observaciones, precio.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CAMPOS_SOLICITANTE = ['servicio', 'fecha', 'hora', 'direccion', 'observaciones']
CAMPOS_ORDEN = CAMPOS_SOLICITANTE + ['precio']

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

ESTADO_LABELS = {
    ESTADO_PENDIENTE: 'Pendiente',
    ESTADO_EN_NEGOCIACION: 'En negociación',
    ESTADO_CONFIRMADO: 'Confirmado',
}

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


def estado_inicial(_servicio_inicial: str = '') -> Dict[str, Any]:
    """Estado vacío: el contratante envía la primera propuesta desde el modal."""
    return {
        'paso_actual': 'servicio',
        'campos': {c: _campo_vacio() for c in CAMPOS_ORDEN},
        'observaciones_profesional': {'valor': '', 'estado': ESTADO_PENDIENTE, 'confirmado_en': None},
        'completo': False,
    }


def parse_negociacion(raw: Any) -> Dict[str, Any]:
    if not raw:
        return estado_inicial()
    if isinstance(raw, dict):
        return normalizar_estado(raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return normalizar_estado(data)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return estado_inicial()


def normalizar_estado(estado: Dict[str, Any]) -> Dict[str, Any]:
    """Sincroniza paso_actual y completo con los campos reales. Evita estados imposibles."""
    if not isinstance(estado, dict):
        return estado_inicial()
    campos = estado.get('campos')
    if not isinstance(campos, dict):
        estado['campos'] = {c: _campo_vacio() for c in CAMPOS_ORDEN}
    else:
        for c in CAMPOS_ORDEN:
            if c not in campos or not isinstance(campos[c], dict):
                campos[c] = _campo_vacio()
    siguiente = _siguiente_paso(estado)
    if siguiente:
        estado['paso_actual'] = siguiente
        estado['completo'] = False
    elif _todos_campos_confirmados(estado):
        estado['completo'] = True
        estado['paso_actual'] = CAMPOS_ORDEN[-1]
    else:
        estado['paso_actual'] = estado.get('paso_actual') or 'servicio'
        estado['completo'] = False
    if 'observaciones_profesional' not in estado or not isinstance(estado['observaciones_profesional'], dict):
        estado['observaciones_profesional'] = {'valor': '', 'estado': ESTADO_PENDIENTE, 'confirmado_en': None}
    return estado


def serializar_negociacion(estado: Dict[str, Any]) -> str:
    return json.dumps(normalizar_estado(estado), ensure_ascii=False)


def _rol_en_contacto(codigo: str, solicitante: str, profesional: str) -> Optional[str]:
    c = (codigo or '').strip()
    if c == (solicitante or '').strip():
        return 'solicitante'
    if c == (profesional or '').strip():
        return 'profesional'
    return None


def _nombre_rol(rol: str) -> str:
    return 'contratante' if rol == 'solicitante' else 'profesional'


def _otro_rol(rol: str) -> str:
    return 'profesional' if rol == 'solicitante' else 'solicitante'


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
        return extra or 'RUANA ha iniciado la negociación guiada.'
    if tipo == TIPO_PROPUESTA:
        return f'El {quien} propone {label.lower()}: «{valor}».'
    if tipo == TIPO_CONTRAOFERTA:
        return f'El {quien} sugiere cambiar {label.lower()} a: «{valor}».'
    if tipo == TIPO_ACEPTACION:
        return f'El {quien} confirma {label.lower()}: «{valor}».'
    return extra or ''


def resumen_acuerdo(estado: Dict[str, Any]) -> List[Dict[str, Any]]:
    estado = normalizar_estado(estado)
    items = []
    for campo in CAMPOS_ORDEN:
        c = estado['campos'][campo]
        est = c.get('estado') or ESTADO_PENDIENTE
        items.append({
            'campo': campo,
            'label': CAMPOS_LABELS[campo],
            'valor': c.get('valor') or '',
            'estado': est,
            'estado_label': ESTADO_LABELS.get(est, est),
            'propuesto_por': c.get('propuesto_por'),
            'confirmado_en': c.get('confirmado_en'),
        })
    obs_prof = estado.get('observaciones_profesional') or {}
    obs_est = obs_prof.get('estado') or ESTADO_PENDIENTE
    items.append({
        'campo': 'observaciones_profesional',
        'label': 'Observaciones del profesional',
        'valor': obs_prof.get('valor') or '',
        'estado': obs_est,
        'estado_label': ESTADO_LABELS.get(obs_est, obs_est),
        'propuesto_por': 'profesional' if obs_prof.get('valor') else None,
        'confirmado_en': obs_prof.get('confirmado_en'),
    })
    return items


def _mensaje_proponer(campo: str, rol: str) -> str:
    label = CAMPOS_LABELS.get(campo, campo).lower()
    if campo == 'servicio':
        return 'Indica qué servicio necesitas. Puedes elegir del catálogo del profesional o escribirlo tú.'
    if rol == 'solicitante':
        return f'Propón la {label} para continuar con el acuerdo.'
    return f'Indica la {label}.'


def _mensaje_esperar_turno(campo: str, rol: str, valor: str, propuesto_por: str) -> str:
    label = CAMPOS_LABELS.get(campo, campo).lower()
    otro = _nombre_rol(_otro_rol(rol))
    if propuesto_por == rol:
        return (
            f'Has propuesto {label}: «{valor}». '
            f'RUANA ha enviado tu propuesta al {otro}. Te avisaremos en cuanto responda.'
        )
    return f'Espera a que el {otro} proponga {label}.'


def _mensaje_esperar_otro(campo: str, rol: str) -> str:
    label = CAMPOS_LABELS.get(campo, campo).lower()
    otro = _nombre_rol(_otro_rol(rol))
    if rol == 'profesional' and campo == 'servicio':
        return f'El contratante indicará el {label}. Te avisaremos en cuanto lo proponga.'
    return f'Espera a que el {otro} proponga {label}.'


def _pregunta_profesional(campo: str) -> str:
    """Preguntas conversacionales que el profesional hace al contratante."""
    preguntas = {
        'servicio': 'Hola, ¿qué servicio necesitas? Puedes elegir del catálogo o escribirlo tú.',
        'fecha': '¿Qué fecha te vendría bien para el servicio?',
        'hora': '¿A qué hora prefieres que vayamos?',
        'direccion': '¿Cuál es la dirección donde realizar el trabajo?',
        'observaciones': '¿Alguna observación adicional? (acceso, detalles del trabajo, etc.)',
        'precio': 'Indica el precio que propones por este encargo.',
    }
    return preguntas.get(campo, f'Indica {CAMPOS_LABELS.get(campo, campo).lower()}.')


def _propuesta_solicitante_enviada(estado: Dict[str, Any]) -> bool:
    return all(
        estado['campos'][c].get('estado', ESTADO_PENDIENTE) != ESTADO_PENDIENTE
        for c in CAMPOS_SOLICITANTE
    )


def _todos_solicitante_confirmados(estado: Dict[str, Any]) -> bool:
    return all(
        estado['campos'][c].get('estado') == ESTADO_CONFIRMADO
        for c in CAMPOS_SOLICITANTE
    )


def _todos_campos_pendientes(estado: Dict[str, Any]) -> bool:
    return all(
        estado['campos'][c].get('estado', ESTADO_PENDIENTE) == ESTADO_PENDIENTE
        for c in CAMPOS_ORDEN
    )


def _paso_actual_data(estado: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    paso = _siguiente_paso(estado) or estado.get('paso_actual') or 'servicio'
    return paso, estado['campos'].get(paso, _campo_vacio())


def _mensaje_responder(paso: str, propuesto_por: str, valor: str) -> str:
    label = CAMPOS_LABELS.get(paso, paso).lower()
    quien = _nombre_rol(propuesto_por) if propuesto_por else 'contratante'
    return (
        f'El {quien} propone {label}: «{valor}». '
        f'¿Lo confirmas o quieres sugerir otro valor?'
    )


def _mensaje_espera_propia_propuesta(paso: str, rol: str, valor: str) -> str:
    otro = _nombre_rol(_otro_rol(rol))
    label = CAMPOS_LABELS.get(paso, paso).lower()
    return (
        f'Has propuesto {label}: «{valor}». '
        f'Esperando la respuesta del {otro}. Puedes actualizar tu propuesta si lo necesitas.'
    )


def meta_negociacion(
    estado: Dict[str, Any],
    rol: str,
    contacto_estado: str,
) -> Dict[str, Any]:
    """Metadatos de estado para UI: turno, progreso y siguiente acción."""
    estado = normalizar_estado(estado)
    total = len(CAMPOS_ORDEN)
    confirmados = sum(
        1 for c in CAMPOS_ORDEN if estado['campos'][c].get('estado') == ESTADO_CONFIRMADO
    )

    if contacto_estado == 'trabajo_cerrado':
        return {
            'fase': 'cerrado',
            'progreso_confirmados': total,
            'progreso_total': total,
            'turno': 'completado',
            'requiere_mi_respuesta': False,
            'paso': None,
            'paso_label': 'Trabajo cerrado',
            'contexto': 'El encargo quedó registrado como realizado.',
            'siguiente_accion': 'Revisa el Apoyo RUANA pendiente si corresponde.',
        }

    if contacto_estado == 'acuerdo_alcanzado' or estado.get('completo'):
        return {
            'fase': 'acuerdo',
            'progreso_confirmados': total,
            'progreso_total': total,
            'turno': 'completado',
            'requiere_mi_respuesta': False,
            'paso': None,
            'paso_label': 'Acuerdo alcanzado',
            'contexto': 'Todos los puntos del encargo están confirmados.',
            'siguiente_accion': 'Revisa el resumen y cierra la negociación para confirmar el acuerdo.',
        }

    if _todos_campos_pendientes(estado):
        if rol == 'solicitante':
            return {
                'fase': 'inicio',
                'progreso_confirmados': 0,
                'progreso_total': total,
                'turno': 'contratante',
                'requiere_mi_respuesta': True,
                'paso': 'servicio',
                'paso_label': 'Datos del encargo',
                'contexto': 'Indica los detalles del servicio que necesitas.',
                'siguiente_accion': 'Responde las preguntas para enviar la propuesta al profesional.',
            }
        return {
            'fase': 'inicio',
            'progreso_confirmados': 0,
            'progreso_total': total,
            'turno': 'contratante',
            'requiere_mi_respuesta': False,
            'paso': 'servicio',
            'paso_label': 'Datos del encargo',
            'contexto': 'El contratante está preparando los detalles del encargo.',
            'siguiente_accion': 'Te avisaremos cuando haya una propuesta para revisar.',
        }

    paso, c = _paso_actual_data(estado)
    paso_label = CAMPOS_LABELS.get(paso, paso)
    campo_estado = c.get('estado', ESTADO_PENDIENTE)
    propuesto_por = c.get('propuesto_por')
    valor = c.get('valor') or ''

    requiere_mi_respuesta = (
        campo_estado == ESTADO_EN_NEGOCIACION
        and propuesto_por
        and propuesto_por != rol
    )

    if requiere_mi_respuesta:
        quien = _nombre_rol(propuesto_por)
        return {
            'fase': 'negociacion',
            'progreso_confirmados': confirmados,
            'progreso_total': total,
            'turno': rol,
            'requiere_mi_respuesta': True,
            'paso': paso,
            'paso_label': paso_label,
            'contexto': f'El {quien} ha propuesto un valor para {paso_label.lower()}.',
            'siguiente_accion': f'Confirma o sugiere otro valor para {paso_label.lower()}.',
            'valor_pendiente': valor,
            'propuesto_por': propuesto_por,
        }

    if campo_estado == ESTADO_EN_NEGOCIACION and propuesto_por == rol:
        otro = _nombre_rol(_otro_rol(rol))
        return {
            'fase': 'negociacion',
            'progreso_confirmados': confirmados,
            'progreso_total': total,
            'turno': _otro_rol(rol),
            'requiere_mi_respuesta': False,
            'paso': paso,
            'paso_label': paso_label,
            'contexto': f'Has enviado tu propuesta de {paso_label.lower()}: «{valor}».',
            'siguiente_accion': f'Esperando respuesta del {otro}.',
            'valor_pendiente': valor,
            'propuesto_por': propuesto_por,
        }

    if paso == 'precio' and campo_estado == ESTADO_PENDIENTE:
        if rol == 'profesional':
            return {
                'fase': 'negociacion',
                'progreso_confirmados': confirmados,
                'progreso_total': total,
                'turno': 'profesional',
                'requiere_mi_respuesta': True,
                'paso': paso,
                'paso_label': paso_label,
                'contexto': 'Los datos del encargo ya están confirmados.',
                'siguiente_accion': 'Indica el precio que propones por este trabajo.',
            }
        return {
            'fase': 'negociacion',
            'progreso_confirmados': confirmados,
            'progreso_total': total,
            'turno': 'profesional',
            'requiere_mi_respuesta': False,
            'paso': paso,
            'paso_label': paso_label,
            'contexto': 'Los datos del encargo están confirmados.',
            'siguiente_accion': 'El profesional indicará el precio en breve.',
        }

    if rol == 'profesional' and _propuesta_solicitante_enviada(estado) and confirmados < len(CAMPOS_SOLICITANTE):
        return {
            'fase': 'revision',
            'progreso_confirmados': confirmados,
            'progreso_total': total,
            'turno': 'profesional',
            'requiere_mi_respuesta': campo_estado == ESTADO_EN_NEGOCIACION and propuesto_por == 'solicitante',
            'paso': paso,
            'paso_label': paso_label,
            'contexto': 'El contratante ha enviado todos los datos del encargo.',
            'siguiente_accion': f'Revisa y confirma {paso_label.lower()} para continuar.',
            'valor_pendiente': valor,
            'propuesto_por': propuesto_por,
        }

    if rol == 'solicitante' and _propuesta_solicitante_enviada(estado):
        return {
            'fase': 'revision',
            'progreso_confirmados': confirmados,
            'progreso_total': total,
            'turno': 'profesional',
            'requiere_mi_respuesta': False,
            'paso': paso,
            'paso_label': paso_label,
            'contexto': 'Has enviado todos los datos del encargo al profesional.',
            'siguiente_accion': 'El profesional revisará y confirmará cada punto.',
        }

    return {
        'fase': 'negociacion',
        'progreso_confirmados': confirmados,
        'progreso_total': total,
        'turno': rol if rol == 'solicitante' else 'contratante',
        'requiere_mi_respuesta': False,
        'paso': paso,
        'paso_label': paso_label,
        'contexto': f'Negociación en curso — {paso_label}.',
        'siguiente_accion': 'Abre la negociación para continuar.',
    }


def _revision_solicitante_pendiente(estado: Dict[str, Any]) -> bool:
    """El profesional aún no ha confirmado todos los datos del contratante."""
    return any(
        estado['campos'][c].get('estado') == ESTADO_EN_NEGOCIACION
        for c in CAMPOS_SOLICITANTE
    )


def _propuesta_completa_en_revision(estado: Dict[str, Any]) -> bool:
    """Propuesta enviada por el contratante; el profesional confirma punto por punto."""
    if not _propuesta_solicitante_enviada(estado):
        return False
    if _todos_campos_confirmados(estado):
        return False
    return True


def _mensaje_proponer_completo() -> str:
    return (
        'Te haré unas preguntas sobre el encargo. Cuando terminemos, '
        'enviaré toda la información al profesional para que la confirme.'
    )


def accion_disponible(estado: Dict[str, Any], rol: str, contacto_estado: str) -> Dict[str, Any]:
    """Indica qué puede hacer el usuario. Nunca devuelve espera sin contexto."""
    if contacto_estado in ('cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado'):
        return {'tipo': 'cerrado', 'mensaje': 'Esta negociación está cerrada.'}
    if contacto_estado == 'acuerdo_alcanzado':
        return {
            'tipo': 'resumen',
            'mensaje': (
                'Acuerdo alcanzado. Revisa el resumen y cierra la negociación '
                'para confirmar. Cuando ambas partes cierren, el encargo se registra como trabajo realizado.'
            ),
        }

    estado = normalizar_estado(estado)
    if estado.get('completo'):
        return {
            'tipo': 'resumen',
            'mensaje': 'Negociación completada. Revisa el resumen del acuerdo.',
        }

    if _todos_campos_pendientes(estado):
        if rol == 'solicitante':
            return {
                'tipo': 'wizard_contratante',
                'mensaje': _mensaje_proponer_completo(),
                'campos': list(CAMPOS_SOLICITANTE),
                'preguntas': {c: _pregunta_profesional(c) for c in CAMPOS_SOLICITANTE},
            }
        return {
            'tipo': 'esperar',
            'mensaje': 'El contratante está indicando los detalles del encargo.',
        }

    paso, campo_data = _paso_actual_data(estado)
    campo_estado = campo_data.get('estado', ESTADO_PENDIENTE)
    propuesto_por = campo_data.get('propuesto_por')
    valor = campo_data.get('valor') or ''

    base = {'campo': paso, 'label': CAMPOS_LABELS[paso], 'paso_actual': paso}

    if campo_estado == ESTADO_PENDIENTE:
        if paso == 'precio':
            if rol == 'profesional':
                return {
                    **base,
                    'tipo': 'proponer',
                    'mensaje': _pregunta_profesional('precio'),
                    'chat_style': True,
                }
            return {
                **base,
                'tipo': 'esperar',
                'mensaje': 'El profesional te indicará el precio en breve.',
            }
        if rol == 'solicitante':
            return {
                **base,
                'tipo': 'proponer',
                'mensaje': _mensaje_proponer(paso, rol),
            }
        return {
            **base,
            'tipo': 'esperar',
            'mensaje': _mensaje_esperar_otro(paso, rol),
        }

    if campo_estado == ESTADO_EN_NEGOCIACION:
        if propuesto_por == rol:
            return {
                **base,
                'tipo': 'proponer',
                'mensaje': _mensaje_espera_propia_propuesta(paso, rol, valor),
                'valor_actual': valor,
                'modificar_propia': True,
            }
        return {
            **base,
            'tipo': 'responder',
            'mensaje': _mensaje_responder(paso, propuesto_por or 'solicitante', valor),
            'valor_actual': valor,
            'propuesto_por': propuesto_por,
            'chat_style': True,
        }

    # Campo confirmado pero aún no avanzó (normalizar lo corrige; fallback seguro)
    if rol == 'solicitante':
        return {**base, 'tipo': 'proponer', 'mensaje': _mensaje_proponer(paso, rol)}
    return {**base, 'tipo': 'esperar', 'mensaje': _mensaje_esperar_otro(paso, rol)}


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

    estado = normalizar_estado(estado)
    paso_permitido = _siguiente_paso(estado)
    if not paso_permitido:
        raise ValueError('La negociación ya está completa')

    if campo == 'precio':
        if rol != 'profesional':
            raise ValueError('Solo el profesional puede proponer el precio')
        if not _todos_solicitante_confirmados(estado):
            raise ValueError('Debes confirmar todos los datos del encargo antes de proponer el precio')
    elif rol != 'solicitante':
        raise ValueError('Solo el contratante puede proponer este dato')

    c = estado['campos'][campo]
    if campo != paso_permitido:
        if c['estado'] == ESTADO_EN_NEGOCIACION and c.get('propuesto_por') == rol:
            pass  # modificar propia propuesta en curso
        elif c['estado'] != ESTADO_EN_NEGOCIACION:
            raise ValueError(f'Solo puedes avanzar en el paso actual ({CAMPOS_LABELS.get(paso_permitido, paso_permitido)})')

    if c['estado'] == ESTADO_PENDIENTE:
        estado['campos'][campo] = {
            'valor': valor,
            'estado': ESTADO_EN_NEGOCIACION,
            'propuesto_por': rol,
            'confirmado_en': None,
        }
        estado['paso_actual'] = campo
        msg = _mensaje_evento(TIPO_PROPUESTA, campo, rol, valor)
        return normalizar_estado(estado), msg, TIPO_PROPUESTA

    if c['estado'] == ESTADO_EN_NEGOCIACION and c.get('propuesto_por') == rol:
        estado['campos'][campo] = {
            'valor': valor,
            'estado': ESTADO_EN_NEGOCIACION,
            'propuesto_por': rol,
            'confirmado_en': None,
        }
        estado['paso_actual'] = campo
        msg = _mensaje_evento(TIPO_PROPUESTA, campo, rol, valor)
        return normalizar_estado(estado), msg, TIPO_PROPUESTA

    raise ValueError('Usa contraoferta si necesitas responder a una propuesta de la otra parte')


def proponer_propuesta_completa(
    estado: Dict[str, Any],
    rol: str,
    valores: Dict[str, str],
) -> Tuple[Dict[str, Any], str, List[Tuple[str, str, str]]]:
    """
    El contratante envía todos los campos a la vez.
    Devuelve lista de (campo, valor, mensaje_evento) para registrar en timeline.
    """
    if rol != 'solicitante':
        raise ValueError('Solo el contratante puede enviar la propuesta completa')

    estado = normalizar_estado(estado)
    if not _todos_campos_pendientes(estado):
        raise ValueError('La propuesta completa solo puede enviarse al inicio, antes de cualquier confirmación')

    eventos: List[Tuple[str, str, str]] = []
    for campo in CAMPOS_SOLICITANTE:
        valor = (valores.get(campo) or '').strip()
        if not valor:
            raise ValueError(f'{CAMPOS_LABELS[campo]} es obligatorio')
        estado['campos'][campo] = {
            'valor': valor,
            'estado': ESTADO_EN_NEGOCIACION,
            'propuesto_por': rol,
            'confirmado_en': None,
        }
        msg = _mensaje_evento(TIPO_PROPUESTA, campo, rol, valor)
        eventos.append((campo, valor, msg))

    estado['paso_actual'] = 'servicio'
    estado = normalizar_estado(estado)
    msg_resumen = (
        'El contratante ha enviado todos los datos del encargo. '
        'Revisa y confirma cada punto; luego podrás proponer el precio.'
    )
    return estado, msg_resumen, eventos


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

    estado = normalizar_estado(estado)
    paso_permitido = _siguiente_paso(estado)
    if not paso_permitido:
        raise ValueError('La negociación ya está completa')
    if campo != paso_permitido:
        raise ValueError(
            f'Solo puedes negociar el paso actual ({CAMPOS_LABELS.get(paso_permitido, paso_permitido)})'
        )

    c = estado['campos'][campo]
    if c['estado'] != ESTADO_EN_NEGOCIACION:
        raise ValueError(f'{CAMPOS_LABELS[campo]} no está en negociación')

    propuesto_por = c.get('propuesto_por')
    if propuesto_por == rol:
        raise ValueError('No puedes contraofertar tu propia propuesta; modifícala o espera la respuesta')

    estado['campos'][campo] = {
        'valor': valor,
        'estado': ESTADO_EN_NEGOCIACION,
        'propuesto_por': rol,
        'confirmado_en': None,
    }
    estado['paso_actual'] = campo
    msg = _mensaje_evento(TIPO_CONTRAOFERTA, campo, rol, valor)
    return normalizar_estado(estado), msg, TIPO_CONTRAOFERTA


def aceptar_campo(
    estado: Dict[str, Any],
    rol: str,
    campo: str,
    observaciones_profesional: str = '',
) -> Tuple[Dict[str, Any], str, str, bool]:
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    estado = normalizar_estado(estado)
    paso_permitido = _siguiente_paso(estado)
    if not paso_permitido:
        raise ValueError('La negociación ya está completa')
    if campo != paso_permitido:
        raise ValueError(
            f'Solo puedes confirmar el paso actual ({CAMPOS_LABELS.get(paso_permitido, paso_permitido)})'
        )

    c = estado['campos'][campo]
    if c['estado'] != ESTADO_EN_NEGOCIACION:
        raise ValueError(f'{CAMPOS_LABELS[campo]} no tiene una propuesta pendiente de confirmación')

    propuesto_por = c.get('propuesto_por')
    if propuesto_por == rol:
        raise ValueError('No puedes confirmar tu propia propuesta')

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

    estado = normalizar_estado(estado)
    msg = _mensaje_evento(TIPO_ACEPTACION, campo, rol, valor)
    return estado, msg, TIPO_ACEPTACION, completo


def reabrir_campo_negociacion(estado: Dict[str, Any], rol: str, campo: str, valor: str) -> Tuple[Dict[str, Any], str]:
    """Reabre un campo ya confirmado para negociarlo de nuevo (contraoferta sobre punto acordado)."""
    valor = (valor or '').strip()
    if not valor:
        raise ValueError('El valor es obligatorio')
    if campo not in CAMPOS_ORDEN:
        raise ValueError('Campo no válido')

    estado = normalizar_estado(estado)
    c = estado['campos'][campo]
    if c['estado'] != ESTADO_CONFIRMADO:
        raise ValueError('Solo se puede renegociar un punto ya confirmado mediante contraoferta')

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
    return normalizar_estado(estado), msg


def construir_payload(
    contacto: Dict[str, Any],
    eventos: List[Dict[str, Any]],
    rol: str,
) -> Dict[str, Any]:
    estado = parse_negociacion(contacto.get('negociacion_json'))
    contacto_estado = contacto.get('estado') or ''
    servicio_contacto = (contacto.get('servicio') or '').strip()
    accion = accion_disponible(estado, rol, contacto_estado)
    if accion.get('tipo') in ('wizard_contratante', 'proponer_completo'):
        sugeridos: Dict[str, str] = {}
        if servicio_contacto:
            sugeridos['servicio'] = servicio_contacto
        accion['valores_sugeridos'] = sugeridos
        accion['campos'] = list(CAMPOS_SOLICITANTE)
        accion['preguntas'] = {c: _pregunta_profesional(c) for c in CAMPOS_SOLICITANTE}
        if accion.get('tipo') == 'proponer_completo':
            accion['tipo'] = 'wizard_contratante'
    elif accion.get('tipo') == 'proponer' and accion.get('campo') == 'servicio' and servicio_contacto:
        paso_servicio = estado['campos'].get('servicio', _campo_vacio())
        if paso_servicio.get('estado') == ESTADO_PENDIENTE:
            accion['valor_sugerido'] = servicio_contacto
    return {
        'contacto_id': contacto.get('id'),
        'estado_contacto': contacto_estado,
        'rol': rol,
        'solicitante_codigo': contacto.get('solicitante_codigo'),
        'profesional_codigo': contacto.get('profesional_codigo'),
        'servicio_contacto': servicio_contacto,
        'acuerdo_alcanzado': contacto_estado == 'acuerdo_alcanzado' or bool(estado.get('completo')),
        'negociacion': estado,
        'resumen': resumen_acuerdo(estado),
        'paso_actual': estado.get('paso_actual'),
        'eventos': eventos,
        'accion': accion,
        'campos_labels': CAMPOS_LABELS,
        'campos_orden': CAMPOS_ORDEN,
        'campos_solicitante': CAMPOS_SOLICITANTE,
        'negociacion_meta': meta_negociacion(estado, rol, contacto_estado),
        'cierre_confirmado_solicitante': bool(contacto.get('cierre_confirmado_solicitante_en')),
        'cierre_confirmado_profesional': bool(contacto.get('cierre_confirmado_profesional_en')),
        'yo_confirme_cierre': bool(
            contacto.get('cierre_confirmado_solicitante_en')
            if rol == 'solicitante'
            else contacto.get('cierre_confirmado_profesional_en')
        ),
        'ambos_confirmaron_cierre': bool(
            contacto.get('cierre_confirmado_solicitante_en')
            and contacto.get('cierre_confirmado_profesional_en')
        ),
        'resumen_dismissed': bool(
            contacto.get('resumen_dismiss_solicitante_en')
            if rol == 'solicitante'
            else contacto.get('resumen_dismiss_profesional_en')
        ),
        'acuerdo_alcanzado_en': contacto.get('acuerdo_alcanzado_en'),
    }
