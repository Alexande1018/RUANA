# Autenticación segura y sesiones por pestaña (RUANA)

## 1) Fallo encontrado

### Causa raíz: sesiones cruzadas entre pestañas

- **Flask usaba la cookie de sesión** para guardar `aliado_codigo` / `admin_codigo` y expiración. Esa cookie es **compartida por todas las pestañas** del mismo origen.
- Al iniciar sesión en una pestaña (Usuario A), el servidor escribía la nueva sesión en la cookie. Cualquier otra pestaña (Usuario B) enviaba en la siguiente petición **la misma cookie**, por lo que el backend identificaba a todos como el último usuario que había hecho login.
- **Admin:** además, el panel guardaba `admin_codigo`, `admin_token`, `admin_expires_at` en **localStorage**, también compartido entre pestañas y accesible por JavaScript (riesgo XSS y sobrescritura de identidad).

### Resumen del diagnóstico

| Problema | Ubicación | Estado |
|----------|-----------|--------|
| Cookie de sesión compartida entre pestañas | Flask `session` (cookie firmada) | Corregido: auth por header + store server-side |
| localStorage para tokens/código admin | `admin.html`: admin_codigo, admin_token | Eliminado: solo sessionStorage + header |
| sessionStorage usado como caché pero cookie como autoridad | `aliado.html`: sesión validada por cookie | Corregido: sesión por header, sessionStorage solo guarda session_id |
| Una sola “identidad” por dominio | Cookie única por sitio | Corregido: un session_id distinto por login (por pestaña si se usa sessionStorage) |
| JWT en localStorage | admin_token | Eliminado para auth principal; JWT opcional solo para API externa |

---

## 2) Cambios en el frontend

### Aliado (index, register, aliado.html)

- **Login:** Tras `POST /api/aliado/login` se guarda `data.session_id` en **sessionStorage** (`ruana_session_id`). No se usa la cookie para identidad.
- **Todas las peticiones:** Se envían las cabeceras con `getRuanaAuthHeaders()` (o `getRuanaAuthHeaders({ 'Content-Type': 'application/json' })` cuando aplique), que añade `X-Ruana-Session-Id` desde `sessionStorage.getItem('ruana_session_id')`.
- **Bootstrap del panel:** `GET /api/aliado/sesion` se llama con `X-Ruana-Session-Id`. Si no hay session_id o la sesión es inválida, redirección a `/`.
- **Logout:** `POST /api/aliado/logout` con el mismo header; luego se limpia `sessionStorage` (incluye `ruana_session_id` por la clave `ruana_`).
- **Register:** Tras mostrar el código del nuevo aliado y al aceptar, se llama a `POST /api/aliado/login` con el código; se guarda `session_id` en sessionStorage y se redirige a `/aliado`.

### Admin (admin.html)

- **Login:** Tras `POST /api/admin/validar` se guarda solo `data.session_id` en **sessionStorage** (`admin_session_id`). Se eliminó el uso de `localStorage` para `admin_codigo`, `admin_token`, `admin_expires_at`, `admin_login_time`.
- **Comprobación de sesión:** `checkExistingSession()` usa `GET /api/admin/me` con cabecera `X-Ruana-Session-Id`. Si no hay `admin_session_id` o la respuesta no es 200, se muestra el modal de login.
- **Peticiones:** `AdminAuthenticator.getAdminAuthHeaders()` (y por tanto `getAuthHeaders()` del panel) devuelve `X-Ruana-Session-Id` desde sessionStorage y, por defecto, `Content-Type: application/json`.
- **Logout y sesión expirada:** Se elimina `admin_session_id` de sessionStorage; el logout envía el header para invalidar la sesión en el servidor.

### Resumen frontend

- **No se usa localStorage para tokens ni para identidad.** Solo sessionStorage para el `session_id` por pestaña.
- El frontend **no manipula el token** (no hay JWT en cliente para auth normal); solo guarda y envía el `session_id` en el header.
- Las peticiones usan `credentials: 'same-origin'` y el header `X-Ruana-Session-Id` para identificación.

---

## 3) Cambios en el backend

### Store de sesiones (app.py)

- **Store en memoria:** `_RUANA_SESSION_STORE` (dict) y `_RUANA_SESSION_LOCK` (threading.Lock). Cada entrada: `session_id -> { tipo, codigo, expires_at, permisos? }`.
- **Helpers:**
  - `_get_ruana_session()`: lee cabecera `X-Ruana-Session-Id`, busca en el store y comprueba expiración; devuelve la sesión o `None`.
  - `_ruana_session_create(tipo, codigo, expires_at, permisos=None)`: genera `session_id` con `secrets.token_urlsafe(32)`, guarda en el store y devuelve el id (evita session fixation).
  - `_ruana_session_invalidate(session_id)`: borra la sesión del store.

