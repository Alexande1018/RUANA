/**
 * RUANA Admin Shell — navegación, acciones masivas y auditoría de sesión.
 * No modifica APIs ni lógica de negocio: envuelve el AdminPanel existente.
 */
(function () {
    'use strict';

    const MODULE_DEFS = [
        {
            id: 'resumen',
            label: 'Resumen',
            kicker: 'Vista general',
            subtitle: 'Estado del sistema, movimiento reciente y métricas clave.',
            icon: 'grid',
            targets: ['.estado-global', '.movimiento-sistema', '.metricas-salud']
        },
        {
            id: 'operaciones',
            label: 'Operaciones',
            kicker: 'Bandeja de trabajo',
            subtitle: 'Validaciones, pagos, solicitudes, competencias y comunicación.',
            icon: 'inbox',
            targets: [
                '#pendientes-validacion-wrap',
                '#conflictos-pago-wrap',
                '#pagos-apoyo-wrap',
                '#pagos-en-revision-wrap',
                '#solicitudes-admin-wrap',
                '#competencias-activas-wrap',
                '#competencias-pendientes-wrap',
                '#competencias-historial-wrap',
                '#suplentes-espera-wrap',
                '#conversaciones-ruana-wrap',
                '#centro-comunicacion-admin-wrap'
            ]
        },
        {
            id: 'red',
            label: 'Red',
            kicker: 'Aliados',
            subtitle: 'Explora y gestiona la red de aliados por CP y grupo.',
            icon: 'network',
            targets: ['#control-aliados-wrap']
        },
        {
            id: 'sistema',
            label: 'Sistema',
            kicker: 'Configuración',
            subtitle: 'Trazabilidad, métodos de pago y acciones administrativas.',
            icon: 'settings',
            targets: ['.eventos-trazabilidad', '#metodos-pago-admin-wrap', '#acciones-admin-wrap']
        }
    ];

    const NAV_SECTIONS = [
        { id: 'overview', label: 'Estado global', group: 'Resumen', module: 'resumen', target: '.estado-global', icon: 'grid' },
        { id: 'movimiento', label: 'Movimiento 24h', group: 'Resumen', module: 'resumen', target: '.movimiento-sistema', icon: 'activity' },
        { id: 'salud', label: 'Métricas de salud', group: 'Resumen', module: 'resumen', target: '.metricas-salud', icon: 'heart' },
        { id: 'pendientes', label: 'Pendientes validación', group: 'Operaciones', module: 'operaciones', target: '#pendientes-validacion-wrap', icon: 'user-check', badge: '#pendientes-validacion-count' },
        { id: 'conflictos', label: 'Conflictos de pago', group: 'Operaciones', module: 'operaciones', target: '#conflictos-pago-wrap', icon: 'alert' },
        { id: 'pagos-apoyo', label: 'Pagos Apoyo', group: 'Operaciones', module: 'operaciones', target: '#pagos-apoyo-wrap', icon: 'credit' },
        { id: 'pagos-revision', label: 'Pagos en revisión', group: 'Operaciones', module: 'operaciones', target: '#pagos-en-revision-wrap', icon: 'clock' },
        { id: 'solicitudes', label: 'Solicitudes', group: 'Operaciones', module: 'operaciones', target: '#solicitudes-admin-wrap', icon: 'inbox' },
        { id: 'competencias', label: 'Competencias', group: 'Operaciones', module: 'operaciones', target: '#competencias-activas-wrap', icon: 'zap' },
        { id: 'suplentes', label: 'Suplentes en espera', group: 'Operaciones', module: 'operaciones', target: '#suplentes-espera-wrap', icon: 'users' },
        { id: 'chats', label: 'Negociaciones guiadas', group: 'Operaciones', module: 'operaciones', target: '#conversaciones-ruana-wrap', icon: 'message' },
        { id: 'centro-comunicacion', label: 'Centro de comunicación', group: 'Operaciones', module: 'operaciones', target: '#centro-comunicacion-admin-wrap', icon: 'message' },
        { id: 'aliados', label: 'Control de aliados', group: 'Red', module: 'red', target: '#control-aliados-wrap', icon: 'network' },
        { id: 'aliados-eliminados', label: 'Aliados eliminados', group: 'Red', module: 'red', target: '#aliados-eliminados-wrap', icon: 'trash' },
        { id: 'trazabilidad', label: 'Trazabilidad', group: 'Sistema', module: 'sistema', target: '.eventos-trazabilidad', icon: 'list' },
        { id: 'metodos-pago', label: 'Métodos de pago', group: 'Sistema', module: 'sistema', target: '#metodos-pago-admin-wrap', icon: 'wallet' },
        { id: 'acciones', label: 'Acciones admin', group: 'Sistema', module: 'sistema', target: '#acciones-admin-wrap', icon: 'settings' }
    ];

    let currentModule = 'resumen';
    let scrollSpyObserver = null;

    const ADMIN_DELETE_MOTIVO = 'Gestionado desde panel de administración.';

    async function apiRechazarAliado(panel, codigo) {
        const r = await fetch('/api/admin/rechazar-aliado', {
            method: 'POST',
            credentials: 'same-origin',
            headers: panel.getAuthHeaders(),
            body: JSON.stringify({ codigo })
        });
        if (r.status === 401) { panel._adminSessionExpired(); return false; }
        const data = await r.json().catch(() => ({}));
        return r.ok && data.status === 'success';
    }

    async function apiRechazarPago(panel, contactoId, motivo) {
        const r = await fetch(`/api/admin/contactos/${contactoId}/estado-pago`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: panel.getAuthHeaders(),
            body: JSON.stringify({ estado_pago: 'rechazado', motivo: motivo || ADMIN_DELETE_MOTIVO })
        });
        if (r.status === 401) { panel._adminSessionExpired(); return false; }
        const data = await r.json().catch(() => ({}));
        return r.ok && data.status === 'success';
    }

    async function apiResolverConflicto(panel, conflictId) {
        const r = await fetch(`/api/admin/payment-conflicts/${conflictId}/resolver`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: panel.getAuthHeaders(),
            body: JSON.stringify({ decision: 'rechazado', comentario: ADMIN_DELETE_MOTIVO })
        });
        if (r.status === 401) { panel._adminSessionExpired(); return false; }
        const data = await r.json().catch(() => ({}));
        return r.ok && data.status === 'success';
    }

    async function apiDesactivarCampana(panel, codigo) {
        const r = await fetch('/api/admin/invitacion-campanas/' + encodeURIComponent(codigo) + '/desactivar', {
            method: 'POST',
            credentials: 'same-origin',
            headers: panel.getAuthHeaders()
        });
        if (r.status === 401) { panel._adminSessionExpired(); return false; }
        if (r.status === 403) { panel.showToast('Sin permiso de escritura.', 'error'); return false; }
        const data = await r.json().catch(() => ({}));
        return r.ok && data.status === 'success';
    }

    function getRowCodigo(tr) {
        return tr.querySelector('[data-codigo]')?.getAttribute('data-codigo')
            || tr.querySelector('.btn-rechazar-pendiente')?.getAttribute('data-codigo')
            || tr.querySelector('td:nth-child(3)')?.textContent?.trim();
    }

    function getRowContactoId(tr) {
        return tr.getAttribute('data-contacto-id')
            || tr.querySelector('[data-contacto-id]')?.getAttribute('data-contacto-id');
    }

    function getRowConflictId(tr) {
        return tr.getAttribute('data-conflict-id') || tr.dataset.conflictId;
    }

    function getRowSolicitudId(tr) {
        return tr.dataset.solicitudId
            || tr.querySelector('[data-solicitud-id]')?.getAttribute('data-solicitud-id')
            || tr.querySelector('td:nth-child(2)')?.textContent?.trim();
    }

    const SECTION_REGISTRY = [
        { wrapId: 'pendientes-validacion-wrap', tbodyId: 'tbody-pendientes-validacion', deletable: true },
        { wrapId: 'conflictos-pago-wrap', tbodyId: 'tbody-conflictos-pago', deletable: true },
        { wrapId: 'pagos-apoyo-wrap', tbodyId: 'tbody-pagos-apoyo', deletable: true },
        { wrapId: 'pagos-en-revision-wrap', tbodyId: 'tbody-pagos-en-revision', deletable: true },
        { wrapId: 'solicitudes-admin-wrap', tbodyId: 'tbody-solicitudes-admin', deletable: true },
        { wrapId: 'admin-campanas-invitacion-panel', tbodyId: 'admin-campanas-invitacion-tbody', deletable: true },
        { wrapId: 'competencias-activas-wrap', tbodyId: 'tbody-competencias-activas', deletable: false, note: 'Solo lectura' },
        { wrapId: 'competencias-pendientes-wrap', tbodyId: 'tbody-competencias-pendientes', deletable: false, note: 'Solo lectura' },
        { wrapId: 'competencias-historial-wrap', tbodyId: 'tbody-competencias-historial', deletable: false, note: 'Auditoría — solo lectura' },
        { wrapId: 'suplentes-espera-wrap', tbodyId: 'tbody-suplentes-espera', deletable: false, note: 'Use «Incorporar» por fila' },
        { wrapId: 'conversaciones-ruana-wrap', tbodyId: 'tbody-conversaciones', deletable: false, note: 'Auditoría — solo lectura' }
    ];

    const BULK_CONFIG = {
        'tbody-pendientes-validacion': {
            name: 'pendientes de validación',
            critical: true,
            rowLabel: (tr) => getRowCodigo(tr) || tr.dataset.id || 'registro',
            rowDelete: {
                consequences: [
                    'El aliado será rechazado y no podrá acceder al panel.',
                    'No hay restauración desde este panel.'
                ],
                confirmPhrase: 'ELIMINAR',
                run: async (panel, tr) => {
                    const codigo = getRowCodigo(tr);
                    if (!codigo) return;
                    if (await apiRechazarAliado(panel, codigo) && tr.parentNode) tr.remove();
                    panel.cargarDesdeApi();
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: [
                        'Los aliados seleccionados serán rechazados.',
                        'No podrán acceder al panel.'
                    ],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const codigo = getRowCodigo(tr);
                            if (codigo && await apiRechazarAliado(panel, codigo) && tr.parentNode) tr.remove();
                        }
                        panel.cargarDesdeApi();
                    }
                },
                {
                    id: 'activar',
                    label: 'Activar seleccionados',
                    consequences: [
                        'Los aliados seleccionados podrán acceder al panel con su código.',
                        'Esta acción no se puede deshacer desde el panel.'
                    ],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = tr.dataset.id;
                            if (id) await panel.activarAliadoPendiente(Number(id), tr);
                        }
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: [
                    'Se rechazarán TODOS los aliados pendientes visibles.',
                    'Operación crítica e irreversible desde el panel.'
                ],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const codigo = getRowCodigo(tr);
                        if (codigo) await apiRechazarAliado(panel, codigo);
                    }
                    panel.cargarDesdeApi();
                }
            }
        },
        'admin-campanas-invitacion-tbody': {
            name: 'códigos multiuso',
            critical: true,
            rowLabel: (tr) => tr.querySelector('.btn-desactivar-campana')?.getAttribute('data-codigo') || tr.querySelector('td:nth-child(2)')?.textContent?.trim() || 'campaña',
            rowDelete: {
                consequences: ['El código dejará de validar inmediatamente.', 'Los usos consumidos no se revierten.'],
                confirmPhrase: 'ELIMINAR',
                run: async (panel, tr) => {
                    const codigo = tr.querySelector('.btn-desactivar-campana')?.getAttribute('data-codigo') || tr.querySelector('td:nth-child(2)')?.textContent?.trim();
                    if (!codigo) return;
                    if (await apiDesactivarCampana(panel, codigo) && tr.parentNode) tr.remove();
                    panel.cargarDesdeApi();
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: ['Los códigos dejarán de validar.', 'Los usos ya consumidos no se revierten.'],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const codigo = tr.querySelector('.btn-desactivar-campana')?.getAttribute('data-codigo') || tr.querySelector('td:nth-child(2)')?.textContent?.trim();
                            if (codigo && await apiDesactivarCampana(panel, codigo) && tr.parentNode) tr.remove();
                        }
                        panel.cargarDesdeApi();
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: ['Se desactivarán TODOS los códigos multiuso visibles.'],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const codigo = tr.querySelector('.btn-desactivar-campana')?.getAttribute('data-codigo') || tr.querySelector('td:nth-child(2)')?.textContent?.trim();
                        if (codigo) await apiDesactivarCampana(panel, codigo);
                    }
                    panel.cargarDesdeApi();
                }
            }
        },
        'tbody-solicitudes-admin': {
            name: 'solicitudes',
            critical: false,
            rowLabel: (tr) => `solicitud #${getRowSolicitudId(tr)}`,
            rowDelete: {
                consequences: ['La solicitud pasará a estado atendida.', 'Permanece en el historial.'],
                run: async (panel, tr) => {
                    const id = getRowSolicitudId(tr);
                    if (id) await panel.marcarSolicitudAtendidaAdmin(id, tr);
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: ['Las solicitudes pasarán a estado atendida (archivadas en la lista).'],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowSolicitudId(tr);
                            if (id) await panel.marcarSolicitudAtendidaAdmin(id, tr);
                        }
                    }
                },
                {
                    id: 'atender',
                    label: 'Marcar atendidas',
                    consequences: [
                        'Las solicitudes pasarán a estado atendida.',
                        'No elimina el historial, solo actualiza el estado.'
                    ],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowSolicitudId(tr);
                            if (id) await panel.marcarSolicitudAtendidaAdmin(id, tr);
                        }
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: ['Todas las solicitudes visibles se marcarán como atendidas.'],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const id = getRowSolicitudId(tr);
                        if (id) await panel.marcarSolicitudAtendidaAdmin(id, tr);
                    }
                }
            }
        },
        'tbody-conflictos-pago': {
            name: 'conflictos de pago',
            critical: true,
            rowLabel: (tr) => `conflicto #${getRowConflictId(tr)}`,
            rowDelete: {
                consequences: ['El conflicto se cerrará como rechazado.', 'Afecta al contacto y al score asociado.'],
                confirmPhrase: 'ELIMINAR',
                run: async (panel, tr) => {
                    const id = getRowConflictId(tr);
                    if (!id) return;
                    if (await apiResolverConflicto(panel, id) && tr.parentNode) tr.remove();
                    panel.cargarDesdeApi();
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: ['Los conflictos se resolverán como rechazados.'],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowConflictId(tr);
                            if (id && await apiResolverConflicto(panel, id) && tr.parentNode) tr.remove();
                        }
                        panel.cargarDesdeApi();
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: ['Todos los conflictos visibles se cerrarán como rechazados.'],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const id = getRowConflictId(tr);
                        if (id) await apiResolverConflicto(panel, id);
                    }
                    panel.cargarDesdeApi();
                }
            }
        },
        'tbody-pagos-apoyo': {
            name: 'pagos Apoyo RUANA',
            critical: true,
            rowLabel: (tr) => `contacto #${getRowContactoId(tr) || '?'}`,
            rowDelete: {
                consequences: ['El pago se marcará como rechazado.', 'El profesional puede volver a subir comprobante.'],
                confirmPhrase: 'ELIMINAR',
                run: async (panel, tr) => {
                    const id = getRowContactoId(tr);
                    if (!id) return;
                    if (await apiRechazarPago(panel, id) && tr.parentNode) tr.remove();
                    panel.cargarDesdeApi();
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: ['Los pagos seleccionados se rechazarán.'],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowContactoId(tr);
                            if (id && await apiRechazarPago(panel, id) && tr.parentNode) tr.remove();
                        }
                        panel.cargarDesdeApi();
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: ['Todos los pagos Apoyo visibles se rechazarán.'],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const id = getRowContactoId(tr);
                        if (id) await apiRechazarPago(panel, id);
                    }
                    panel.cargarDesdeApi();
                }
            }
        },
        'tbody-pagos-en-revision': {
            name: 'pagos en revisión',
            critical: true,
            rowLabel: (tr) => `contacto #${getRowContactoId(tr) || '?'}`,
            rowDelete: {
                consequences: ['El pago en revisión se rechazará.', 'Se notificará al aliado afectado.'],
                confirmPhrase: 'ELIMINAR',
                run: async (panel, tr) => {
                    const id = getRowContactoId(tr);
                    if (!id) return;
                    if (await apiRechazarPago(panel, id) && tr.parentNode) tr.remove();
                    panel.cargarDesdeApi();
                }
            },
            actions: [
                {
                    id: 'eliminar',
                    label: 'Eliminar seleccionados',
                    danger: true,
                    confirmPhrase: 'ELIMINAR',
                    consequences: ['Los pagos seleccionados se rechazarán.'],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowContactoId(tr);
                            if (id && await apiRechazarPago(panel, id) && tr.parentNode) tr.remove();
                        }
                        panel.cargarDesdeApi();
                    }
                },
                {
                    id: 'aprobar',
                    label: 'Aprobar pagos seleccionados',
                    consequences: [
                        'Los pagos pasarán a estado «pagado».',
                        'Esta acción afecta el score y la trazabilidad del contacto.'
                    ],
                    run: async (panel, rows) => {
                        for (const tr of rows) {
                            const id = getRowContactoId(tr);
                            if (id) await panel.cambiarEstadoPagoContacto(id, 'pagado', tr);
                        }
                    }
                }
            ],
            allAction: {
                id: 'eliminar-todos',
                label: 'Eliminar todos',
                danger: true,
                confirmPhrase: 'ELIMINAR TODOS',
                consequences: ['Todos los pagos en revisión visibles se rechazarán.'],
                run: async (panel, tbody) => {
                    const rows = Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td'));
                    for (const tr of rows) {
                        const id = getRowContactoId(tr);
                        if (id) await apiRechazarPago(panel, id);
                    }
                    panel.cargarDesdeApi();
                }
            }
        }
    };

    const ICONS = {
        grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
        activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
        heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
        'user-check': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/></svg>',
        alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        credit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>',
        clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>',
        zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        message: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        network: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><line x1="12" y1="8" x2="5" y2="16"/><line x1="12" y1="8" x2="19" y2="16"/></svg>',
        list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
        wallet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4"/><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/></svg>',
        settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
    };

    const auditLog = [];
    let adminCodigo = 'admin';
    let enhanceTimer = null;

    function getPanel() {
        return window._ruanaAdminPanel || null;
    }

    function formatTime(date) {
        return date.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'medium' });
    }

    function logAudit(action, detail, meta) {
        const entry = {
            at: new Date(),
            admin: adminCodigo,
            action,
            detail,
            meta: meta || {}
        };
        auditLog.unshift(entry);
        if (auditLog.length > 200) auditLog.pop();
        renderAuditList();
    }

    function renderAuditList() {
        const list = document.getElementById('adminAuditList');
        if (!list) return;
        if (!auditLog.length) {
            list.innerHTML = '<p style="color:#71717a;font-size:0.8rem;padding:8px;">Sin acciones en esta sesión.</p>';
            return;
        }
        list.innerHTML = auditLog.slice(0, 50).map((e) => `
            <div class="admin-audit-entry">
                <time>${formatTime(e.at)}</time>
                <div><strong>${escapeHtml(e.admin)}</strong> — ${escapeHtml(e.action)}</div>
                <div style="color:#a1a1aa;margin-top:4px;">${escapeHtml(e.detail)}</div>
            </div>
        `).join('');
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function buildModules() {
        const dataContent = document.querySelector('.admin-data-content');
        if (!dataContent || dataContent.querySelector('.admin-module')) return;

        // Ensure acciones has a stable id even if markup drifts
        const acciones = dataContent.querySelector('.acciones-admin:not(#metodos-pago-admin-wrap)');
        if (acciones && !acciones.id) acciones.id = 'acciones-admin-wrap';

        MODULE_DEFS.forEach((mod, idx) => {
            const els = mod.targets
                .map((sel) => dataContent.querySelector(sel))
                .filter(Boolean);
            if (!els.length) return;

            const pane = document.createElement('section');
            pane.className = 'admin-module' + (idx === 0 ? ' is-active' : '');
            pane.setAttribute('data-admin-module', mod.id);
            pane.setAttribute('aria-hidden', idx === 0 ? 'false' : 'true');
            pane.innerHTML = `
                <header class="admin-module-header">
                    <p class="admin-module-kicker">${escapeHtml(mod.kicker)}</p>
                    <h2 class="admin-module-title">${escapeHtml(mod.label)}</h2>
                    <p class="admin-module-subtitle">${escapeHtml(mod.subtitle)}</p>
                </header>
                <div class="admin-module-body"></div>
            `;
            const body = pane.querySelector('.admin-module-body');
            els[0].parentNode.insertBefore(pane, els[0]);
            els.forEach((el) => body.appendChild(el));
        });
    }

    function showModule(moduleId, options) {
        const opts = options || {};
        const target = MODULE_DEFS.some((m) => m.id === moduleId) ? moduleId : 'resumen';
        currentModule = target;

        document.querySelectorAll('.admin-module').forEach((pane) => {
            const active = pane.getAttribute('data-admin-module') === target;
            pane.classList.toggle('is-active', active);
            pane.setAttribute('aria-hidden', active ? 'false' : 'true');
        });

        document.querySelectorAll('[data-admin-module-nav]').forEach((btn) => {
            btn.classList.toggle('is-active', btn.getAttribute('data-admin-module-nav') === target);
        });

        renderModuleSwitcher();
        const search = document.getElementById('adminNavSearch');
        renderNavItems(search ? search.value : '');

        if (!opts.skipHash) {
            try {
                const hash = '#' + target;
                if (location.hash !== hash) history.replaceState(null, '', hash);
            } catch (_) { /* ignore */ }
        }

        if (!opts.skipScroll) {
            window.scrollTo({ top: 0, behavior: opts.instant ? 'auto' : 'smooth' });
        }

        setupScrollSpy();
        return target;
    }

    function ensureModuleForTarget(selector) {
        const section = NAV_SECTIONS.find((s) => s.target === selector);
        if (section && section.module) {
            showModule(section.module, { skipScroll: true, instant: true });
            return section.module;
        }
        const el = document.querySelector(selector);
        if (!el) return null;
        const pane = el.closest('.admin-module');
        if (pane) {
            const mod = pane.getAttribute('data-admin-module');
            showModule(mod, { skipScroll: true, instant: true });
            return mod;
        }
        return null;
    }

    function navigateTo(selector) {
        ensureModuleForTarget(selector);
        const target = document.querySelector(selector);
        if (!target) return;
        requestAnimationFrame(() => {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        const nav = document.getElementById('adminSidebarNav');
        if (nav) {
            nav.querySelectorAll('.admin-nav-item').forEach((b) => {
                b.classList.toggle('is-active', b.getAttribute('data-nav-target') === selector);
            });
        }
        document.getElementById('adminSidebar')?.classList.remove('is-mobile-open');
    }

    function setupScrollSpy() {
        if (scrollSpyObserver) {
            scrollSpyObserver.disconnect();
            scrollSpyObserver = null;
        }
        if (typeof IntersectionObserver === 'undefined') return;
        const activePane = document.querySelector('.admin-module.is-active');
        if (!activePane) return;
        const sections = NAV_SECTIONS.filter((s) => s.module === currentModule);
        const elements = sections
            .map((s) => ({ section: s, el: document.querySelector(s.target) }))
            .filter((x) => x.el);

        scrollSpyObserver = new IntersectionObserver((entries) => {
            const visible = entries
                .filter((e) => e.isIntersecting)
                .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
            if (!visible.length) return;
            const el = visible[0].target;
            const match = elements.find((x) => x.el === el);
            if (!match) return;
            const nav = document.getElementById('adminSidebarNav');
            if (!nav) return;
            nav.querySelectorAll('.admin-nav-item').forEach((b) => {
                b.classList.toggle('is-active', b.getAttribute('data-nav-target') === match.section.target);
            });
        }, { root: null, rootMargin: '-20% 0px -55% 0px', threshold: [0.1, 0.35, 0.6] });

        elements.forEach((x) => scrollSpyObserver.observe(x.el));
    }

    function buildBottomNav() {
        if (document.getElementById('adminBottomNav')) return;
        const nav = document.createElement('nav');
        nav.className = 'admin-shell-bottom';
        nav.id = 'adminBottomNav';
        nav.setAttribute('aria-label', 'Navegación de módulos');
        nav.innerHTML = MODULE_DEFS.map((mod) => `
            <button type="button" class="admin-shell-bottom-item${mod.id === 'resumen' ? ' is-active' : ''}" data-admin-module-nav="${mod.id}">
                ${ICONS[mod.icon] || ''}
                <span>${escapeHtml(mod.label)}</span>
            </button>
        `).join('');
        document.body.appendChild(nav);
        nav.querySelectorAll('[data-admin-module-nav]').forEach((btn) => {
            btn.addEventListener('click', () => {
                showModule(btn.getAttribute('data-admin-module-nav'));
            });
        });
    }

    function buildSidebar() {
        if (document.getElementById('adminSidebar')) return;

        buildModules();

        const app = document.createElement('div');
        app.className = 'admin-app';
        app.id = 'adminApp';

        const sidebar = document.createElement('aside');
        sidebar.className = 'admin-sidebar';
        sidebar.id = 'adminSidebar';
        sidebar.innerHTML = `
            <div class="admin-sidebar-brand">
                <span class="admin-sidebar-brand-name">RUANA</span>
                <span class="admin-sidebar-brand-sub">Administración</span>
            </div>
            <div class="admin-module-switcher" id="adminModuleSwitcher"></div>
            <div class="admin-sidebar-search">
                <div class="admin-sidebar-search-wrap">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <input type="search" id="adminNavSearch" placeholder="Buscar sección…" autocomplete="off" />
                </div>
            </div>
            <nav class="admin-sidebar-nav" id="adminSidebarNav"></nav>
            <div class="admin-sidebar-footer">
                <button type="button" id="adminOpenAuditBtn">Auditoría de sesión <span class="admin-kbd">⌘⇧A</span></button>
            </div>
        `;

        const main = document.createElement('main');
        main.className = 'admin-main';
        main.id = 'adminMain';

        const container = document.getElementById('admin-main-content');
        if (container && container.parentNode) {
            container.parentNode.insertBefore(app, container);
            app.appendChild(sidebar);
            app.appendChild(main);
            main.appendChild(container);
        }

        renderModuleSwitcher();
        renderNavItems();
        setupNavSearch();
        buildBottomNav();

        const hash = (location.hash || '').replace(/^#/, '');
        if (MODULE_DEFS.some((m) => m.id === hash)) {
            showModule(hash, { skipHash: true, instant: true });
        } else {
            showModule('resumen', { skipHash: false, instant: true });
        }

        // Route KPI shortcuts into modules without changing AdminPanel handlers
        document.addEventListener('click', (e) => {
            const pend = e.target.closest && e.target.closest('#indicador-pendientes-validacion');
            if (pend) {
                navigateTo('#pendientes-validacion-wrap');
                return;
            }
            const espera = e.target.closest && e.target.closest('#indicador-en-espera');
            if (espera) {
                navigateTo('#suplentes-espera-wrap');
            }
        }, true);

        window.addEventListener('hashchange', () => {
            const h = (location.hash || '').replace(/^#/, '');
            if (MODULE_DEFS.some((m) => m.id === h)) showModule(h, { skipHash: true });
        });
    }

    function renderModuleSwitcher() {
        const wrap = document.getElementById('adminModuleSwitcher');
        if (!wrap) return;
        wrap.innerHTML = MODULE_DEFS.map((mod) => `
            <button type="button" class="admin-module-chip${mod.id === currentModule ? ' is-active' : ''}" data-admin-module-nav="${mod.id}">
                ${ICONS[mod.icon] || ''}
                <span>${escapeHtml(mod.label)}</span>
            </button>
        `).join('');
        wrap.querySelectorAll('[data-admin-module-nav]').forEach((btn) => {
            btn.addEventListener('click', () => showModule(btn.getAttribute('data-admin-module-nav')));
        });
    }

    function renderNavItems(filter) {
        const nav = document.getElementById('adminSidebarNav');
        if (!nav) return;
        const q = (filter || '').trim().toLowerCase();
        const groups = {};
        NAV_SECTIONS.forEach((s) => {
            // When not searching, only show sections of the active module
            if (!q && s.module !== currentModule) return;
            if (q && !s.label.toLowerCase().includes(q) && !s.group.toLowerCase().includes(q)) return;
            if (!groups[s.group]) groups[s.group] = [];
            groups[s.group].push(s);
        });
        const groupKeys = Object.keys(groups);
        if (!groupKeys.length) {
            nav.innerHTML = '<p class="admin-nav-empty">Sin resultados</p>';
            return;
        }
        nav.innerHTML = groupKeys.map((group) => {
            const items = groups[group].map((s) => {
                const badgeEl = s.badge ? document.querySelector(s.badge) : null;
                const badgeVal = badgeEl ? badgeEl.textContent.trim() : '';
                const hasBadge = badgeVal && badgeVal !== '—' && badgeVal !== '0';
                return `<button type="button" class="admin-nav-item" data-nav-target="${s.target}" data-nav-module="${s.module}">
                    ${ICONS[s.icon] || ''}
                    <span>${escapeHtml(s.label)}</span>
                    ${hasBadge ? `<span class="admin-nav-badge has-items">${escapeHtml(badgeVal)}</span>` : ''}
                </button>`;
            }).join('');
            return `<div class="admin-nav-group-label">${escapeHtml(group)}</div>${items}`;
        }).join('');

        nav.querySelectorAll('.admin-nav-item').forEach((btn) => {
            btn.addEventListener('click', () => {
                navigateTo(btn.getAttribute('data-nav-target'));
            });
        });
    }

    function setupNavSearch() {
        const input = document.getElementById('adminNavSearch');
        if (!input) return;
        input.addEventListener('input', () => renderNavItems(input.value));
    }

    function buildDangerModal() {
        if (document.getElementById('adminDangerModal')) return;
        const modal = document.createElement('div');
        modal.className = 'admin-danger-modal';
        modal.id = 'adminDangerModal';
        modal.innerHTML = `
            <div class="admin-danger-card" role="dialog" aria-modal="true" aria-labelledby="adminDangerTitle">
                <h3 id="adminDangerTitle">Confirmar acción</h3>
                <p id="adminDangerDesc"></p>
                <div class="admin-danger-consequences" id="adminDangerConsequences"></div>
                <div id="adminDangerStep2" style="display:none;">
                    <p style="font-size:0.82rem;color:#fca5a5;margin-bottom:8px;">Escribe la frase de confirmación para continuar:</p>
                    <p style="font-size:0.78rem;color:#a1a1aa;margin-bottom:8px;font-family:monospace;" id="adminDangerPhrase"></p>
                    <input type="text" class="admin-danger-confirm-input" id="adminDangerInput" autocomplete="off" />
                </div>
                <div class="admin-danger-actions">
                    <button type="button" class="admin-bulk-btn admin-bulk-clear" id="adminDangerCancel">Cancelar</button>
                    <button type="button" class="admin-bulk-btn" id="adminDangerContinue">Continuar</button>
                    <button type="button" class="admin-bulk-btn is-danger" id="adminDangerConfirm" style="display:none;">Confirmar</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeDangerModal();
        });
        document.getElementById('adminDangerCancel')?.addEventListener('click', closeDangerModal);
    }

    function buildAuditDrawer() {
        if (document.getElementById('adminAuditDrawer')) return;
        const drawer = document.createElement('aside');
        drawer.className = 'admin-audit-drawer';
        drawer.id = 'adminAuditDrawer';
        drawer.innerHTML = `
            <div class="admin-audit-header">
                <h3>Auditoría de sesión</h3>
                <button type="button" class="admin-bulk-btn admin-bulk-clear" id="adminCloseAuditBtn">Cerrar</button>
            </div>
            <div class="admin-audit-list" id="adminAuditList"></div>
        `;
        document.body.appendChild(drawer);
        document.getElementById('adminOpenAuditBtn')?.addEventListener('click', () => toggleAudit(true));
        document.getElementById('adminCloseAuditBtn')?.addEventListener('click', () => toggleAudit(false));
    }

    function toggleAudit(open) {
        document.getElementById('adminAuditDrawer')?.classList.toggle('is-open', open);
    }

    let dangerResolve = null;
    let dangerState = { step: 1 };

    function closeDangerModal() {
        const modal = document.getElementById('adminDangerModal');
        if (modal) modal.classList.remove('is-open');
        dangerResolve = null;
        dangerState = { step: 1 };
    }

    function confirmDanger({ title, description, consequences, confirmPhrase }) {
        buildDangerModal();
        return new Promise((resolve) => {
            dangerResolve = resolve;
            dangerState = { step: 1, confirmPhrase: confirmPhrase || null };
            const modal = document.getElementById('adminDangerModal');
            const step2 = document.getElementById('adminDangerStep2');
            const input = document.getElementById('adminDangerConfirm');
            const continueBtn = document.getElementById('adminDangerContinue');
            const confirmBtn = document.getElementById('adminDangerConfirm');
            document.getElementById('adminDangerTitle').textContent = title || 'Confirmar acción';
            document.getElementById('adminDangerDesc').textContent = description || '';
            const consEl = document.getElementById('adminDangerConsequences');
            consEl.innerHTML = consequences && consequences.length
                ? '<strong>Consecuencias:</strong><ul>' + consequences.map((c) => `<li>${escapeHtml(c)}</li>`).join('') + '</ul>'
                : '';
            step2.style.display = 'none';
            confirmBtn.style.display = 'none';
            continueBtn.style.display = '';
            input.value = '';
            modal.classList.add('is-open');

            const onContinue = () => {
                if (!confirmPhrase) {
                    closeDangerModal();
                    resolve(true);
                    return;
                }
                dangerState.step = 2;
                step2.style.display = 'block';
                continueBtn.style.display = 'none';
                confirmBtn.style.display = '';
                document.getElementById('adminDangerPhrase').textContent = confirmPhrase;
                document.getElementById('adminDangerInput')?.focus();
            };

            const onConfirm = () => {
                const val = (document.getElementById('adminDangerInput')?.value || '').trim();
                if (val !== confirmPhrase) {
                    getPanel()?.showToast?.('La frase de confirmación no coincide.', 'error');
                    return;
                }
                closeDangerModal();
                resolve(true);
            };

            continueBtn.onclick = onContinue;
            confirmBtn.onclick = onConfirm;
        });
    }

    function getSelectedRows(tbody) {
        return Array.from(tbody.querySelectorAll('tr.is-selected'));
    }

    function updateBulkToolbar(tbodyId) {
        const config = BULK_CONFIG[tbodyId];
        if (!config) return;
        const tbody = document.getElementById(tbodyId);
        const toolbar = document.getElementById(`bulk-toolbar-${tbodyId}`);
        if (!tbody || !toolbar) return;
        const selected = getSelectedRows(tbody);
        const countEl = toolbar.querySelector('.admin-bulk-count');
        if (countEl) countEl.textContent = `${selected.length} seleccionado${selected.length === 1 ? '' : 's'}`;
        toolbar.classList.toggle('is-visible', selected.length > 0);
    }

    function enhanceTable(tbodyId) {
        const config = BULK_CONFIG[tbodyId];
        if (!config) return;
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;

        const table = tbody.closest('table');
        if (!table) return;

        const wrap = table.closest('.movimiento-24h-tabla-scroll, .tabla-scroll, .admin-tabla-wrap') || table.parentElement;
        if (wrap && !wrap.classList.contains('admin-table-shell')) {
            wrap.classList.add('admin-table-shell');
        }

        let toolbar = document.getElementById(`bulk-toolbar-${tbodyId}`);
        if (!toolbar && wrap) {
            toolbar = document.createElement('div');
            toolbar.className = 'admin-bulk-toolbar';
            toolbar.id = `bulk-toolbar-${tbodyId}`;
            toolbar.innerHTML = `<span class="admin-bulk-count">0 seleccionados</span>`;
            config.actions.forEach((action) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'admin-bulk-btn' + (action.danger ? ' is-danger' : '');
                btn.textContent = action.label;
                btn.addEventListener('click', () => runBulkAction(tbodyId, action));
                toolbar.appendChild(btn);
            });
            if (config.allAction) {
                const allBtn = document.createElement('button');
                allBtn.type = 'button';
                allBtn.className = 'admin-bulk-btn is-danger';
                allBtn.textContent = config.allAction.label;
                allBtn.addEventListener('click', () => runBulkAllAction(tbodyId, config.allAction));
                toolbar.appendChild(allBtn);
            }
            const clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.className = 'admin-bulk-btn admin-bulk-clear';
            clearBtn.textContent = 'Limpiar selección';
            clearBtn.addEventListener('click', () => {
                tbody.querySelectorAll('tr.is-selected').forEach((tr) => {
                    tr.classList.remove('is-selected');
                    const cb = tr.querySelector('.admin-row-checkbox');
                    if (cb) cb.checked = false;
                });
                const headCb = table.querySelector('thead .admin-row-checkbox');
                if (headCb) headCb.checked = false;
                updateBulkToolbar(tbodyId);
            });
            toolbar.appendChild(clearBtn);
            wrap.parentNode.insertBefore(toolbar, wrap);
        }

        const headerRow = table.querySelector('thead tr');
        if (headerRow && !headerRow.querySelector('.admin-bulk-cell')) {
            const th = document.createElement('th');
            th.className = 'admin-bulk-cell';
            th.innerHTML = '<input type="checkbox" class="admin-row-checkbox admin-select-all" aria-label="Seleccionar todos" />';
            headerRow.insertBefore(th, headerRow.firstChild);
            th.querySelector('.admin-select-all')?.addEventListener('change', (e) => {
                const checked = e.target.checked;
                tbody.querySelectorAll('tr').forEach((tr) => {
                    if (!tr.querySelector('td')) return;
                    tr.classList.toggle('is-selected', checked);
                    const cb = tr.querySelector('.admin-row-checkbox');
                    if (cb) cb.checked = checked;
                });
                updateBulkToolbar(tbodyId);
            });
        }

        tbody.querySelectorAll('tr').forEach((tr) => {
            if (!tr.querySelector('td')) return;
            if (!tr.querySelector('.admin-bulk-cell')) {
                const td = document.createElement('td');
                td.className = 'admin-bulk-cell';
                td.innerHTML = '<input type="checkbox" class="admin-row-checkbox" aria-label="Seleccionar fila" />';
                tr.insertBefore(td, tr.firstChild);
                const cb = td.querySelector('.admin-row-checkbox');
                cb.addEventListener('change', () => {
                    tr.classList.toggle('is-selected', cb.checked);
                    updateBulkToolbar(tbodyId);
                });
            }
            injectRowDeleteButton(tr, tbodyId, config);
        });

        if (config.rowDelete && headerRow && !headerRow.querySelector('.admin-delete-cell')) {
            const thDel = document.createElement('th');
            thDel.className = 'admin-delete-cell';
            thDel.textContent = 'Eliminar';
            headerRow.appendChild(thDel);
        }
    }

    function injectRowDeleteButton(tr, tbodyId, config) {
        if (!config?.rowDelete) return;
        const existing = tr.querySelector('.admin-delete-cell .btn-row-delete');
        if (existing) return;
        const panel = getPanel();
        if (!panel) return;

        let tdDel = tr.querySelector('.admin-delete-cell');
        if (!tdDel) {
            tdDel = document.createElement('td');
            tdDel.className = 'admin-delete-cell';
            tr.appendChild(tdDel);
        }

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-accion danger btn-row-delete';
        btn.textContent = 'Eliminar';
        btn.title = 'Eliminar este registro';
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            await runRowDelete(tbodyId, tr, config.rowDelete);
        });
        tdDel.appendChild(btn);
    }

    async function runRowDelete(tbodyId, tr, rowDelete) {
        const panel = getPanel();
        const config = BULK_CONFIG[tbodyId];
        if (!panel || !config) return;

        const label = config.rowLabel(tr);
        const ok = await confirmDanger({
            title: 'Eliminar registro',
            description: `Vas a eliminar: ${label}.`,
            consequences: rowDelete.consequences || [],
            confirmPhrase: rowDelete.confirmPhrase || (config.critical ? 'ELIMINAR' : null)
        });
        if (!ok) return;

        logAudit('Eliminar registro', label, { tbodyId });
        await rowDelete.run(panel, tr);
        scheduleEnhance();
    }

    function injectSectionHeaders() {
        SECTION_REGISTRY.forEach((sec) => {
            const wrap = document.getElementById(sec.wrapId);
            if (!wrap) return;
            const h2 = wrap.querySelector(':scope > .seccion-titulo');
            if (!h2) return;
            if (h2.closest('.admin-section-header')) return;

            const header = document.createElement('div');
            header.className = 'admin-section-header';
            h2.parentNode.insertBefore(header, h2);
            header.appendChild(h2);

            const actions = document.createElement('div');
            actions.className = 'admin-section-actions';

            if (sec.deletable && BULK_CONFIG[sec.tbodyId]) {
                const cfg = BULK_CONFIG[sec.tbodyId];
                const deleteAct = cfg.actions.find((a) => a.id === 'eliminar');

                const btnSel = document.createElement('button');
                btnSel.type = 'button';
                btnSel.className = 'admin-section-btn is-danger';
                btnSel.textContent = 'Eliminar seleccionados';
                btnSel.addEventListener('click', () => {
                    const tbody = document.getElementById(sec.tbodyId);
                    const panel = getPanel();
                    if (!tbody || !panel) return;
                    const rows = getSelectedRows(tbody);
                    if (!rows.length) {
                        panel.showToast('Selecciona al menos un registro con la casilla.', 'error');
                        return;
                    }
                    if (deleteAct) runBulkAction(sec.tbodyId, deleteAct);
                });
                actions.appendChild(btnSel);

                if (cfg.allAction) {
                    const btnAll = document.createElement('button');
                    btnAll.type = 'button';
                    btnAll.className = 'admin-section-btn is-danger-outline';
                    btnAll.textContent = 'Eliminar todos';
                    btnAll.addEventListener('click', () => runBulkAllAction(sec.tbodyId, cfg.allAction));
                    actions.appendChild(btnAll);
                }
            } else if (sec.note) {
                const note = document.createElement('span');
                note.className = 'admin-section-note';
                note.textContent = sec.note;
                actions.appendChild(note);
            }

            header.appendChild(actions);
        });
    }

    async function runBulkAction(tbodyId, action) {
        const panel = getPanel();
        if (!panel) return;
        const tbody = document.getElementById(tbodyId);
        const rows = getSelectedRows(tbody);
        if (!rows.length) return;

        const config = BULK_CONFIG[tbodyId];
        const labels = rows.map((tr) => config.rowLabel(tr)).slice(0, 5);
        const more = rows.length > 5 ? ` y ${rows.length - 5} más` : '';
        const ok = await confirmDanger({
            title: action.label,
            description: `Vas a aplicar esta acción a ${rows.length} elemento(s): ${labels.join(', ')}${more}.`,
            consequences: action.consequences || [],
            confirmPhrase: action.danger ? (action.confirmPhrase || 'CONFIRMAR') : null
        });
        if (!ok) return;

        logAudit(action.label, `${rows.length} registro(s) en ${config.name}`, { tbodyId, count: rows.length });
        await action.run(panel, rows);
        rows.forEach((tr) => {
            tr.classList.remove('is-selected');
            const cb = tr.querySelector('.admin-row-checkbox');
            if (cb) cb.checked = false;
        });
        updateBulkToolbar(tbodyId);
        scheduleEnhance();
    }

    async function runBulkAllAction(tbodyId, allAction) {
        const panel = getPanel();
        if (!panel) return;
        const tbody = document.getElementById(tbodyId);
        const config = BULK_CONFIG[tbodyId];
        const total = tbody ? tbody.querySelectorAll('tr td').length : 0;
        const rowCount = tbody ? Array.from(tbody.querySelectorAll('tr')).filter((tr) => tr.querySelector('td')).length : 0;
        if (!rowCount) return;

        const ok = await confirmDanger({
            title: allAction.label,
            description: `Esta operación afectará a los ${rowCount} registros visibles en ${config.name}.`,
            consequences: allAction.consequences || [],
            confirmPhrase: allAction.confirmPhrase || 'CONFIRMAR TODOS'
        });
        if (!ok) return;

        logAudit(allAction.label, `Todos los registros (${rowCount}) en ${config.name}`, { tbodyId, count: rowCount });
        await allAction.run(panel, tbody);
        scheduleEnhance();
    }

    function scheduleEnhance() {
        clearTimeout(enhanceTimer);
        enhanceTimer = setTimeout(enhanceAll, 120);
    }

    function enhanceAll() {
        injectSectionHeaders();
        Object.keys(BULK_CONFIG).forEach(enhanceTable);
        renderNavItems(document.getElementById('adminNavSearch')?.value || '');
    }

    function patchPanel(panel) {
        if (!panel || panel._adminShellPatched) return;
        panel._adminShellPatched = true;

        const originalToast = panel.showToast.bind(panel);
        panel.showToast = function (message, type) {
            if (type === 'success') logAudit('Acción completada', message);
            return originalToast(message, type);
        };

        const originalCargar = panel.cargarDesdeApi.bind(panel);
        panel.cargarDesdeApi = async function () {
            const result = await originalCargar();
            scheduleEnhance();
            return result;
        };

        fetch('/api/admin/me', {
            method: 'GET',
            credentials: 'same-origin',
            headers: typeof AdminAuthenticator !== 'undefined' ? AdminAuthenticator.getAdminAuthHeaders() : {}
        }).then((r) => r.ok ? r.json() : null).then((data) => {
            if (data && data.admin_codigo) adminCodigo = data.admin_codigo;
        }).catch(() => {});

        scheduleEnhance();
    }

    function setupTopbarExtras() {
        const actions = document.querySelector('.admin-topbar-actions');
        if (!actions || document.getElementById('adminSidebarToggle')) return;
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'admin-sidebar-toggle';
        toggle.id = 'adminSidebarToggle';
        toggle.setAttribute('aria-label', 'Abrir menú');
        toggle.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
        actions.insertBefore(toggle, actions.firstChild);
        toggle.addEventListener('click', () => {
            document.getElementById('adminSidebar')?.classList.toggle('is-mobile-open');
        });

        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                toggleAudit(true);
            }
            if (e.key === 'Escape') {
                closeDangerModal();
                toggleAudit(false);
            }
        });
    }

    function observeMutations() {
        const root = document.getElementById('admin-main-content');
        if (!root || root._adminShellObserved) return;
        root._adminShellObserved = true;
        const observer = new MutationObserver(() => scheduleEnhance());
        observer.observe(root, { childList: true, subtree: true });
    }

    function init() {
        document.documentElement.classList.add('admin-shell-enabled');
        buildSidebar();
        buildDangerModal();
        buildAuditDrawer();
        setupTopbarExtras();
        observeMutations();

        const tryPatch = () => {
            const panel = getPanel();
            if (panel) {
                patchPanel(panel);
                return true;
            }
            return false;
        };

        if (!tryPatch()) {
            const interval = setInterval(() => {
                if (tryPatch()) clearInterval(interval);
            }, 200);
            setTimeout(() => clearInterval(interval), 60000);
        }

        scheduleEnhance();
    }

    window.AdminShell = {
        init,
        enhanceAll,
        logAudit,
        confirmDanger,
        showModule,
        navigateTo
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
