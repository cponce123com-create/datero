/**
 * app.js — Frontend de RedCorruptela
 *
 * SPA sencillo en vanilla JavaScript que consume la API REST protegida
 * con HTTP Basic Auth. Las credenciales se almacenan en sessionStorage
 * y se envían en cada petición fetch.
 *
 * Funcionalidades:
 *  - Búsqueda por DNI o nombre
 *  - Ficha completa de persona con relaciones, parentescos inferidos y etiquetas
 *  - Modales para crear persona, relación, asignar etiqueta
 *  - Navegación entre personas haciendo clic en nombres
 *  - Toast de notificaciones
 */

/* ─── Configuración ──────────────────────────────────────────────────────── */

const API_BASE = '/api';

/**
 * Obtiene las credenciales Basic Auth.
 * Si no están en sessionStorage, las pide al usuario con un prompt.
 */
function getAuth() {
    let auth = sessionStorage.getItem('rc_auth');
    if (!auth) {
        const user = prompt('Usuario:');
        const pass = prompt('Contraseña:');
        if (!user || !pass) {
            alert('Se requieren credenciales para acceder.');
            throw new Error('Sin credenciales');
        }
        auth = btoa(user + ':' + pass);
        sessionStorage.setItem('rc_auth', auth);
    }
    return auth;
}

/**
 * Realiza una petición a la API con autenticación Basic.
 * Si la respuesta es 401, limpia las credenciales y reintenta una vez.
 */
async function apiFetch(url, options = {}) {
    const auth = getAuth();
    const headers = {
        'Authorization': 'Basic ' + auth,
        'Content-Type': 'application/json',
        ...options.headers,
    };

    let res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        // Credenciales inválidas: limpiar y pedir de nuevo
        sessionStorage.removeItem('rc_auth');
        const newAuth = getAuth();
        headers['Authorization'] = 'Basic ' + newAuth;
        res = await fetch(url, { ...options, headers });
    }

    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg = data.detail || `Error ${res.status}`;
        throw new Error(msg);
    }

    if (res.status === 204) return null;
    return res.json();
}

/* ─── Toast ──────────────────────────────────────────────────────────────── */

let toastTimer = null;

function showToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = `toast toast-${type}`;
    toast.classList.remove('hidden');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add('hidden'), 4000);
}

/* ─── Modales ────────────────────────────────────────────────────────────── */

function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// Cerrar modales con el botón X o haciendo clic fuera
document.addEventListener('click', (e) => {
    if (e.target.dataset.close) {
        closeModal(e.target.dataset.close);
    }
    if (e.target.classList.contains('modal-overlay')) {
        const modal = e.target.closest('.modal');
        if (modal) modal.classList.add('hidden');
    }
});

// Cerrar modal con Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
});

/* ─── Búsqueda ───────────────────────────────────────────────────────────── */

const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const searchResults = document.getElementById('search-results');

searchBtn.addEventListener('click', doSearch);
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
});

async function doSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    try {
        const data = await apiFetch(`${API_BASE}/personas?q=${encodeURIComponent(query)}`);

        if (data.total === 0) {
            searchResults.innerHTML = '<div class="no-results">No se encontraron resultados</div>';
            searchResults.classList.remove('hidden');
            return;
        }

        if (data.total === 1) {
            // Un solo resultado: ir directo a la ficha
            searchResults.classList.add('hidden');
            cargarFicha(data.resultados[0].dni);
            return;
        }

        // Múltiples resultados: mostrar lista
        searchResults.innerHTML = data.resultados.map(p => `
            <div class="search-result-item" data-dni="${p.dni}">
                <span><strong>${escapeHtml(p.nombre_completo)}</strong></span>
                <span class="search-result-dni">DNI: ${escapeHtml(p.dni)}</span>
            </div>
        `).join('');

        // Click en un resultado
        searchResults.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                const dni = item.dataset.dni;
                searchResults.classList.add('hidden');
                searchInput.value = '';
                cargarFicha(dni);
            });
        });

        searchResults.classList.remove('hidden');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

