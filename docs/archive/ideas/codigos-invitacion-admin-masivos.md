# Idea futura: codigos de invitacion admin reutilizables

Fecha: 2026-05-29

## Objetivo

Permitir que un administrador genere codigos de invitacion reutilizables para que varias personas puedan unirse a la plataforma sin crear previamente un aliado placeholder por cada invitado.

## Necesidad

El admin deberia poder:

- Crear un codigo de invitacion general o por campana.
- Definir un numero maximo de usos.
- Ver cuantos usos lleva el codigo.
- Darlo de baja manualmente.
- Generar un codigo nuevo cuando sea necesario.
- Obtener un enlace y un QR para compartir.

El QR deberia llevar a una URL publica con el codigo ya incluido, por ejemplo:

```text
/invite.html?codigo=RUANA-MADRID-01
```

o:

```text
/register.html?codigo=RUANA-MADRID-01
```

La app deberia validar automaticamente el codigo, guardar el contexto de invitacion y abrir el formulario de registro sin que el usuario tenga que escribirlo manualmente.

## Encaje con el sistema actual

La opcion mas compatible es anadir una capa nueva, sin sustituir los codigos actuales:

- Mantener los codigos personales de aliado para ingreso.
- Mantener las invitaciones existentes de oficio y los placeholders `pendiente_completar`.
- Anadir una tabla nueva para codigos de invitacion admin reutilizables.
- Hacer que `/api/validar-invitacion` compruebe primero esta nueva tabla y, si no encuentra el codigo, continue con el flujo actual.
- Al completar el registro, incrementar el contador de usos del codigo reutilizable.

## Modelo orientativo

```text
codigos_invitacion_admin
- codigo
- nombre
- activo
- max_usos
- usos_actuales
- creado_por_admin
- creado_en
- desactivado_en
- expira_en
- codigo_postal
- notas
```

## Recomendacion

Usar prefijos claros para evitar confundirlos con codigos personales de aliado de 5 digitos. Ejemplos:

```text
INV-MADRID-01
RUANA-ABRIL26
RUANA-FERIA-2026
```

Esta idea es especialmente util para campanas, eventos, flyers, QR fisicos, colaboraciones o altas iniciales controladas por administracion.