### Aliado

- **POST /api/aliado/login:** Crea sesión con `_ruana_session_create('aliado', codigo, expires_at)` y devuelve `{ status, codigo, session_id }`. No escribe en `session` de Flask para auth.
- **GET /api/aliado/sesion:** Comprueba sesión con `_get_ruana_session()` (header). Responde `{ status: 'ok', codigo }` o 401.
- **POST /api/aliado/logout:** Lee `X-Ruana-Session-Id` o body `session_id` y llama a `_ruana_session_invalidate(sid)`.
- **Rutas protegidas:** `_aliado_session_valid()` y `_aliado_codigo()` usan solo `_get_ruana_session()` (tipo `aliado`). No se usa la cookie de Flask para identidad.

### Admin

- **POST /api/admin/validar:** Crea sesión con `_ruana_session_create('admin', codigo, expires_at, permisos=permisos)` y devuelve `{ status, ..., session_id, token }`. El JWT se mantiene opcional para API externa; la auth del panel es por `session_id`.
- **POST /api/admin/logout:** Lee `X-Ruana-Session-Id` o body `session_id` e invalida con `_ruana_session_invalidate(sid)`.
- **Rutas protegidas:** `_admin_session_valid()`, `_admin_codigo()`, `_admin_permisos()` leen primero de `_get_ruana_session()` (tipo `admin`); si no hay sesión por header, se sigue aceptando JWT por `Authorization: Bearer` para compatibilidad.

### Seguridad

- **Session fixation:** Cada login genera un `session_id` nuevo (no se reutiliza el de la petición).
- **Regeneración en login:** Siempre se crea una entrada nueva en el store.
- **Invalidación:** Logout elimina solo esa sesión del store; no afecta a otras pestañas ni a otros usuarios.
- **Múltiples sesiones:** Se permiten varias sesiones activas por usuario (varias pestañas o dispositivos); cada una tiene su propio `session_id`.

---

## 4) Código corregido (referencia)

- **Backend:** `web/app.py` (store, helpers, login/sesion/logout aliado y admin, uso de `_get_ruana_session()` en validadores).
- **Frontend aliado:** `web/index.html` (guardar `session_id` tras login), `web/register.html` (guardar `session_id` tras login al aceptar modal), `web/aliado.html` (`getRuanaAuthHeaders()`, header en todas las peticiones, bootstrap y logout).
- **Frontend admin:** `web/admin.html` (sessionStorage `admin_session_id`, `checkExistingSession` con `/api/admin/me`, `getAdminAuthHeaders()` con `X-Ruana-Session-Id`, logout y `_adminSessionExpired` sin localStorage).

---

## 5) Buenas prácticas aplicadas

- **No almacenar tokens en localStorage:** Evita robo por XSS y sobrescritura entre pestañas.
- **Sesión por pestaña con sessionStorage:** Cada pestaña tiene su propio `session_id`; login en una no cambia la identidad de las demás.
- **Identidad en el servidor:** El `session_id` es un opaco; la identidad (código, permisos) vive en el store server-side.
- **Cabecera dedicada:** `X-Ruana-Session-Id` deja claro qué se usa para sesión y permite CORS/cookies por separado.
- **Protección session fixation:** Nuevo `session_id` en cada login.
- **Logout que invalida:** El servidor borra la sesión; no basta con borrar el id en el cliente.
- **Múltiples sesiones permitidas:** No se limita a una sesión por usuario; cada login (pestaña/dispositivo) obtiene su propia sesión.
- **JWT opcional:** Admin puede seguir usando Bearer JWT para integraciones; la auth principal del panel es por `session_id` y header.

### Producción (recomendaciones)

- Sustituir el store en memoria por un almacén persistente (por ejemplo Redis o base de datos) si hay varios workers o reinicios.
- Mantener `SESSION_COOKIE_HTTPONLY` y `SESSION_COOKIE_SAMESITE` para cualquier cookie que siga usando Flask (por ejemplo mensajes flash).
- En HTTPS, considerar cabeceras adicionales (por ejemplo `Secure`) si en el futuro se usan cookies para algo más.

---

**Resultado:** Cada pestaña mantiene su usuario; el login en una pestaña no cambia la identidad de las demás; las sesiones son independientes y el sistema es adecuado para producción con las consideraciones anteriores.