/* ─── Cargar Ficha de Persona ────────────────────────────────────────────── */

async function cargarFicha(dni) {
    const fichaDiv = document.getElementById('persona-ficha');
    const emptyState = document.getElementById('empty-state');

    fichaDiv.innerHTML = '<div class="loading-text"><span class="spinner"></span> Cargando ficha...</div>';
    fichaDiv.classList.remove('hidden');
    emptyState.classList.add('hidden');

    try {
        const data = await apiFetch(`${API_BASE}/personas/${dni}`);
        renderFicha(data);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
        fichaDiv.innerHTML = `<div class="no-results">Error: ${escapeHtml(err.message)}</div>`;
    }
}

function renderFicha(data) {
    const p = data.persona;
    const fichaDiv = document.getElementById('persona-ficha');

    const fnac = p.fecha_nacimiento
        ? new Date(p.fecha_nacimiento + 'T00:00:00').toLocaleDateString('es-PE')
        : '—';

    let html = `
    <div class="ficha-header">
        <div>
            <div class="ficha-nombre">${escapeHtml(p.nombre_completo)}</div>
            <div class="ficha-dni">DNI: ${escapeHtml(p.dni)}</div>
            <div class="ficha-meta">
                <span>📅 Nacimiento: ${fnac}</span>
                ${p.foto_url ? `<span>🖼 <a href="${escapeHtml(p.foto_url)}" target="_blank">Ver foto</a></span>` : ''}
            </div>
        </div>
        <div class="ficha-actions">
            <button class="btn btn-outline btn-sm" onclick="cargarArbol('${escapeHtml(p.dni)}')">🌳 Árbol</button>
            <button class="btn btn-outline btn-sm" onclick="abrirEtiqueta('${escapeHtml(p.dni)}')">🏷 Etiquetar</button>
            <button class="btn btn-ghost btn-sm btn-delete-persona" data-dni="${escapeHtml(p.dni)}">🗑 Eliminar</button>
        </div>
    </div>
    <div class="ficha-body">
    `;

    // Notas
    if (p.notas) {
        html += `<div class="ficha-notas">📝 ${escapeHtml(p.notas)}</div>`;
    }

    // ─── Relaciones Directas ───
    html += `<div class="section">
        <div class="section-title">
            👥 Familiares Directos
            <span class="section-badge">${data.relaciones_directas.length}</span>
        </div>`;

    if (data.relaciones_directas.length === 0) {
        html += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin relaciones registradas.</p>';
    } else {
        html += '<div class="relaciones-list">';
        data.relaciones_directas.forEach(r => {
            html += `
            <div class="relacion-card">
                <div class="relacion-info">
                    <div class="relacion-tipo">${escapeHtml(r.tipo_relacion)}</div>
                    <div class="relacion-nombre" data-dni="${escapeHtml(r.persona_relacionada.dni)}">
                        ${escapeHtml(r.persona_relacionada.nombre_completo)}
                    </div>
                    <div class="relacion-certeza">${escapeHtml(r.certeza)}${r.notas ? ' — ' + escapeHtml(r.notas) : ''}</div>
                </div>
                <button class="relacion-delete" data-id="${r.id}" title="Eliminar relación">✕</button>
            </div>`;
        });
        html += '</div>';
    }
    html += '</div>';

    // ─── Parentescos Inferidos ───
    html += `<div class="section">
        <div class="section-title">
            🧠 Parentescos Inferidos
            <span class="section-badge">${data.parentescos_inferidos.length}</span>
        </div>`;

    if (data.parentescos_inferidos.length === 0) {
        html += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">No se encontraron parentescos inferidos. Agregue más relaciones familiares para habilitar las deducciones.</p>';
    } else {
        html += '<div class="parentesco-list">';
        data.parentescos_inferidos.forEach(inf => {
            html += `
            <div class="parentesco-card">
                <div class="parentesco-header">
                    <span class="parentesco-badge">inferido</span>
                    <span class="parentesco-tipo">${escapeHtml(inf.tipo_parentesco)}:</span>
                    <span class="parentesco-nombre" data-dni="${escapeHtml(inf.persona.dni)}">
                        ${escapeHtml(inf.persona.nombre_completo)}
                    </span>
                </div>
                <div class="parentesco-camino">${escapeHtml(inf.camino)}</div>
            </div>`;
        });
        html += '</div>';
    }
    html += '</div>';

    // ─── Etiquetas ───
    html += `<div class="section">
        <div class="section-title">
            🏷 Etiquetas
            <span class="section-badge">${data.etiquetas.length}</span>
        </div>
        <div class="tags-list">`;

    data.etiquetas.forEach(et => {
        html += `
        <div class="tag-item">
            <span class="tag-nombre">${escapeHtml(et.etiqueta.nombre)}</span>
            ${et.observacion ? `<span class="tag-obs" title="${escapeHtml(et.observacion)}">${escapeHtml(et.observacion)}</span>` : ''}
            <button class="tag-remove" data-etiqueta="${escapeHtml(et.etiqueta.nombre)}" title="Quitar etiqueta">✕</button>
        </div>`;
    });

    html += `
            <button class="tag-add-btn" data-dni="${escapeHtml(p.dni)}">+ Agregar etiqueta</button>
        </div>
    </div>`;

    // Árbol (vacío, se llena al hacer clic)
    html += `<div id="arbol-container-${p.dni}" class="tree-section hidden">
        <div class="section-title">🌳 Árbol Genealógico</div>
        <div class="tree-container" id="tree-content-${p.dni}"></div>
    </div>`;

    html += '</div>'; // ficha-body

    fichaDiv.innerHTML = html;

    // ─── Event Listeners ───

    // Navegación al hacer clic en nombres
    fichaDiv.querySelectorAll('.relacion-nombre, .parentesco-nombre').forEach(el => {
        el.addEventListener('click', () => cargarFicha(el.dataset.dni));
    });

    // Eliminar relación
    fichaDiv.querySelectorAll('.relacion-delete').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm('¿Eliminar esta relación?')) return;
            try {
                await apiFetch(`${API_BASE}/relaciones/${btn.dataset.id}`, { method: 'DELETE' });
                showToast('Relación eliminada', 'success');
                cargarFicha(p.dni);
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Quitar etiqueta
    fichaDiv.querySelectorAll('.tag-remove').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            try {
                await apiFetch(
                    `${API_BASE}/personas/${p.dni}/etiquetas/${encodeURIComponent(btn.dataset.etiqueta)}`,
                    { method: 'DELETE' }
                );
                showToast('Etiqueta removida', 'success');
                cargarFicha(p.dni);
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Botón agregar etiqueta
    fichaDiv.querySelector('.tag-add-btn').addEventListener('click', () => {
        abrirEtiqueta(p.dni);
    });

    // Botón eliminar persona
    fichaDiv.querySelector('.btn-delete-persona').addEventListener('click', async () => {
        if (!confirm(`¿Eliminar a ${p.nombre_completo}?

La persona se marcará como inactiva (baja lógica).`)) return;
        try {
            await apiFetch(`${API_BASE}/personas/${p.dni}`, { method: 'DELETE' });
            showToast('Persona eliminada (baja lógica)', 'success');
            document.getElementById('persona-ficha').classList.add('hidden');
            document.getElementById('empty-state').classList.remove('hidden');
        } catch (err) {
            showToast(err.message, 'error');
        }
    });
}

/* ─── Árbol Genealógico ─────────────────────────────────────────────────── */

async function cargarArbol(dni) {
    const container = document.getElementById(`arbol-container-${dni}`);
    const content = document.getElementById(`tree-content-${dni}`);

    if (!container.classList.contains('hidden')) {
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    content.innerHTML = '<span class="spinner"></span> Cargando árbol...';

    try {
        const data = await apiFetch(`${API_BASE}/personas/${dni}/arbol?profundidad=3`);

        let tree = '👤 ' + data.raiz.nombre_completo + ' (DNI: ' + data.raiz.dni + ')\n';

        if (data.ascendentes.length > 0) {
            tree += '\n▲ ASCENDENTES:\n';
            data.ascendentes.forEach(n => {
                tree += formatArbolNodo(n, '', true);
            });
        }

        if (data.descendentes.length > 0) {
            tree += '\n▼ DESCENDENTES:\n';
            data.descendentes.forEach(n => {
                tree += formatArbolNodo(n, '', false);
            });
        }

        content.textContent = tree;
    } catch (err) {
        content.textContent = 'Error al cargar el árbol: ' + err.message;
    }
}

function formatArbolNodo(nodo, prefix, isAsc) {
    const rel = nodo.tipo_relacion ? `[${nodo.tipo_relacion}] ` : '';
    let line = prefix + (prefix ? '├─ ' : '') + rel + nodo.persona.nombre_completo + '\n';

    if (nodo.hijos && nodo.hijos.length > 0) {
        nodo.hijos.forEach((child, i) => {
            const isLast = i === nodo.hijos.length - 1;
            const newPrefix = prefix + (prefix ? (isLast ? '   ' : '│  ') : (isLast ? '   ' : '│  '));
            line += formatArbolNodo(child, newPrefix, isAsc);
        });
    }
    return line;
}

/* ─── Abrir modal de etiqueta ───────────────────────────────────────────── */

function abrirEtiqueta(dni) {
    document.getElementById('e-dni').value = dni;
    document.getElementById('e-nombre').value = '';
    document.getElementById('e-obs').value = '';
    openModal('modal-etiqueta');
}

/* ─── Form: Nueva Persona ───────────────────────────────────────────────── */

document.getElementById('form-persona').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
        dni: document.getElementById('p-dni').value.trim(),
        nombres: document.getElementById('p-nombres').value.trim(),
        apellido_paterno: document.getElementById('p-ap-paterno').value.trim(),
        apellido_materno: document.getElementById('p-ap-materno').value.trim() || null,
        fecha_nacimiento: document.getElementById('p-fecha-nac').value || null,
        foto_url: document.getElementById('p-foto').value.trim() || null,
        notas: document.getElementById('p-notas').value.trim() || null,
    };

    try {
        await apiFetch(`${API_BASE}/personas`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        showToast('Persona creada exitosamente', 'success');
        closeModal('modal-persona');
        document.getElementById('form-persona').reset();
        cargarFicha(body.dni);
    } catch (err) {
        showToast(err.message, 'error');
    }
});

