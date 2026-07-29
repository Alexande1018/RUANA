/**
 * RUANA Dashboard - JavaScript
 * Capa de Presentación - Consume datos del Motor RUANA
 */

class RAUANADashboard {
    constructor() {
        this.SCORE_MAX = 500;
        this.aliados = [];
        this.filteredAliados = [];
        this.zonas = [];
        this.oficios = [];
        this.checkAccess();
        this.init();
    }

    checkAccess() {
        /**
         * Verifica que el usuario tenga código de invitación válido.
         * El dashboard sólo debe ser accesible en contextos reales.
         */
        const inviteCode = sessionStorage.getItem('ruana_codigo_aliado');
        if (!inviteCode) {
            window.location.href = '/';
        }
    }

    async init() {
        await this.loadDataFromApi();
        this.setupEventListeners();
        this.populateFilters();
        this.renderCards();
        this.updateStats();
    }

    async loadDataFromApi() {
        /**
         * Consulta la API real para obtener todos los aliados.
         */
        console.log('[DASHBOARD] Cargando datos desde API real');
        try {
            const resp = await fetch('/api/aliados/listar');
            if (!resp.ok) {
                console.error('[DASHBOARD] Error HTTP al cargar aliados:', resp.status);
                return;
            }
            const data = await resp.json();
            if (data.status !== 'success' || !Array.isArray(data.aliados)) {
                console.error('[DASHBOARD] Respuesta inválida de /api/aliados/listar', data);
                return;
            }
            this.aliados = data.aliados;
            this.filteredAliados = [...this.aliados];
            this.zonas = [...new Set(this.aliados.map(a => a.codigo_postal).filter(Boolean))];
            this.oficios = [...new Set(this.aliados.map(a => a.oficio).filter(Boolean))];
            console.log('[DASHBOARD] Datos cargados:', this.aliados.length, 'aliados');
        } catch (e) {
            console.error('[DASHBOARD] Error cargando datos desde API:', e);
        }
    }
                suplente: {
                    nombre: 'Javier Ruiz',
                    referencia: 'JR-018',
                    score: 88,
                    estado: 'recomendado',
                    razon: 'Reemplazo activo'
                }
            },
            {
                id: 4,
                nombre: 'Laura Domínguez',
                referencia: 'LD-004',
                oficio: 'Pintura',
                zona: 'Occidente',
                score: 89,
                estado: 'recomendado',
                descripcion: 'Desempeño consistente y confiable',
                especialidades: 'Pintura interior y exterior, decoración',
                contacto: '+57 300 456 7890',
                suplente: null
            },
            {
                id: 5,
                nombre: 'Francisco Gutiérrez',
                referencia: 'FG-005',
                oficio: 'Carpintería',
                zona: 'Centro',
                score: 72,
                estado: 'observacion',
                descripcion: 'Rendimiento variable, en seguimiento',
                especialidades: 'Puertas, ventanas',
                contacto: '+57 300 567 8901',
                suplente: null
            },
            {
                id: 6,
                nombre: 'Patricia Morales',
                referencia: 'PM-006',
                oficio: 'Limpieza',
                zona: 'Este',
                score: 81,
                estado: 'recomendado',
                descripcion: 'Servicio de calidad, cumplimiento total',
                especialidades: 'Limpieza residencial y comercial',
                contacto: '+57 300 678 9012',
                suplente: null
            },
            {
                id: 7,
                nombre: 'Diego Rodríguez',
                referencia: 'DR-007',
                oficio: 'Plomería',
                zona: 'Norte',
                score: 52,
                estado: 'riesgo',
                descripcion: 'Problemas de puntualidad, en revisión',
                especialidades: 'Reparación de fugas',
                contacto: '+57 300 789 0123',
                suplente: {
                    nombre: 'Andrés Pérez',
                    referencia: 'AP-015',
                    score: 91,
                    estado: 'recomendado',
                    razon: 'Reemplazo activo'
                }
            },
            {
                id: 8,
                nombre: 'Mónica Sánchez',
                referencia: 'MS-008',
                oficio: 'Electricidad',
                zona: 'Sur',
                score: 86,
                estado: 'recomendado',
                descripcion: 'Profesional confiable y experimentada',
                especialidades: 'Instalaciones comerciales, reparaciones',
                contacto: '+57 300 890 1234',
                suplente: null
            },
            {
                id: 9,
                nombre: 'Alberto Vega',
                referencia: 'AV-009',
                oficio: 'Carpintería',
                zona: 'Occidente',
                score: 77,
                estado: 'observacion',
                descripcion: 'Mejorando, resultados prometedores',
                especialidades: 'Muebles, carpintería general',
                contacto: '+57 300 901 2345',
                suplente: null
            },
            {
                id: 10,
                nombre: 'Verónica Castro',
                referencia: 'VC-010',
                oficio: 'Pintura',
                zona: 'Este',
                score: 94,
                estado: 'recomendado',
                descripcion: 'Excelencia en ejecución, altamente recomendado',
                especialidades: 'Todo tipo de pintura y acabados',
                contacto: '+57 300 012 3456',
                suplente: null
            }
        ];

        this.zonas = [...new Set(this.aliados.map(a => a.zona))].sort();
        this.oficios = [...new Set(this.aliados.map(a => a.oficio))].sort();
        this.filteredAliados = [...this.aliados];
    }

    setupEventListeners() {
        document.getElementById('filter-zona').addEventListener('change', () => this.applyFilters());
        document.getElementById('filter-oficio').addEventListener('change', () => this.applyFilters());
        document.getElementById('filter-estado').addEventListener('change', () => this.applyFilters());
        document.getElementById('filter-search').addEventListener('input', () => this.applyFilters());
        document.getElementById('sort-by').addEventListener('change', () => this.renderCards());
        document.getElementById('btn-reset-filters').addEventListener('click', () => this.resetFilters());
        document.getElementById('modal-close', { capture: true }).addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-close')) {
                this.closeModal();
            }
        }, true);
        document.getElementById('modal-detail').addEventListener('click', (e) => {
            if (e.target.id === 'modal-detail') {
                this.closeModal();
            }
        });
    }

    populateFilters() {
        // Zonas
        const zonaSelect = document.getElementById('filter-zona');
        this.zonas.forEach(zona => {
            const option = document.createElement('option');
            option.value = zona;
            option.textContent = zona;
            zonaSelect.appendChild(option);
        });

        // Oficios: siempre value y texto legible (nunca mostrar objeto)
        const oficioSelect = document.getElementById('filter-oficio');
        this.oficios.forEach(oficio => {
            const texto = typeof oficio === 'object' && oficio && oficio.nombre != null ? String(oficio.nombre) : String(oficio || '');
            if (!texto) return;
            const option = document.createElement('option');
            option.value = texto;
            option.textContent = texto;
            oficioSelect.appendChild(option);
        });
    }

    applyFilters() {
        const zona = document.getElementById('filter-zona').value;
        const oficio = document.getElementById('filter-oficio').value;
        const estado = document.getElementById('filter-estado').value;
        const search = document.getElementById('filter-search').value.toLowerCase();

        this.filteredAliados = this.aliados.filter(aliado => {
            const matchZona = !zona || aliado.zona === zona;
            const matchOficio = !oficio || aliado.oficio === oficio;
            const matchEstado = !estado || aliado.estado === estado;
            const matchSearch = !search || 
                aliado.nombre.toLowerCase().includes(search) ||
                aliado.referencia.toLowerCase().includes(search);

            return matchZona && matchOficio && matchEstado && matchSearch;
        });

        this.renderCards();
        this.updateStats();
    }

    resetFilters() {
        document.getElementById('filter-zona').value = '';
        document.getElementById('filter-oficio').value = '';
        document.getElementById('filter-estado').value = '';
        document.getElementById('filter-search').value = '';
        this.filteredAliados = [...this.aliados];
        this.renderCards();
        this.updateStats();
    }

    sortAliados() {
        const sortBy = document.getElementById('sort-by').value;
        const aliados = [...this.filteredAliados];

        switch (sortBy) {
            case 'score-desc':
                aliados.sort((a, b) => b.score - a.score);
                break;
            case 'score-asc':
                aliados.sort((a, b) => a.score - b.score);
                break;
            case 'nombre':
                aliados.sort((a, b) => a.nombre.localeCompare(b.nombre));
                break;
        }

        return aliados;
    }

    renderCards() {
        const grid = document.getElementById('cards-grid');
        const noResults = document.getElementById('no-results');
        const aliados = this.sortAliados();

        if (aliados.length === 0) {
            grid.style.display = 'none';
            noResults.style.display = 'block';
            return;
        }

        grid.style.display = 'grid';
        noResults.style.display = 'none';
        grid.innerHTML = aliados.map(aliado => this.createCardHTML(aliado)).join('');

        // Agregar event listeners a las tarjetas
        document.querySelectorAll('.card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (!e.target.closest('.status-badge')) {
                    const aliado = this.aliados.find(a => String(a.id) === String(card.dataset.id));
                    this.openModal(aliado);
                }
            });
        });
    }

    createCardHTML(aliado) {
        /**
         * Renderiza una tarjeta basada en decisiones del motor
         * Los datos provienen del Motor RUANA, no de lógica local
         */
            const estado = aliado.estado || 'activo';
            const estadoClass = `estado-${estado}`;
            const estadoLabel = this.getEstadoLabel(estado);

        const scorePct = Math.max(0, Math.min(100, (Number(aliado.score) || 0) / this.SCORE_MAX * 100));
        return `
            <div class="card ${estadoClass}" data-id="${aliado.id}">
                <div class="card-header">
                    <div>
                        <div class="card-title">${this.escapeHtml(aliado.nombre)}</div>
                        <div class="card-subtitle">${this.escapeHtml(aliado.marca)}</div>
                    </div>
                    <div class="status-badge ${aliado.estado}">
                        <span class="status-dot ${aliado.estado}"></span>
                        ${estadoLabel}
                    </div>
                </div>

                <div class="card-info">
                    <div class="info-row">
                        <span class="info-label">Oficio</span>
                        <span class="info-value">${this.escapeHtml(aliado.oficio)}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Código Postal</span>
                        <span class="info-value">${this.escapeHtml(aliado.codigo_postal || '')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Rol</span>
                        <span class="info-value">${aliado.rol}</span>
                    </div>
                </div>

                <div class="score-container">
                    <div class="score-label">Score RUANA</div>
                    <div class="score-value">${aliado.score}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${scorePct}%"></div>
                    </div>
                    <div class="score-text">${aliado.score}/${this.SCORE_MAX}</div>
                </div>
            </div>
        `;
    }

    createCardWithSuplenteHTML(aliado) {
        /**
         * En la estructura del Motor RUANA, los suplentes son aliados independientes
         * No se renderizan como subelementos sino como tarjetas separadas
         */
        return this.createCardHTML(aliado);
                            <span class="info-value">${this.escapeHtml(aliado.oficio)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Zona</span>
                            <span class="info-value">${this.escapeHtml(aliado.zona)}</span>
                        </div>
                    </div>

                    <div class="score-container">
                        <div class="score-label">Score RUANA</div>
                        <div class="score-value">${aliado.score}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: ${Math.max(0, Math.min(100, (Number(aliado.score) || 0) / this.SCORE_MAX * 100))}%"></div>
                        </div>
                        <div class="score-text">${aliado.score}/${this.SCORE_MAX}</div>
                    </div>
                </div>

                <!-- Suplente -->
                <div>
                    <div class="suplente-label">⚡ Suplente Activo</div>
                    <div class="card-header">
                        <div>
                            <div class="card-title">${this.escapeHtml(suplente.nombre)}</div>
                            <div class="card-subtitle">${this.escapeHtml(suplente.referencia)}</div>
                        </div>
                        <div class="status-badge ${suplente.estado}">
                            <span class="status-dot ${suplente.estado}"></span>
                            ${this.getEstadoLabel(suplente.estado)}
                        </div>
                    </div>

                    <div class="card-info">
                        <div class="info-row">
                            <span class="info-label">Motivo</span>
                            <span class="info-value">${this.escapeHtml(suplente.razon)}</span>
                        </div>
                    </div>

                    <div class="score-container">
                        <div class="score-label">Score RUANA</div>
                        <div class="score-value">${suplente.score}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: ${Math.max(0, Math.min(100, (Number(suplente.score) || 0) / this.SCORE_MAX * 100))}%"></div>
                        </div>
                        <div class="score-text">${suplente.score}/${this.SCORE_MAX}</div>
                    </div>
                </div>
            </div>
        `;
    }

    getEstadoLabel(estado) {
                const labels = {
                    'activo': 'Activo',
                    'inactivo': 'Inactivo',
                    'observacion': 'En Observación',
                    'riesgo': 'En Riesgo'
                };
        return labels[estado] || estado;
    }

    updateStats() {
        /**
         * Obtiene estadísticas desde la API real.
         */
        fetch('/api/stats')
            .then(r => r.json())
            .then(data => {
                if (data.status !== 'success') return;
                const total = data.total_aliados ?? 0;
                const activos = data.aliados_activos ?? 0;
                document.getElementById('total-aliados').textContent = total;
                document.getElementById('recomendados').textContent = activos;
                document.getElementById('en-riesgo').textContent = data.contactos?.contactos_en_disputa ?? 0;
            })
            .catch(err => console.error('[DASHBOARD] Error cargando stats:', err));
    }

    openModal(aliado) {
        const modal = document.getElementById('modal-detail');
        const body = document.getElementById('modal-body');

        let suplementeHTML = '';
        if (aliado.suplente) {
            suplementeHTML = `
                <div style="margin-top: 30px; padding-top: 30px; border-top: 1px solid rgba(255,255,255,0.1);">
                    <h3 style="color: #fca5a5; margin-bottom: 15px;">⚡ Suplente Activo</h3>
                    <p><strong>Nombre:</strong> ${this.escapeHtml(aliado.suplente.nombre)}</p>
                    <p><strong>Referencia:</strong> ${this.escapeHtml(aliado.suplente.referencia)}</p>
                    <p><strong>Score:</strong> ${aliado.suplente.score}/${this.SCORE_MAX}</p>
                    <p><strong>Estado:</strong> ${this.getEstadoLabel(aliado.suplente.estado)}</p>
                    <p><strong>Motivo:</strong> ${this.escapeHtml(aliado.suplente.razon)}</p>
                </div>
            `;
        }

        body.innerHTML = `
            <h2 style="margin-bottom: 20px; color: #fff;">${this.escapeHtml(aliado.nombre)}</h2>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px;">
                <div>
                    <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Referencia</p>
                    <p style="color: #22c55e; font-size: 1.1rem; font-weight: 600;">${this.escapeHtml(aliado.referencia)}</p>
                </div>
                <div>
                    <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Estado</p>
                    <p style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">${this.getEstadoLabel(aliado.estado)}</p>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px;">
                <div>
                    <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Oficio</p>
                    <p style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">${this.escapeHtml(aliado.oficio)}</p>
                </div>
                <div>
                    <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Zona</p>
                    <p style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">${this.escapeHtml(aliado.zona)}</p>
                </div>
            </div>

            <div style="margin-bottom: 25px;">
                <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Especialidades</p>
                <p style="color: #e0e0e0;">${this.escapeHtml(aliado.especialidades)}</p>
            </div>

            <div style="margin-bottom: 25px;">
                <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Descripción</p>
                <p style="color: #e0e0e0;">${this.escapeHtml(aliado.descripcion)}</p>
            </div>

            <div style="margin-bottom: 25px;">
                <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Score RUANA</p>
                <div style="font-size: 2.5rem; font-weight: 700; color: #22c55e; margin-bottom: 12px;">${aliado.score}/${this.SCORE_MAX}</div>
                <div style="background: rgba(255,255,255,0.1); height: 8px; border-radius: 4px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #22c55e 0%, #86efac 100%); height: 100%; width: ${Math.max(0, Math.min(100, (Number(aliado.score) || 0) / this.SCORE_MAX * 100))}%; border-radius: 4px;"></div>
                </div>
            </div>

            <div style="margin-bottom: 25px;">
                <p style="color: #999; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px;">Contacto</p>
                <p style="color: #e0e0e0;">${this.escapeHtml(aliado.contacto)}</p>
            </div>

            ${suplementeHTML}
        `;

        modal.style.display = 'flex';
    }

    closeModal() {
        document.getElementById('modal-detail').style.display = 'none';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

        // Inicializar cuando DOM esté listo
        document.addEventListener('DOMContentLoaded', () => {
            new RAUANADashboard();
        });
