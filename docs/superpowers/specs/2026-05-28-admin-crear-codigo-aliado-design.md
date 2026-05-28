# Admin Crear Codigo Aliado Design

## Objetivo

Permitir que un administrador genere desde `/admin` un codigo inicial para un nuevo aliado, sin depender de que ya exista un aliado activo que pueda invitar.

## Alcance

- Anadir un endpoint admin protegido por permisos de escritura: `POST /api/admin/invitaciones/crear`.
- Reutilizar el modelo actual de invitacion: crear un aliado placeholder con codigo numerico unico de 5 digitos y estado `pendiente_completar`.
- Mostrar en el panel admin una accion para generar y copiar el codigo.
- Mantener el registro final en manos del nuevo aliado: el codigo se usa en la pantalla inicial y redirige a `register.html` para completar datos.

## Fuera De Alcance

- Migrar este flujo a Supabase Auth.
- Crear aliados completos desde admin.
- Cambiar las reglas de activacion/rechazo de aliados pendientes.

## Comportamiento

El administrador puede indicar un codigo postal opcional. El backend genera un codigo no usado, crea un aliado placeholder con email y telefono temporales unicos, y devuelve el codigo. El placeholder no se marca como invitacion referida por un aliado, porque el actor es admin.

El usuario recibe ese codigo, lo introduce como codigo de invitacion/ingreso en `/`, completa el formulario de registro, y el sistema mantiene el flujo existente de validacion.

## Pruebas

- El endpoint rechaza peticiones sin sesion admin.
- El endpoint rechaza admins solo lectura.
- El endpoint permite admins con permiso `escribir` o `configurar`.
- El endpoint crea un placeholder `pendiente_completar` con datos temporales y devuelve el codigo.