/* ─── Form: Nueva Relación ──────────────────────────────────────────────── */

document.getElementById('form-relacion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
        persona_origen_dni: document.getElementById('r-origen').value.trim(),
        persona_destino_dni: document.getElementById('r-destino').value.trim(),
        tipo_relacion: document.getElementById('r-tipo').value,
        certeza: document.getElementById('r-certeza').value,
        notas: document.getElementById('r-notas').value.trim() || null,
    };

    try {
        const res = await apiFetch(`${API_BASE}/relaciones`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        showToast(res.mensaje || 'Relación creada', 'success');
        closeModal('modal-relacion');
        document.getElementById('form-relacion').reset();
        // Recargar la ficha si está visible
        const ficha = document.getElementById('persona-ficha');
        if (!ficha.classList.contains('hidden')) {
            const dniActual = ficha.querySelector('.ficha-dni')?.textContent?.replace('DNI: ', '');
            if (dniActual) cargarFicha(dniActual);
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
});

/* ─── Form: Asignar Etiqueta ────────────────────────────────────────────── */

document.getElementById('form-etiqueta').addEventListener('submit', async (e) => {
    e.preventDefault();
    const dni = document.getElementById('e-dni').value;
    const body = {
        etiqueta_nombre: document.getElementById('e-nombre').value.trim(),
        observacion: document.getElementById('e-obs').value.trim() || null,
    };

    try {
        await apiFetch(`${API_BASE}/personas/${dni}/etiquetas`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        showToast('Etiqueta asignada', 'success');
        closeModal('modal-etiqueta');
        document.getElementById('form-etiqueta').reset();
        cargarFicha(dni);
    } catch (err) {
        showToast(err.message, 'error');
    }
});

/* ─── Botones del Header ────────────────────────────────────────────────── */

document.getElementById('btn-nueva-persona').addEventListener('click', () => {
    document.getElementById('form-persona').reset();
    openModal('modal-persona');
});

document.getElementById('btn-nueva-relacion').addEventListener('click', () => {
    document.getElementById('form-relacion').reset();
    openModal('modal-relacion');
});

document.getElementById('btn-etiquetas').addEventListener('click', async () => {
    openModal('modal-lista-etiquetas');
    const content = document.getElementById('lista-etiquetas-content');
    content.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando...</p>';

    try {
        const etiquetas = await apiFetch(`${API_BASE}/etiquetas`);
        if (etiquetas.length === 0) {
            content.innerHTML = '<p class="no-results">No hay etiquetas creadas todavía.</p>';
            return;
        }

        content.innerHTML = etiquetas.map(et => `
            <div class="etiqueta-list-item" data-nombre="${escapeHtml(et.nombre)}">
                <span>🏷 <strong>${escapeHtml(et.nombre)}</strong></span>
                <span style="color:var(--color-text-secondary);font-size:0.82rem;">Click para ver personas →</span>
            </div>
        `).join('');

        content.querySelectorAll('.etiqueta-list-item').forEach(item => {
            item.addEventListener('click', async () => {
                const nombre = item.dataset.nombre;
                try {
                    const personas = await apiFetch(
                        `${API_BASE}/etiquetas/${encodeURIComponent(nombre)}/personas`
                    );
                    if (personas.length === 0) {
                        showToast(`Ninguna persona tiene la etiqueta "${nombre}"`, 'info');
                        return;
                    }
                    closeModal('modal-lista-etiquetas');
                    if (personas.length === 1) {
                        cargarFicha(personas[0].dni);
                    } else {
                        // Mostrar resultados en la búsqueda
                        searchResults.innerHTML = personas.map(p => `
                            <div class="search-result-item" data-dni="${p.dni}">
                                <span><strong>${escapeHtml(p.nombre_completo)}</strong></span>
                                <span class="search-result-dni">DNI: ${escapeHtml(p.dni)}</span>
                            </div>
                        `).join('');
                        searchResults.querySelectorAll('.search-result-item').forEach(el => {
                            el.addEventListener('click', () => {
                                searchResults.classList.add('hidden');
                                cargarFicha(el.dataset.dni);
                            });
                        });
                        searchResults.classList.remove('hidden');
                    }
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        });
    } catch (err) {
        content.innerHTML = `<p class="no-results">Error: ${escapeHtml(err.message)}</p>`;
    }
});

/* ─── Utilidades ─────────────────────────────────────────────────────────── */

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/* ─── Inicialización ─────────────────────────────────────────────────────── */

// Verificar que las credenciales funcionan al cargar la página
(async function init() {
    try {
        await apiFetch(`${API_BASE}/health`);
        console.log('✅ Conectado a RedCorruptela API');
    } catch (err) {
        // Si falla el health check, puede ser que no haya BD todavía
        console.warn('⚠ Health check falló:', err.message);
    }
})();
