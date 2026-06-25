/**
 * ui.js — Funciones de renderizado y manejo del DOM.
 * 
 * Contiene todas las funciones de interfaz: búsqueda, fichas,
 * modales, árbol genealógico, importación, dashboard, etc.
 */

/* ─── Toast ─── */
function st(msg, type) {
    type = type || "info";
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.className = "toast toast-" + type;
    t.classList.remove("hidden");
    if (AppState.get("toastTimer")) clearTimeout(AppState.get("toastTimer"));
    AppState.set("toastTimer", setTimeout(function() { t.classList.add("hidden"); }, 4000));
}


/* ─── Login ─── */
document.getElementById("form-login").addEventListener("submit", async function(e) {
    e.preventDefault();
    var u = document.getElementById("login-user").value.trim();
    var p = document.getElementById("login-pass").value.trim();
    if (!u || !p) return;
    var btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.textContent = "Ingresando...";
    try {
        var r = await fetch(A + "/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) });
        if (!r.ok) { var ed = await r.json(); throw new Error(ed.detail || "Error"); }
        var d = await r.json();
        setAuth(d.access_token, d.username, d.rol);
        hl();
        if (d.rol === "lector") st("Modo lectura: solo puede ver datos", "info");
        _init();
    } catch (err) { console.error("[Login]", err); st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "Ingresar";
});


/* ─── Modals ─── */
function om(id) { document.getElementById(id).classList.remove("hidden"); }
function cm(id) { document.getElementById(id).classList.add("hidden"); }

document.addEventListener("click", function(e) {
    if (e.target.dataset.close) cm(e.target.dataset.close);
    if (e.target.classList.contains("modal-overlay")) { var m = e.target.closest(".modal"); if (m) m.classList.add("hidden"); }
});
document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") document.querySelectorAll(".modal:not(.hidden)").forEach(function(m) { m.classList.add("hidden"); });
});

function es(s) { if (!s) return ""; var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

/* ─── Search Personas ─── */
var si = document.getElementById("search-input");
var sb = document.getElementById("search-btn");
var sr = document.getElementById("search-results");

sb.addEventListener("click", function() { ds(true); });
si.addEventListener("input", function(e) {
    var q = si.value.trim();
    if (q.length < 2) { sr.classList.add("hidden"); return; }
    if (AppState.get("searchTimer")) clearTimeout(AppState.get("searchTimer"));
    AppState.set("searchTimer", setTimeout(function() { dsLive(q); }, 300));
});
si.addEventListener("keydown", function(e) {
    if (e.key === "Enter") { if (AppState.get("searchTimer")) clearTimeout(AppState.get("searchTimer")); ds(true); }
    if (e.key === "Escape") { sr.classList.add("hidden"); }
});
document.addEventListener("click", function(e) {
    if (!e.target.closest("#search-input") && !e.target.closest("#search-results")) { sr.classList.add("hidden"); }
});

async function dsLive(q) {
    try {
        var d = await af(A + "/personas?q=" + encodeURIComponent(q) + "&limite=8");
        if (d.total === 0) { sr.innerHTML = '<div class="no-results">Sin resultados</div>'; sr.classList.remove("hidden"); return; }
        sr.innerHTML = d.resultados.map(function(p) {
            return '<div class="search-result-item" data-dni="' + p.dni + '"><span><strong>' + es(p.nombre_completo) + '</strong></span><span class="search-result-dni">DNI: ' + es(p.dni) + '</span></div>';
        }).join("");
        sr.querySelectorAll(".search-result-item").forEach(function(it) {
            it.addEventListener("click", function() { sr.classList.add("hidden"); si.value = d.resultados.find(function(x){return x.dni===it.dataset.dni}).nombre_completo; cf(it.dataset.dni); });
        });
        sr.classList.remove("hidden");
    } catch (err) { /* silent */ }
}

async function ds(enter) {
    var q = si.value.trim(); if (!q) return;
    try {
        var d = await af(A + "/personas?q=" + encodeURIComponent(q));
        if (d.total === 0) { sr.innerHTML = '<div class="no-results">Sin resultados</div>'; sr.classList.remove("hidden"); return; }
        if (d.total === 1 && enter) { sr.classList.add("hidden"); cf(d.resultados[0].dni); return; }
        sr.innerHTML = d.resultados.map(function(p) {
            return '<div class="search-result-item" data-dni="' + p.dni + '"><span><strong>' + es(p.nombre_completo) + '</strong></span><span class="search-result-dni">DNI: ' + es(p.dni) + '</span></div>';
        }).join("");
        sr.querySelectorAll(".search-result-item").forEach(function(it) {
            it.addEventListener("click", function() { sr.classList.add("hidden"); si.value = ""; cf(it.dataset.dni); });
        });
        sr.classList.remove("hidden");
    } catch (err) { st(err.message, "error"); }
}

/* ─── Search Empresas ─── */
var esi = document.getElementById("search-empresa-input");
var esb = document.getElementById("search-empresa-btn");
var esr = document.getElementById("search-empresa-results");

esb.addEventListener("click", function() { dsEmpresa(); });
esi.addEventListener("input", function(e) {
    var q = esi.value.trim();
    if (q.length < 2) { esr.classList.add("hidden"); return; }
    if (AppState.get("empresaSearchTimer")) clearTimeout(AppState.get("empresaSearchTimer"));
    AppState.set("empresaSearchTimer", setTimeout(function() { dsEmpresaLive(q); }, 300));
});
esi.addEventListener("keydown", function(e) {
    if (e.key === "Enter") { if (AppState.get("empresaSearchTimer")) clearTimeout(AppState.get("empresaSearchTimer")); dsEmpresa(); }
    if (e.key === "Escape") { esr.classList.add("hidden"); }
});
document.addEventListener("click", function(e) {
    if (!e.target.closest("#search-empresa-input") && !e.target.closest("#search-empresa-results")) { esr.classList.add("hidden"); }
});

async function dsEmpresaLive(q) {
    try {
        var d = await af(A + "/empresas?q=" + encodeURIComponent(q) + "&limite=8");
        if (d.total === 0) { esr.innerHTML = '<div class="no-results">Sin resultados</div>'; esr.classList.remove("hidden"); return; }
        esr.innerHTML = d.resultados.map(function(emp) {
            return '<div class="search-result-item" data-ruc="' + emp.ruc + '"><span><strong>' + es(emp.nombre) + '</strong></span><span class="search-result-dni">RUC: ' + es(emp.ruc) + '</span></div>';
        }).join("");
        esr.querySelectorAll(".search-result-item").forEach(function(it) {
            it.addEventListener("click", function() { esr.classList.add("hidden"); esi.value = ""; cfEmpresa(it.dataset.ruc); });
        });
        esr.classList.remove("hidden");
    } catch (err) { /* silent */ }
}

async function dsEmpresa() {
    var q = esi.value.trim(); if (!q) return;
    try {
        var d = await af(A + "/empresas?q=" + encodeURIComponent(q));
        if (d.total === 0) { esr.innerHTML = '<div class="no-results">Sin resultados</div>'; esr.classList.remove("hidden"); return; }
        if (d.total === 1) { esr.classList.add("hidden"); cfEmpresa(d.resultados[0].ruc); return; }
        esr.innerHTML = d.resultados.map(function(emp) {
            return '<div class="search-result-item" data-ruc="' + emp.ruc + '"><span><strong>' + es(emp.nombre) + '</strong></span><span class="search-result-dni">RUC: ' + es(emp.ruc) + '</span></div>';
        }).join("");
        esr.querySelectorAll(".search-result-item").forEach(function(it) {
            it.addEventListener("click", function() { esr.classList.add("hidden"); esi.value = ""; cfEmpresa(it.dataset.ruc); });
        });
        esr.classList.remove("hidden");
    } catch (err) { st(err.message, "error"); }
}

/* ─── Ficha Persona (Modal) ─── */
function _abrirModalFicha() {
    var modal = document.getElementById("modal-ficha");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "modal-ficha";
        modal.className = "modal-overlay";
        modal.innerHTML = '<div class="modal-content" style="width:90%;max-width:720px;max-height:85vh;overflow-y:auto;border-radius:16px;"><div class="modal-header"><h3 id="modal-ficha-title">👤 Persona</h3><button class="btn btn-ghost" onclick="document.getElementById(\'modal-ficha\').classList.add(\'hidden\')">✕</button></div><div id="modal-ficha-content"></div></div>';
        document.body.appendChild(modal);
        modal.addEventListener("click", function(e) { if (e.target === modal) modal.classList.add("hidden"); });
    }
    modal.classList.remove("hidden");
    return document.getElementById("modal-ficha-content");
}

async function cf(dni) {
    var content = _abrirModalFicha();
    document.getElementById("modal-ficha-title").textContent = "👤 Persona";
    content.innerHTML = '<div class="loading-text" style="padding:40px;text-align:center;"><span class="spinner"></span> Cargando...</div>';
    try {
        var d = await af(A + "/personas/" + dni);
        window._fichaData = d;
        rf(d);
        var fd = document.getElementById("persona-ficha");
        if (fd && fd.innerHTML) {
            content.innerHTML = fd.innerHTML;
            fd.innerHTML = ""; // Limpiar para que no se vea debajo del modal
            _aplicarEventosFicha(content, d);
        }
    } catch (err) {
        content.innerHTML = '<div class="no-results" style="padding:40px;text-align:center;">Error: ' + es(err.message) + '</div>';
    }
}

function _aplicarEventosFicha(container, d) {
    if (!d) d = window._fichaData;
    if (!d) return;
    var p = d.persona;
    container.querySelectorAll(".relacion-nombre:not(.empresa-link), .parentesco-nombre").forEach(function(el) {
        el.addEventListener("click", function() { cf(el.dataset.dni); });
    });
    container.querySelectorAll(".empresa-link").forEach(function(el) {
        el.addEventListener("click", function() { cfEmpresa(el.dataset.ruc); });
    });
    container.querySelectorAll(".relacion-delete:not(.btn-desvincular-empresa)").forEach(function(btn) {
        btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Eliminar relacion?")) return; try { await af(A + "/relaciones/" + btn.dataset.id, { method: "DELETE" }); st("Relacion eliminada", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } });
    });
    container.querySelectorAll(".btn-desvincular-empresa").forEach(function(btn) {
        btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Desvincular?")) return; try { await af(A + "/persona-empresa/" + btn.dataset.id, { method: "DELETE" }); st("Desvinculado", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } });
    });
    container.querySelectorAll(".tag-remove").forEach(function(btn) {
        btn.addEventListener("click", async function(e) { e.stopPropagation(); try { await af(A + "/personas/" + p.dni + "/etiquetas/" + encodeURIComponent(btn.dataset.etiqueta), { method: "DELETE" }); st("Etiqueta removida", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } });
    });
    var ta_ = container.querySelector(".tag-add-btn");
    if (ta_) ta_.addEventListener("click", function() { abrirEtiqueta(p.dni); });
    var db_ = container.querySelector(".btn-delete-persona");
    if (db_) db_.addEventListener("click", async function() { if (!confirm("Eliminar a " + p.nombre_completo + "?")) return; try { await af(A + "/personas/" + p.dni, { method: "DELETE" }); st("Persona eliminada", "success"); document.getElementById("modal-ficha").classList.add("hidden"); } catch (err) { st(err.message, "error"); } });
}

function rf(d) {
    var p = d.persona, fd = document.getElementById("persona-ficha");
    var fn = p.fecha_nacimiento ? new Date(p.fecha_nacimiento + "T00:00:00").toLocaleDateString("es-PE") : "\u2014";
    var h = "";
    // Generar avatar SVG inline basado en DNI (no requiere API externa)
    var seed = p.dni || "00000000";
    var color = ["#2563eb","#7c3aed","#dc2626","#16a34a","#d97706","#0891b2"][parseInt(seed.slice(-1), 10) % 6];
    var iniciales = (p.nombres ? p.nombres.charAt(0) : "?") + (p.apellido_paterno ? p.apellido_paterno.charAt(0) : "");
    var avatarSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"><rect width="80" height="80" rx="40" fill="' + color + '"/><text x="40" y="43" text-anchor="middle" fill="white" font-size="28" font-weight="bold" font-family="sans-serif">' + es(iniciales) + '</text></svg>';
    var avatarDataUri = "data:image/svg+xml," + encodeURIComponent(avatarSvg);
    var imgSrc = p.foto_url || avatarDataUri;
    h += '<div class="ficha-header"><div class="ficha-avatar"><img src="' + imgSrc + '" alt="Avatar" style="width:80px;height:80px;border-radius:50%;object-fit:cover;background:var(--color-bg);"></div><div><div class="ficha-nombre">' + es(p.nombre_completo) + '</div><div class="ficha-dni">DNI: ' + es(p.dni) + '</div><div class="ficha-meta"><span>📅 Nacimiento: ' + fn + '</span>';
    if (p.foto_url) h += '<span>🖼 <a href="' + es(p.foto_url) + '" target="_blank">Ver foto</a></span>';
    h += '</div></div><div class="ficha-actions"><button class="btn btn-outline btn-sm" onclick="cargarArbol(\x27' + es(p.dni) + '\x27)">🌳 Árbol</button> <button class="btn btn-outline btn-sm" onclick="abrirEtiqueta(\x27' + es(p.dni) + '\x27)">🏷 Etiquetar</button> <button class="btn btn-outline btn-sm" onclick="abrirVincularEmpresa(\x27' + es(p.dni) + '\x27)">🏢 + Empresa</button> <button class="btn btn-outline btn-sm" onclick="editarPersona(\x27' + es(p.dni) + '\x27)">✏️ Editar</button> <button class="btn btn-ghost btn-sm btn-delete-persona" data-dni="' + es(p.dni) + '">🗑 Eliminar</button></div></div><div class="ficha-body">';
    if (p.notas) h += '<div class="ficha-notas">📝 ' + es(p.notas) + '</div>';
    h += '<div class="section"><div class="section-title">👥 Familiares Directos <span class="section-badge">' + d.relaciones_directas.length + '</span></div>';
    if (d.relaciones_directas.length === 0) { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin relaciones.</p>'; }
    else { h += '<div class="relaciones-list">'; d.relaciones_directas.forEach(function(r) { h += '<div class="relacion-card"><div class="relacion-info"><div class="relacion-tipo">' + es(r.tipo_relacion) + '</div><div class="relacion-nombre" data-dni="' + es(r.persona_relacionada.dni) + '">' + es(r.persona_relacionada.nombre_completo) + '</div><div class="relacion-certeza">' + es(r.certeza) + (r.notas ? " — " + es(r.notas) : "") + '</div></div><button class="relacion-delete" data-id="' + r.id + '" title="Eliminar">✕</button></div>'; }); h += '</div>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🧠 Parentescos Inferidos <span class="section-badge">' + d.parentescos_inferidos.length + '</span></div>';
    if (d.parentescos_inferidos.length === 0) { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">No se encontraron parentescos inferidos.</p>'; }
    else { h += '<div class="parentesco-list">'; d.parentescos_inferidos.forEach(function(inf) { h += '<div class="parentesco-card"><div class="parentesco-header"><span class="parentesco-badge">inferido</span><span class="parentesco-tipo">' + es(inf.tipo_parentesco) + ':</span><span class="parentesco-nombre" data-dni="' + es(inf.persona.dni) + '">' + es(inf.persona.nombre_completo) + '</span></div><div class="parentesco-camino">' + es(inf.camino) + '</div></div>'; }); h += '</div>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🏢 Empresas Vinculadas <span class="section-badge">' + (d.empresas ? d.empresas.length : 0) + '</span></div>';
    if (d.empresas && d.empresas.length > 0) {
        h += '<div class="relaciones-list">';
        d.empresas.forEach(function(pe) {
            var cargoLabel = pe.cargo || "trabajador";
            var desde = pe.fecha_desde ? "desde " + pe.fecha_desde : "";
            var hasta = pe.fecha_hasta ? " hasta " + pe.fecha_hasta : "";
            h += '<div class="relacion-card"><div class="relacion-info"><div class="relacion-tipo" style="color:var(--color-primary);">' + es(cargoLabel) + '</div><div class="relacion-nombre empresa-link" data-ruc="' + es(pe.empresa.ruc) + '">🏢 ' + es(pe.empresa.nombre) + '</div><div class="relacion-certeza">RUC: ' + es(pe.empresa.ruc) + (desde || hasta ? " (" + desde + hasta + ")" : "") + (pe.observacion ? " — " + es(pe.observacion) : "") + '</div></div><button class="relacion-delete btn-desvincular-empresa" data-id="' + pe.id + '" title="Desvincular">✕</button></div>';
            // Mostrar contratos de la empresa si tiene notas JSON
            if (pe.empresa.notas) {
                try {
                    var parsed = JSON.parse(pe.empresa.notas);
                    if (parsed.contratos && parsed.contratos.length > 0) {
                        var subtotal = parsed.contratos.reduce(function(s, c) { return s + (c.importe || 0); }, 0);
                        h += '<div style="padding:4px 12px 8px 12px;margin:-4px 0 8px 0;font-size:0.8rem;background:#f1f5f9;border-radius:0 0 8px 8px;border-left:3px solid var(--color-primary);">';
                        h += '<div style="font-weight:500;color:var(--color-primary);margin-bottom:4px;">📋 Contratos (' + parsed.contratos.length + ' · S/. ' + subtotal.toLocaleString("es-PE", { minimumFractionDigits: 2 }) + ')</div>';
                        parsed.contratos.slice(0, 3).forEach(function(c) {
                            h += '<div style="padding:2px 0;color:#475569;">';
                            var icon = c.tipo && c.tipo.indexOf("O/C") !== -1 ? "🛒" : "🔧";
                            h += icon + ' ' + es(c.tipo || "") + ' N°' + es(c.numero || "") + ' — ' + (c.descripcion || "").substring(0, 80);
                            if (c.descripcion && c.descripcion.length > 80) h += '…';
                            h += ' <span style="color:#64748b;">S/. ' + (c.importe || 0).toLocaleString("es-PE", { minimumFractionDigits: 2 }) + '</span>';
                            h += '</div>';
                        });
                        if (parsed.contratos.length > 3) {
                            h += '<div style="padding:2px 0;color:#94a3b8;font-style:italic;">+ ' + (parsed.contratos.length - 3) + ' más…</div>';
                        }
                        h += '</div>';
                    }
                } catch (ex) { /* ignorar */ }
            }
        });
        h += '</div>';
    } else { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin empresas vinculadas.</p>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🏷 Etiquetas <span class="section-badge">' + d.etiquetas.length + '</span></div><div class="tags-list">';
    d.etiquetas.forEach(function(et) { h += '<div class="tag-item"><span class="tag-nombre">' + es(et.etiqueta.nombre) + '</span>'; if (et.observacion) h += '<span class="tag-obs" title="' + es(et.observacion) + '">' + es(et.observacion) + '</span>'; h += '<button class="tag-remove" data-etiqueta="' + es(et.etiqueta.nombre) + '" title="Quitar">✕</button></div>'; });
    h += '<button class="tag-add-btn" data-dni="' + es(p.dni) + '">+ Agregar etiqueta</button></div></div>';
    h += '<div id="arbol-container-' + p.dni + '" class="tree-section hidden"><div class="section-title">🌳 Árbol Genealógico</div><div class="tree-container" id="tree-content-' + p.dni + '"></div></div>';
    h += '</div>';
    fd.innerHTML = h;
    fd.querySelectorAll(".relacion-nombre:not(.empresa-link), .parentesco-nombre").forEach(function(el) { el.addEventListener("click", function() { cf(el.dataset.dni); }); });
    fd.querySelectorAll(".empresa-link").forEach(function(el) { el.addEventListener("click", function() { cfEmpresa(el.dataset.ruc); }); });
    fd.querySelectorAll(".relacion-delete:not(.btn-desvincular-empresa)").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Eliminar relacion?")) return; try { await af(A + "/relaciones/" + btn.dataset.id, { method: "DELETE" }); st("Relacion eliminada", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } }); });
    fd.querySelectorAll(".btn-desvincular-empresa").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Desvincular esta empresa de " + p.nombre_completo + "?")) return; try { await af(A + "/persona-empresa/" + btn.dataset.id, { method: "DELETE" }); st("Desvinculado", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } }); });
    fd.querySelectorAll(".tag-remove").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); try { await af(A + "/personas/" + p.dni + "/etiquetas/" + encodeURIComponent(btn.dataset.etiqueta), { method: "DELETE" }); st("Etiqueta removida", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } }); });
    var ta_ = fd.querySelector(".tag-add-btn"); if (ta_) ta_.addEventListener("click", function() { abrirEtiqueta(p.dni); });
    var db_ = fd.querySelector(".btn-delete-persona"); if (db_) db_.addEventListener("click", async function() { if (!confirm("Eliminar a " + p.nombre_completo + "?")) return; try { await af(A + "/personas/" + p.dni, { method: "DELETE" }); st("Persona eliminada", "success"); fd.classList.add("hidden"); document.getElementById("empty-state").classList.remove("hidden"); } catch (err) { st(err.message, "error"); } });
}

/* ─── Ficha Empresa (Modal) ─── */
async function cfEmpresa(ruc) {
    var content = _abrirModalFicha();
    document.getElementById("modal-ficha-title").textContent = "🏢 Empresa";
    content.innerHTML = '<div class="loading-text" style="padding:40px;text-align:center;"><span class="spinner"></span> Cargando empresa...</div>';
    try {
        var d = await af(A + "/empresas/" + ruc);
        window._fichaData = d;
        rfEmpresa(d);
        var ef = document.getElementById("empresa-ficha");
        if (ef && ef.innerHTML) {
            content.innerHTML = ef.innerHTML;
            _aplicarEventosEmpresa(content, d, ruc);
        }
    } catch (err) {
        content.innerHTML = '<div class="no-results" style="padding:40px;text-align:center;">Error: ' + es(err.message) + '</div>';
    }
}
window.cfEmpresa = cfEmpresa;

function _aplicarEventosEmpresa(container, d, ruc) {
    if (!d) d = window._fichaData;
    if (!d) return;
    var e = d.empresa || {};
    container.querySelectorAll(".relacion-nombre:not(.empresa-link)").forEach(function(el) {
        el.addEventListener("click", function() { cf(el.dataset.dni); });
    });
    container.querySelectorAll(".btn-desvincular-persona").forEach(function(btn) {
        btn.addEventListener("click", async function(ev) { ev.stopPropagation(); if (!confirm("Desvincular?")) return; try { await af(A + "/persona-empresa/" + btn.dataset.id, { method: "DELETE" }); st("Desvinculado", "success"); cfEmpresa(ruc); } catch (err) { st(err.message, "error"); } });
    });
    container.querySelectorAll(".tag-remove-empresa").forEach(function(btn) {
        btn.addEventListener("click", async function(ev) { ev.stopPropagation(); try { await af(A + "/empresas/" + ruc + "/etiquetas/" + encodeURIComponent(btn.dataset.etiqueta), { method: "DELETE" }); st("Etiqueta removida", "success"); cfEmpresa(ruc); } catch (err) { st(err.message, "error"); } });
    });
    var ta2 = container.querySelector(".tag-add-btn");
    if (ta2) ta2.addEventListener("click", function() { abrirEtiquetaEmpresa(ruc); });
    var db2 = container.querySelector(".btn-delete-empresa");
    if (db2) db2.addEventListener("click", async function() { if (!confirm("Eliminar empresa?")) return; try { await af(A + "/empresas/" + ruc, { method: "DELETE" }); st("Empresa eliminada", "success"); document.getElementById("modal-ficha").classList.add("hidden"); } catch (err) { st(err.message, "error"); } });
}

function rfEmpresa(d) {
    var e = d.empresa, ef = document.getElementById("empresa-ficha");
    var h = "";

    // ── Header ──
    var rucBadge = e.ruc && e.ruc.charAt(0) === "1" ? "🔵 RUC 10" : "🔴 RUC 20";
    h += '<div class="ficha-header"><div><div class="ficha-nombre">🏢 ' + es(e.nombre) + '</div><div class="ficha-dni">' + rucBadge + ' · ' + es(e.ruc) + '</div>';
    h += '<div class="ficha-meta">';
    if (e.estado) h += '<span class="status-badge status-' + es(e.estado.toLowerCase()) + '">' + es(e.estado) + '</span>';
    else h += '<span class="status-badge" style="background:#e2e8f0;color:#64748b;">Estado —</span>';
    if (e.condicion) h += '<span>' + es(e.condicion) + '</span>';
    if (e.tipo_contribuyente) h += '<span>' + es(e.tipo_contribuyente) + '</span>';
    if (e.nombre_comercial) h += '<span>🏷 ' + es(e.nombre_comercial) + '</span>';
    if (e.fecha_inicio_actividades) h += '<span>📅 Inicio: ' + es(e.fecha_inicio_actividades) + '</span>';
    if (e.fecha_inscripcion) h += '<span>📋 Inscripción: ' + es(e.fecha_inscripcion) + '</span>';
    h += '</div></div><div class="ficha-actions">';
    h += '<button class="btn btn-outline btn-sm" onclick="abrirEtiquetaEmpresa(\x27' + es(e.ruc) + '\x27)">🏷 Etiquetar</button>';
    h += '<button class="btn btn-outline btn-sm" onclick="editarEmpresa(\x27' + es(e.ruc) + '\x27)">✏️ Editar</button>';
    h += '<button class="btn btn-outline btn-sm" onclick="enriquecerEmpresa(\x27' + es(e.ruc) + '\x27)" title="Completar datos desde SUNAT">🔄 SUNAT</button>';
    h += '<button class="btn btn-ghost btn-sm btn-delete-empresa" data-ruc="' + es(e.ruc) + '">🗑 Eliminar</button>';
    h += '</div></div><div class="ficha-body">';
    if (e.notas) h += '<div class=\"ficha-notas\">📝 ' + es(e.notas) + '</div>';

    // ── Contratos (desde notas JSON del import transparencia) ──
    var contratos = [];
    if (e.notas) {
        try {
            var parsed = JSON.parse(e.notas);
            if (parsed.contratos && Array.isArray(parsed.contratos)) {
                contratos = parsed.contratos;
            }
        } catch (ex) { /* notas no es JSON, ignorar */ }
    }
    if (contratos.length > 0) {
        var totalMonto = contratos.reduce(function(sum, c) { return sum + (c.importe || 0); }, 0);
        h += '<div class="section"><div class="section-title">📋 Órdenes de Compra/Servicio <span class="section-badge">' + contratos.length + '</span></div>';
        h += '<div style="margin-bottom:8px;font-size:0.9rem;color:var(--color-text-secondary);">💰 Total: S/. ' + totalMonto.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '</div>';
        h += '<div class="relaciones-list" style="max-height:400px;overflow-y:auto;">';
        contratos.forEach(function(c) {
            var tipoIcon = c.tipo && c.tipo.toUpperCase().indexOf("O/C") !== -1 ? "🛒" : "🔧";
            h += '<div class="relacion-card">';
            h += '<div class="relacion-info">';
            h += '<div class="relacion-tipo">' + tipoIcon + ' ' + es(c.tipo || "") + ' N° ' + es(c.numero || "") + '</div>';
            h += '<div class="relacion-nombre">' + es(c.descripcion || "") + '</div>';
            h += '<div class="relacion-certeza">';
            if (c.fecha) h += '📅 ' + es(c.fecha) + ' · ';
            h += '💰 S/. ' + (c.importe || 0).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            if (c.estado) h += ' · ' + es(c.estado);
            h += '</div>';
            h += '</div></div>';
        });
        h += '</div></div>';
    }

    // ── Datos SUNAT ──
    h += '<div class="section"><div class="section-title">📊 Datos SUNAT <span style="font-weight:400;font-size:0.75rem;color:var(--color-text-secondary);">(completa con 🔄 SUNAT)</span></div><div class="sunat-grid">';
    var placeholder = function(v) {
        return v ? es(v) : '<span style="color:#94a3b8;font-style:italic;">— pendiente —</span>';
    };
    var sunatFields = [
        { label: "Tipo Contribuyente", value: e.tipo_contribuyente },
        { label: "Nombre Comercial", value: e.nombre_comercial },
        { label: "Estado", value: e.estado },
        { label: "Condición", value: e.condicion },
        { label: "Dirección", value: e.direccion },
        { label: "Fecha Inscripción", value: e.fecha_inscripcion },
        { label: "Inicio Actividades", value: e.fecha_inicio_actividades },
        { label: "Sistema Contabilidad", value: e.sistema_contabilidad },
        { label: "Comercio Exterior", value: e.actividad_comercio_exterior },
        { label: "Actividad Económica", value: e.actividad_economica },
        { label: "Comprobantes", value: e.comprobantes_autorizados },
        { label: "Sistema Emisión", value: e.sistema_emision },
        { label: "Afiliado PLE", value: e.afiliado_ple },
        { label: "Sistema Emisión Electrónica", value: e.sistema_emision_electronica },
        { label: "Emisor Electrónico Desde", value: e.emisor_electronico_desde },
        { label: "Comprobantes Electrónicos", value: e.comprobantes_electronicos },
        { label: "Padrones", value: e.padrones },
        { label: "Establecimientos", value: e.establecimientos },
    ];
    sunatFields.forEach(function(f) {
        h += '<div class="sunat-field"><span class="sunat-label">' + es(f.label) + ':</span><span class="sunat-value">' + placeholder(f.value) + '</span></div>';
    });
    h += '</div></div>';

    // ── Representante Legal ──
    if (e.representante_legal_dni) {
        h += '<div class="section"><div class="section-title">👤 Representante Legal</div>';
        h += '<div class="relacion-card" style="margin-top:8px;">';
        h += '<div class="relacion-info">';
        h += '<div class="relacion-nombre" data-dni="' + es(e.representante_legal_dni) + '">' + es(e.representante_legal_nombre || "—") + '</div>';
        h += '<div class="relacion-certeza">DNI: ' + es(e.representante_legal_dni) + '</div>';
        h += '</div>';
        // Boton para vincular si no existe ya
        var yaVinculado = d.personas_vinculadas.some(function(pv) {
            return pv.persona.dni === e.representante_legal_dni && pv.cargo === "representante legal";
        });
        if (!yaVinculado) {
            h += '<button class="btn btn-primary btn-sm" onclick="crearVinculoDesdeConsulta(\x27' + es(e.ruc) + '\x27, \x27' + es(e.representante_legal_dni) + '\x27)">🔗 Vincular como Rep. Legal</button>';
        } else {
            h += '<span style="color:var(--color-success);font-weight:500;">✅ Vinculado</span>';
        }
        h += '</div></div>';
    }

    // ── Personas Vinculadas ──
    h += '<div class="section"><div class="section-title">👥 Personas Vinculadas <span class="section-badge">' + d.personas_vinculadas.length + '</span></div>';
    if (d.personas_vinculadas.length === 0) {
        h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin personas vinculadas.</p>';
    } else {
        h += '<div class="relaciones-list">';
        d.personas_vinculadas.forEach(function(pv) {
            var cargoLabel = pv.cargo || "trabajador";
            var badgeClass = pv.cargo === "representante legal" ? 'style="background:var(--color-inferido);color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem;"' : 'style="background:var(--color-border);padding:2px 8px;border-radius:10px;font-size:0.75rem;"';
            h += '<div class="relacion-card"><div class="relacion-info"><div><span ' + badgeClass + '>' + es(cargoLabel) + '</span></div><div class="relacion-nombre" data-dni="' + es(pv.persona.dni) + '">' + es(pv.persona.nombre_completo) + '</div><div class="relacion-certeza">DNI: ' + es(pv.persona.dni) + (pv.observacion ? " — " + es(pv.observacion) : "") + '</div></div><button class="relacion-delete btn-desvincular-persona" data-id="' + pv.id + '" title="Desvincular">✕</button></div>';
        });
        h += '</div>';
    }
    h += '</div>';

    // ── Etiquetas ──
    h += '<div class="section"><div class="section-title">🏷 Etiquetas <span class="section-badge">' + d.etiquetas.length + '</span></div><div class="tags-list">';
    d.etiquetas.forEach(function(et) { h += '<div class="tag-item"><span class="tag-nombre">' + es(et.etiqueta.nombre) + '</span>'; if (et.observacion) h += '<span class="tag-obs" title="' + es(et.observacion) + '">' + es(et.observacion) + '</span>'; h += '<button class="tag-remove-empresa" data-etiqueta="' + es(et.etiqueta.nombre) + '" title="Quitar">✕</button></div>'; });
    h += '<button class="tag-add-btn" data-ruc="' + es(e.ruc) + '">+ Agregar etiqueta</button></div></div>';
    h += '</div>';
    ef.innerHTML = h;

    // ── Event listeners ──
    ef.querySelectorAll(".relacion-nombre:not(.empresa-link)").forEach(function(el) { el.addEventListener("click", function() { cf(el.dataset.dni); }); });
    ef.querySelectorAll(".btn-desvincular-persona").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Desvincular esta persona?")) return; try { await af(A + "/persona-empresa/" + btn.dataset.id, { method: "DELETE" }); st("Desvinculado", "success"); cfEmpresa(e.ruc); } catch (err) { st(err.message, "error"); } }); });
    ef.querySelectorAll(".tag-remove-empresa").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); try { await af(A + "/empresas/" + e.ruc + "/etiquetas/" + encodeURIComponent(btn.dataset.etiqueta), { method: "DELETE" }); st("Etiqueta removida", "success"); cfEmpresa(e.ruc); } catch (err) { st(err.message, "error"); } }); });
    ef.querySelector(".tag-add-btn").addEventListener("click", function() { abrirEtiquetaEmpresa(e.ruc); });
    ef.querySelector(".btn-delete-empresa").addEventListener("click", async function() { if (!confirm("Eliminar empresa " + e.nombre + "?")) return; try { await af(A + "/empresas/" + e.ruc, { method: "DELETE" }); st("Empresa eliminada", "success"); ef.classList.add("hidden"); document.getElementById("empty-state").classList.remove("hidden"); } catch (err) { st(err.message, "error"); } });
}

/* ─── Tree ─── */
window.cargarArbol = async function(dni) {
    var c = document.getElementById("arbol-container-" + dni), ct_ = document.getElementById("tree-content-" + dni);
    if (!c.classList.contains("hidden")) { c.classList.add("hidden"); return; }
    c.classList.remove("hidden"); ct_.innerHTML = '<span class="spinner"></span> Cargando...';
    try {
        var d = await af(A + "/personas/" + dni + "/arbol?profundidad=3");
        var t = "👤 " + d.raiz.nombre_completo + " (DNI: " + d.raiz.dni + ")\n"
        if (d.ascendentes.length > 0) { t += "\n▲ ASCENDENTES:\n"; d.ascendentes.forEach(function(n) { t += fan(n, "", true); }); }
        if (d.descendentes.length > 0) { t += "\n▼ DESCENDENTES:\n"; d.descendentes.forEach(function(n) { t += fan(n, "", false); }); }
        ct_.textContent = t;
    } catch (err) { ct_.textContent = "Error: " + err.message; }
};

function fan(no, px, il) {
    var conn = il ? "└─ " : "├─ ";
    var l = px + (px ? conn : "") + no.persona.nombre_completo + "\n";
    if (no.hijos && no.hijos.length > 0) {
        no.hijos.forEach(function(ch, i) {
            var last = i === no.hijos.length - 1;
            var np = px + (px ? (il ? "   " : "│  ") : "");
            l += fan(ch, np, last);
        });
    }
    return l;
}

/* ─── Empresa Modal ─── */
document.getElementById("btn-nueva-empresa").addEventListener("click", function() {
    document.getElementById("form-empresa").reset();
    AppState.set("editandoEmpresaRuc", null);
    document.getElementById("modal-empresa-title").textContent = "Nueva Empresa";
    document.querySelector("#form-empresa button[type=submit]").textContent = "Guardar Empresa";
    om("modal-empresa");
});

document.getElementById("form-empresa").addEventListener("submit", async function(e) {
    e.preventDefault();

    // Datos base del formulario visible
    var b = {
        ruc: document.getElementById("e-ruc").value.trim(),
        nombre: document.getElementById("e-nombre").value.trim(),
        direccion: document.getElementById("e-direccion").value.trim() || null,
        notas: document.getElementById("e-notas").value.trim() || null,
    };

    // Agregar datos SUNAT desde la ultima consulta (si existe)
    var consultaData = window._ultimaConsultaRuc;
    if (consultaData && consultaData.numero === b.ruc) {
        if (!b.direccion && consultaData.direccion) b.direccion = consultaData.direccion;
        if (consultaData.estado) b.estado = consultaData.estado;
        if (consultaData.condicion) b.condicion = consultaData.condicion;
        if (consultaData.tipo_contribuyente) b.tipo_contribuyente = consultaData.tipo_contribuyente;
        if (consultaData.nombre_comercial) b.nombre_comercial = consultaData.nombre_comercial;
        if (consultaData.fecha_inscripcion) b.fecha_inscripcion = consultaData.fecha_inscripcion;
        if (consultaData.fecha_inicio_actividades) b.fecha_inicio_actividades = consultaData.fecha_inicio_actividades;
        if (consultaData.sistema_contabilidad) b.sistema_contabilidad = consultaData.sistema_contabilidad;
        if (consultaData.actividad_comercio_exterior) b.actividad_comercio_exterior = consultaData.actividad_comercio_exterior;
        if (consultaData.actividad_economica) b.actividad_economica = consultaData.actividad_economica;
        if (consultaData.comprobantes_autorizados) b.comprobantes_autorizados = consultaData.comprobantes_autorizados;
        if (consultaData.sistema_emision) b.sistema_emision = consultaData.sistema_emision;
        if (consultaData.afiliado_ple) b.afiliado_ple = consultaData.afiliado_ple;
        if (consultaData.representante_legal) {
            b.representante_legal_dni = consultaData.representante_legal.dni;
            b.representante_legal_nombre = consultaData.representante_legal.nombre;
        }
    }

    try {
        if (AppState.get("editandoEmpresaRuc")) {
            await af(A + "/empresas/" + AppState.get("editandoEmpresaRuc"), { method: "PUT", body: JSON.stringify(b) });
            st("Empresa actualizada", "success");
            cm("modal-empresa");
            document.getElementById("form-empresa").reset();
            AppState.set("editandoEmpresaRuc", null);
            window._ultimaConsultaRuc = null;
            cfEmpresa(b.ruc);
        } else {
            await af(A + "/empresas", { method: "POST", body: JSON.stringify(b) });
            st("Empresa creada", "success");
            cm("modal-empresa");
            document.getElementById("form-empresa").reset();
            window._ultimaConsultaRuc = null;
            cfEmpresa(b.ruc);
        }
    } catch (err) { st(err.message, "error"); }
});

window.editarEmpresa = function(ruc) {
    document.getElementById("modal-empresa-title").textContent = "Editar Empresa";
    document.querySelector("#form-empresa button[type=submit]").textContent = "Guardar Cambios";
    AppState.set("editandoEmpresaRuc", null);
    af(A + "/empresas/" + ruc).then(function(d) {
        var e = d.empresa;
        AppState.set("editandoEmpresaRuc", e.ruc);
        document.getElementById("e-ruc").value = e.ruc;
        document.getElementById("e-nombre").value = e.nombre || "";
        document.getElementById("e-direccion").value = e.direccion || "";
        document.getElementById("e-notas").value = e.notas || "";
        om("modal-empresa");
    }).catch(function(err) { st(err.message, "error"); });
};

/* ─── Vincular Persona ↔ Empresa ─── */
window.abrirVincularEmpresa = function(dni) {
    document.getElementById("form-vincular-empresa").reset();
    document.getElementById("ve-dni").value = dni;
    document.getElementById("ve-cargo-otro-group").style.display = "none";
    om("modal-vincular-empresa");
};

document.getElementById("ve-cargo").addEventListener("change", function() {
    document.getElementById("ve-cargo-otro-group").style.display = this.value === "otro" ? "block" : "none";
});

document.getElementById("form-vincular-empresa").addEventListener("submit", async function(e) {
    e.preventDefault();
    var cargo = document.getElementById("ve-cargo").value;
    if (cargo === "otro") cargo = document.getElementById("ve-cargo-otro").value.trim() || "trabajador";
    var b = {
        persona_dni: document.getElementById("ve-dni").value.trim(),
        empresa_ruc: document.getElementById("ve-ruc").value.trim(),
        cargo: cargo,
        fecha_desde: document.getElementById("ve-fecha-desde").value || null,
        fecha_hasta: document.getElementById("ve-fecha-hasta").value || null,
        observacion: document.getElementById("ve-obs").value.trim() || null,
    };
    try {
        var r_ = await af(A + "/persona-empresa", { method: "POST", body: JSON.stringify(b) });
        st(r_.mensaje || "Vinculado", "success");
        cm("modal-vincular-empresa");
        document.getElementById("form-vincular-empresa").reset();
        cf(b.persona_dni);
    } catch (err) { st(err.message, "error"); }
});

/* ─── Etiqueta Persona ─── */
function abrirEtiqueta(dni) { document.getElementById("e-dni").value = dni; document.getElementById("etq-nombre").value = ""; document.getElementById("e-obs").value = ""; om("modal-etiqueta"); }
window.abrirEtiqueta = abrirEtiqueta;

document.getElementById("form-etiqueta").addEventListener("submit", async function(e) {
    e.preventDefault();
    var dni = document.getElementById("e-dni").value;
    var b = { etiqueta_nombre: document.getElementById("etq-nombre").value.trim(), observacion: document.getElementById("e-obs").value.trim() || null };
    try { await af(A + "/personas/" + dni + "/etiquetas", { method: "POST", body: JSON.stringify(b) }); st("Etiqueta asignada", "success"); cm("modal-etiqueta"); document.getElementById("form-etiqueta").reset(); cf(dni); }
    catch (err) { st(err.message, "error"); }
});

/* ─── Etiqueta Empresa ─── */
function abrirEtiquetaEmpresa(ruc) { document.getElementById("ee-ruc").value = ruc; document.getElementById("ee-nombre").value = ""; document.getElementById("ee-obs").value = ""; om("modal-etiqueta-empresa"); }
window.abrirEtiquetaEmpresa = abrirEtiquetaEmpresa;

document.getElementById("form-etiqueta-empresa").addEventListener("submit", async function(e) {
    e.preventDefault();
    var ruc = document.getElementById("ee-ruc").value;
    var b = { etiqueta_nombre: document.getElementById("ee-nombre").value.trim(), observacion: document.getElementById("ee-obs").value.trim() || null };
    try { await af(A + "/empresas/" + ruc + "/etiquetas", { method: "POST", body: JSON.stringify(b) }); st("Etiqueta asignada a empresa", "success"); cm("modal-etiqueta-empresa"); document.getElementById("form-etiqueta-empresa").reset(); cfEmpresa(ruc); }
    catch (err) { st(err.message, "error"); }
});

/* ─── Editar Persona ─── */
window.editarPersona = function(dni) {
    document.getElementById("modal-persona-title").textContent = "Editar Persona";
    var btn = document.querySelector("#form-persona button[type=submit]");
    btn.textContent = "Guardar Cambios";
    document.getElementById("p-dni").disabled = true;
    AppState.set("editandoDni", null);
    af(A + "/personas/" + dni).then(function(d) {
        var p = d.persona;
        AppState.set("editandoDni", dni);
        document.getElementById("p-dni").value = p.dni;
        document.getElementById("p-nombres").value = p.nombres || "";
        document.getElementById("p-ap-paterno").value = p.apellido_paterno || "";
        document.getElementById("p-ap-materno").value = p.apellido_materno || "";
        document.getElementById("p-fecha-nac").value = p.fecha_nacimiento || "";
        document.getElementById("p-foto").value = p.foto_url || "";
        document.getElementById("p-notas").value = p.notas || "";
        om("modal-persona");
    }).catch(function(err) { st(err.message, "error"); });
};

/* ─── Form Persona ─── */
document.getElementById("form-persona").addEventListener("submit", async function(e) {
    e.preventDefault();
    var b = { nombres: document.getElementById("p-nombres").value.trim(), apellido_paterno: document.getElementById("p-ap-paterno").value.trim(), apellido_materno: document.getElementById("p-ap-materno").value.trim() || null, fecha_nacimiento: document.getElementById("p-fecha-nac").value || null, foto_url: document.getElementById("p-foto").value.trim() || null, notas: document.getElementById("p-notas").value.trim() || null };
    if (AppState.get("editandoDni")) {
        b.dni = document.getElementById("p-dni").value.trim();
        try { await af(A + "/personas/" + AppState.get("editandoDni"), { method: "PUT", body: JSON.stringify(b) }); st("Persona actualizada", "success"); cm("modal-persona"); document.getElementById("form-persona").reset(); AppState.set("editandoDni", null); document.getElementById("modal-persona-title").textContent = "Nueva Persona"; document.querySelector("#form-persona button[type=submit]").textContent = "Guardar Persona"; document.getElementById("p-dni").disabled = false; cf(b.dni); }
        catch (err) { st(err.message, "error"); }
    } else {
        b.dni = document.getElementById("p-dni").value.trim();
        try { await af(A + "/personas", { method: "POST", body: JSON.stringify(b) }); st("Persona creada", "success"); cm("modal-persona"); document.getElementById("form-persona").reset(); cf(b.dni); }
        catch (err) { st(err.message, "error"); }
    }
});

/* ─── Form Relacion ─── */
document.getElementById("form-relacion").addEventListener("submit", async function(e) {
    e.preventDefault();
    var b = { persona_origen_dni: document.getElementById("r-origen").value.trim(), persona_destino_dni: document.getElementById("r-destino").value.trim(), tipo_relacion: document.getElementById("r-tipo").value, certeza: document.getElementById("r-certeza").value, notas: document.getElementById("r-notas").value.trim() || null };
    try { var r_ = await af(A + "/relaciones", { method: "POST", body: JSON.stringify(b) }); st(r_.mensaje || "Relacion creada", "success"); cm("modal-relacion"); document.getElementById("form-relacion").reset(); var fd = document.getElementById("persona-ficha"); if (!fd.classList.contains("hidden")) { var dn = fd.querySelector(".ficha-dni"); if (dn) cf(dn.textContent.replace("DNI: ", "")); } }
    catch (err) { st(err.message, "error"); }
});

/* ─── Header buttons ─── */
document.getElementById("btn-nueva-persona").addEventListener("click", function() { document.getElementById("form-persona").reset(); AppState.set("editandoDni", null); document.getElementById("p-dni").disabled = false; document.getElementById("modal-persona-title").textContent = "Nueva Persona"; document.querySelector("#form-persona button[type=submit]").textContent = "Guardar Persona"; om("modal-persona"); });
document.getElementById("btn-nueva-relacion").addEventListener("click", function() { document.getElementById("form-relacion").reset(); om("modal-relacion"); });

/* ─── Etiquetas List ─── */
document.getElementById("btn-etiquetas").addEventListener("click", async function() {
    om("modal-lista-etiquetas");
    var ct = document.getElementById("lista-etiquetas-content");
    ct.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando...</p>';
    try {
        var ets = await af(A + "/etiquetas");
        if (ets.length === 0) { ct.innerHTML = '<p class="no-results">No hay etiquetas.</p>'; return; }
        ct.innerHTML = '<div style="margin-bottom:12px;color:var(--color-text-secondary);font-size:0.85rem;">' + ets.length + ' etiquetas — Click en una para ver sus elementos</div>';
        ct.innerHTML += ets.map(function(et) {
            return '<div class="etiqueta-list-item" data-nombre="' + es(et.nombre) + '"><span>🏷 <strong>' + es(et.nombre) + '</strong></span><span style="display:flex;gap:6px;"><button class="btn-edit-tag btn btn-xs btn-ghost" data-id="' + et.id + '" data-nombre="' + es(et.nombre) + '">✏️</button><span style="color:var(--color-text-secondary);font-size:0.82rem;">→</span></span></div>';
        }).join("");
        ct.querySelectorAll(".etiqueta-list-item").forEach(function(it) {
            it.addEventListener("click", async function(e) {
                if (e.target.closest(".btn-edit-tag")) return;
                var n = it.dataset.nombre;
                try {
                    var pl = await af(A + "/etiquetas/" + encodeURIComponent(n) + "/personas");
                    var el = await af(A + "/etiquetas/" + encodeURIComponent(n) + "/empresas");
                    if ((pl && pl.length === 0) && (el && el.length === 0)) { st('Ningun elemento con "' + n + '"', "info"); return; }
                    cm("modal-lista-etiquetas");
                    var items = [];
                    if (pl) pl.forEach(function(p) { items.push({ label: "👤 " + p.nombre_completo, dni: p.dni, type: "persona" }); });
                    if (el) el.forEach(function(e2) { items.push({ label: "🏢 " + e2.nombre, ruc: e2.ruc, type: "empresa" }); });
                    if (items.length === 1) {
                        if (items[0].type === "persona") cf(items[0].dni);
                        else cfEmpresa(items[0].ruc);
                        return;
                    }
                    var sr_ = document.getElementById("search-results");
                    sr_.innerHTML = items.map(function(it) {
                        var attr = it.type === "persona" ? 'data-dni="' + it.dni + '"' : 'data-ruc="' + it.ruc + '"';
                        return '<div class="search-result-item" ' + attr + ' data-type="' + it.type + '"><span>' + it.label + '</span></div>';
                    }).join("");
                    sr_.querySelectorAll(".search-result-item").forEach(function(el2) {
                        el2.addEventListener("click", function() { sr_.classList.add("hidden"); if (el2.dataset.type === "persona") cf(el2.dataset.dni); else cfEmpresa(el2.dataset.ruc); });
                    });
                    sr_.classList.remove("hidden");
                } catch (err) { st(err.message, "error"); }
            });
        });
        ct.querySelectorAll(".btn-edit-tag").forEach(function(btn) {
            btn.addEventListener("click", async function(e) {
                e.stopPropagation();
                var nuevo = prompt("Nuevo nombre para esta etiqueta:", btn.dataset.nombre);
                if (!nuevo || nuevo === btn.dataset.nombre) return;
                try { await af(A + "/etiquetas/" + btn.dataset.id, { method: "PUT", body: JSON.stringify({ nombre: nuevo }) }); st("Etiqueta renombrada", "success"); document.getElementById("btn-etiquetas").click(); }
                catch (err) { st(err.message, "error"); }
            });
        });
    } catch (err) { ct.innerHTML = '<p class="no-results">Error: ' + es(err.message) + '</p>'; }
});

/* ─── Visor BD ─── */
document.getElementById("btn-visorbd").addEventListener("click", function() { cv(); });
function cv() {
    om("modal-visorbd");
    var ct = document.getElementById("visorbd-content");
    ct.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando BD...</p>';
    af(A + "/db/todas").then(function(ps) {
        if (ps.length === 0) { ct.innerHTML = '<p class="no-results">BD vacía.</p>'; return; }
        var h = '<p style="margin-bottom:12px;color:var(--color-text-secondary);">' + ps.length + ' personas</p><div style="overflow-x:auto;"><table class="db-table"><thead><tr><th>DNI</th><th>Nombre</th><th>Nacimiento</th><th>Notas</th><th></th><th></th></tr></thead><tbody>';
        ps.forEach(function(p) {
            var fn = p.fecha_nacimiento ? new Date(p.fecha_nacimiento + "T00:00:00").toLocaleDateString("es-PE") : "\u2014";
            h += '<tr><td>' + es(p.dni) + '</td><td><strong>' + es(p.nombre_completo) + '</strong></td><td>' + fn + '</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (p.notas ? es(p.notas) : "\u2014") + '</td>';
            h += '<td><button class="btn btn-primary btn-xs btn-ver-bd" data-dni="' + es(p.dni) + '">Ver</button></td>';
            h += '<td><button class="btn btn-danger btn-xs btn-del-bd" data-dni="' + es(p.dni) + '" title="Eliminar">🗑</button></td></tr>';
        });
        h += '</tbody></table></div>';
        ct.innerHTML = h;
        ct.querySelectorAll(".btn-ver-bd").forEach(function(btn) { btn.addEventListener("click", function() { cm("modal-visorbd"); cf(btn.dataset.dni); }); });
        ct.querySelectorAll(".btn-del-bd").forEach(function(btn) { btn.addEventListener("click", async function() { if (!confirm("Eliminar a " + btn.dataset.dni + "?")) return; try { await af(A + "/personas/" + btn.dataset.dni, { method: "DELETE" }); st("Persona eliminada", "success"); cv(); } catch (err) { st(err.message, "error"); } }); });
    }).catch(function(err) { ct.innerHTML = '<p class="no-results">Error: ' + es(err.message) + '</p>'; });
}

/* ─── Visor Empresas ─── */
document.getElementById("btn-visorempresas").addEventListener("click", function() { cvEmpresas(); });
function cvEmpresas() {
    om("modal-visorempresas");
    var ct = document.getElementById("visorempresas-content");
    ct.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando empresas...</p>';
    af(A + "/empresas/todas").then(function(emps) {
        if (emps.length === 0) { ct.innerHTML = '<p class="no-results">No hay empresas registradas.</p>'; return; }
        var h = '<p style="margin-bottom:12px;color:var(--color-text-secondary);display:flex;justify-content:space-between;align-items:center;"><span>' + emps.length + ' empresas</span><button class="btn btn-outline btn-sm" onclick="enriquecerTodasEmpresas()">🔄 Enriquecer todas desde SUNAT</button></p><div style="overflow-x:auto;"><table class="db-table"><thead><tr><th>RUC</th><th>Nombre</th><th>Estado</th><th></th><th></th></tr></thead><tbody>';
        emps.forEach(function(e) {
            var estadoHtml = e.estado ? '<span class="status-badge status-' + es(e.estado.toLowerCase()) + '">' + es(e.estado) + '</span>' : "\u2014";
            h += '<tr><td>' + es(e.ruc) + '</td><td><strong>' + es(e.nombre) + '</strong></td><td>' + estadoHtml + '</td>';
            h += '<td><button class="btn btn-primary btn-xs btn-ver-empresa" data-ruc="' + es(e.ruc) + '">Ver</button></td>';
            h += '<td><button class="btn btn-danger btn-xs btn-del-empresa" data-ruc="' + es(e.ruc) + '" title="Eliminar">🗑</button></td></tr>';
        });
        h += '</tbody></table></div>';
        ct.innerHTML = h;
        ct.querySelectorAll(".btn-ver-empresa").forEach(function(btn) { btn.addEventListener("click", function() { cm("modal-visorempresas"); cfEmpresa(btn.dataset.ruc); }); });
        ct.querySelectorAll(".btn-del-empresa").forEach(function(btn) { btn.addEventListener("click", async function() { if (!confirm("Eliminar empresa?")) return; try { await af(A + "/empresas/" + btn.dataset.ruc, { method: "DELETE" }); st("Empresa eliminada", "success"); cvEmpresas(); } catch (err) { st(err.message, "error"); } }); });
    }).catch(function(err) { ct.innerHTML = '<p class="no-results">Error: ' + es(err.message) + '</p>'; });
}

/* ─── Importar (unificado) ─── */
var IMP_HINTS = {
    auto: "Pegue cualquier formato soportado (CSV, batch RUC, macro SUNAT, reporte LEDER o export de Telegram) y el sistema detectará automáticamente cuál es.",
    csv: "Formato: DNI,Nombres,ApellidoPaterno,ApellidoMaterno (una persona por línea).",
    ruc_batch: "Pegue un listado tabulado de RUC + nombre, una fila por línea: 10011477432\tCORIAT CELIS ENRIQUE",
    sunat_macro: "Pegue los datos extraídos con la macro SUNAT (formato tabulado de 21 columnas). Soporta RUC 10 (persona natural + empresa + vínculo), RUC 20/30 (empresa jurídica) y representantes legales.",
    leder_individual: "Pegue el reporte individual de LEDER DATA (bloques DNI/NOMBRES/APELLIDOS/...).",
    leder_telegram: "Pegue o arrastra el texto exportado de Telegram con las respuestas del bot @LEDER_DATA_BOT. Se detecta automáticamente META, FAMILIA, EMPRESAS, SUNAT y datos complementarios.",
    transparencia: "Datos de ordenes de compra/servicio (OC/OS) del portal de transparencia. Puedes pegar los datos manualmente o arrastrar archivos .xlsx directamente. 12 columnas tabuladas: N°, Tipo de Orden, Número de orden, Tipo de Contratación, Descripción, Nro. Exp. SIAF, Fecha de Emisión, Fecha de Compromiso, Estado, Monto, RUC, Denominación. Las filas con Estado 'Anulada' se omiten automaticamente.",
};
var IMP_PLACEHOLDERS = {
    auto: "Pegue aquí los datos a importar (cualquier formato soportado)...",
    csv: "12345678,Juan Carlos,Olano,Romero\n87654321,María Rosa,García,López",
    ruc_batch: "10011477432\tCORIAT CELIS ENRIQUE\n10027726459\tJARAMILLO CALLE RICARDO",
    sunat_macro: "INGRESAR EL NUMERO DE RUC | Número de RUC: | Tipo Contribuyente: | ...\n10027726459 | 10027726459 - JARAMILLO CALLE RICARDO MERCEDES | PERSONA NATURAL SIN NEGOCIO...",
    leder_individual: "DNI: 12345678\nNOMBRES: JUAN CARLOS\nAPELLIDOS: OLANO ROMERO\n...",
    leder_telegram: "Pegue aquí el contenido de los archivos HTML exportados de Telegram...",
    transparencia: "1\tO/C\t17\tContrataciones hasta 8 UIT\tADQUISICION DE UTILES...\t243\t2023-02-06\t2023-02-06\tDevengada\tS/. 647\t20601755379\tNAUH BUSINESS GROUP E.I.R.L",
};

function impActualizarVista() {
    var formato = document.getElementById("imp-formato").value;
    document.getElementById("imp-hint").textContent = IMP_HINTS[formato] || "";
    // Dropzone visible siempre (se auto-detecta el formato al arrastrar)
    document.getElementById("imp-dropzone-wrap").classList.remove("hidden");
    document.getElementById("imp-hint-list").classList.toggle("hidden", formato !== "leder_telegram");
    document.getElementById("imp-etiqueta-wrap").classList.toggle("hidden", formato === "leder_telegram");
    document.getElementById("btn-imp-debug").classList.toggle("hidden", formato !== "leder_telegram");
    document.getElementById("imp-textarea").placeholder = IMP_PLACEHOLDERS[formato] || "";
    // Actualizar hint del dropzone segun formato
    var dzText = document.querySelector("#imp-dropzone div:last-child");
    if (formato === "transparencia" && dzText) {
        dzText.textContent = "o haz clic para seleccionar (.xlsx)";
    } else if (dzText) {
        dzText.textContent = "o haz clic para seleccionar";
    }
}

document.getElementById("imp-formato").addEventListener("change", impActualizarVista);

document.getElementById("btn-importar").addEventListener("click", function() {
    document.getElementById("form-importar").reset();
    document.getElementById("imp-resultado").classList.add("hidden");
    document.getElementById("li-file-names").textContent = "";
    impActualizarVista();
    om("modal-importar");
});

document.getElementById("form-importar").addEventListener("submit", async function(e) {
    e.preventDefault();
    var formato = document.getElementById("imp-formato").value;
    var raw = document.getElementById("imp-textarea").value.trim();
    if (!raw) { st("No hay datos para importar", "error"); return; }
    var tag = document.getElementById("imp-etiqueta").value.trim();
    var btn = document.querySelector("#form-importar button[type=submit]");
    btn.disabled = true; btn.textContent = "Importando...";

    try {
        var body = { texto: raw, formato: formato };
        if (tag) body.etiqueta = tag;

        // El formato "csv" se valida y estructura en el cliente antes de enviarse.
        if (formato === "csv") {
            var lines = raw.split("\n");
            var ps = [];
            for (var i = 0; i < lines.length; i++) {
                var ln = lines[i].trim(); if (!ln) continue;
                var p = ln.split(","); if (p.length < 3) continue;
                ps.push({ dni: (p[0]||"").trim(), nombres: (p[1]||"").trim(), apellido_paterno: (p[2]||"").trim(), apellido_materno: (p[3]||"").trim()||null, fecha_nacimiento: null, foto_url: null, notas: null });
            }
            if (ps.length === 0) { st("No hay datos CSV validos", "error"); btn.disabled = false; btn.textContent = "Importar"; return; }
            body.personas = ps;
            delete body.texto;
        }

        var r = await af(A + "/importar", { method: "POST", body: JSON.stringify(body) });
        var div = document.getElementById("imp-resultado");
        div.classList.remove("hidden");
        var hasError = r.errores && r.errores.length > 0;
        div.style.background = hasError ? "#fef2f2" : "#f0fdf4";
        div.style.border = hasError ? "1px solid #fca5a5" : "1px solid #bbf7d0";

        var html = "<strong>" + es(r.mensaje) + "</strong>";
        if (r.formato_detectado) html += '<br><small style="color:var(--color-text-tertiary);">Formato detectado: ' + es(r.formato_detectado) + "</small>";
        html += '<div style="margin-top:8px;font-size:0.85rem;display:grid;grid-template-columns:1fr 1fr;gap:4px;">';
        if (r.personas_creadas)            html += '<span>👤 Personas: ' + r.personas_creadas + '</span>';
        if (r.empresas_creadas)            html += '<span>🏢 Empresas: ' + r.empresas_creadas + '</span>';
        if (r.empresas_actualizadas)       html += '<span>🔄 Actualizadas: ' + r.empresas_actualizadas + '</span>';
        if (r.vinculos_creados)            html += '<span>🔗 Vínculos: ' + r.vinculos_creados + '</span>';
        if (r.representantes_vinculados)   html += '<span>⚖️ Rep. Legales: ' + r.representantes_vinculados + '</span>';
        if (r.relaciones_creadas)          html += '<span>👨‍👩‍👧‍👦 Relaciones: ' + r.relaciones_creadas + '</span>';
        if (r.etiquetados)                 html += '<span>🏷 Etiquetados: ' + r.etiquetados + '</span>';
        html += '</div>';
        if (r.persona_dni) { html += '<button class="btn btn-outline btn-xs" style="margin-top:8px;" onclick="cm(\'modal-importar\'); cf(\'' + r.persona_dni + '\')">Ver ficha de ' + r.persona_dni + "</button>"; }

        if (r.errores && r.errores.length > 0) {
            html += '<div style="margin-top:8px;font-size:0.8rem;color:#dc2626;max-height:100px;overflow-y:auto;">';
            r.errores.slice(0, 5).forEach(function(err) { html += '<div>⚠ ' + es(err) + '</div>'; });
            if (r.errores.length > 5) html += '<div>... y ' + (r.errores.length - 5) + ' más</div>';
            html += '</div>';
        }
        div.innerHTML = html;
        st(r.mensaje, hasError ? "error" : "success");
    } catch (err) { st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "Importar";
});

/* ─── Dropzone: click y drag&drop (funciona para leder_telegram y transparencia) ─── */
document.getElementById("imp-dropzone").addEventListener("click", function() {
    document.getElementById("imp-file-input").click();
});
document.getElementById("imp-file-input").addEventListener("change", function(e) {
    if (e.target.files.length > 0) procesarArchivosImport(e.target.files);
    e.target.value = "";
});
document.getElementById("imp-dropzone").addEventListener("dragover", function(e) {
    e.preventDefault();
    this.style.borderColor = "#2563eb";
    this.style.background = "#eff6ff";
});
document.getElementById("imp-dropzone").addEventListener("dragleave", function(e) {
    e.preventDefault();
    this.style.borderColor = "#94a3b8";
    this.style.background = "#f8fafc";
});
document.getElementById("imp-dropzone").addEventListener("drop", function(e) {
    e.preventDefault();
    this.style.borderColor = "#94a3b8";
    this.style.background = "#f8fafc";
    if (e.dataTransfer.files.length > 0) procesarArchivosImport(e.dataTransfer.files);
});

function excelToTSV(data) {
    /* Convierte un workbook de SheetJS a texto tab-separated */
    var ws = data.Sheets[data.SheetNames[0]];
    var ref = ws["!ref"];
    if (!ref) return "";
    var range = XLSX.utils.decode_range(ref);
    var lines = [];
    for (var r = range.s.r; r <= range.e.r; r++) {
        var cols = [];
        for (var c = range.s.c; c <= range.e.c; c++) {
            var addr = XLSX.utils.encode_cell({ r: r, c: c });
            var cell = ws[addr];
            var val = cell ? cell.v : "";
            // Convert date serial to string
            if (cell && cell.t === "d") {
                val = val.toISOString ? val.toISOString().split("T")[0] : val;
            }
            cols.push(val !== undefined && val !== null ? String(val) : "");
        }
        lines.push(cols.join("\t"));
    }
    return lines.join("\n");
}

function procesarArchivosImport(files) {
    if (!files || files.length === 0) return;
    var formato = document.getElementById("imp-formato").value;
    var ta = document.getElementById("imp-textarea");
    var names = document.getElementById("li-file-names");
    var namesList = [];
    var total = files.length;
    var loaded = 0;

    // Auto-detectar formato segun tipo de archivo
    var hasExcel = false;
    var hasHtml = false;
    for (var fi = 0; fi < total; fi++) {
        if (/\.xlsx?$/i.test(files[fi].name)) hasExcel = true;
        else if (/\.html?$/i.test(files[fi].name)) hasHtml = true;
    }
    if (hasExcel && !hasHtml && (formato === "auto" || formato === "transparencia")) {
        document.getElementById("imp-formato").value = "transparencia";
        impActualizarVista();
    } else if (hasHtml && !hasExcel && (formato === "auto" || formato === "leder_telegram")) {
        document.getElementById("imp-formato").value = "leder_telegram";
        impActualizarVista();
    }

    names.textContent = "Leyendo " + total + " archivo(s)...";

    for (var i = 0; i < total; i++) {
        (function(file) {
            var isExcel = /\.xlsx?$/i.test(file.name);
            var shouldUseSheetJS = isExcel && (formato === "transparencia" || formato === "auto");

            if (shouldUseSheetJS && typeof XLSX !== "undefined") {
                /* Leer Excel con SheetJS */
                var reader = new FileReader();
                reader.onload = function(e) {
                    try {
                        var data = new Uint8Array(e.target.result);
                        var wb = XLSX.read(data, { type: "array" });
                        var tsv = excelToTSV(wb);
                        if (tsv) {
                            if (ta.value) ta.value += "\n\n";
                            ta.value += tsv;
                        }
                        namesList.push(file.name);
                        loaded++;
                        names.textContent = "✅ " + loaded + "/" + total + " archivo(s): " + namesList.join(", ");
                    } catch (err) {
                        names.textContent = "⚠ Error al leer " + file.name;
                        loaded++;
                    }
                    if (loaded === total && loaded > 0) {
                        names.textContent = "✅ " + total + " archivo(s) cargados: " + namesList.join(", ");
                    }
                };
                reader.readAsArrayBuffer(file);
            } else {
                /* Leer como texto (HTML/TXT para LEDER) */
                var reader = new FileReader();
                reader.onload = function(e) {
                    if (ta.value) ta.value += "\n\n--- " + file.name + " ---\n\n";
                    ta.value += e.target.result;
                    namesList.push(file.name);
                    loaded++;
                    names.textContent = "📄 " + namesList.join(", ");
                    if (loaded === total) {
                        names.textContent = "✅ " + total + " archivo(s) cargados: " + namesList.join(", ");
                    }
                };
                reader.readAsText(file, "UTF-8");
            }
        })(files[i]);
    }
}

window.lederDropFiles = procesarArchivosImport;
window.lederDebug = async function() {
    var raw = document.getElementById("imp-textarea").value.trim();
    if (!raw) { st("Pega o arrastra archivos primero", "error"); return; }
    try {
        var r = await af(A + "/importar/debug", { method: "POST", body: JSON.stringify({ texto: raw }) });
        var div = document.getElementById("imp-resultado");
        div.classList.remove("hidden");
        div.style.background = "#f8fafc";
        div.style.border = "1px solid #94a3b8";
        var html = "<strong>🔍 Debug - " + r.total_partes + " partes, " + r.partes_procesables + " procesables</strong>";
        if (r.conteo_tipos) {
            html += '<div style="margin-top:8px;font-size:0.85rem;display:flex;flex-wrap:wrap;gap:6px;">';
            Object.keys(r.conteo_tipos).forEach(function(t) {
                html += '<span style="background:#e2e8f0;padding:2px 8px;border-radius:4px;">' + t + ': ' + r.conteo_tipos[t] + '</span>';
            });
            html += '</div>';
        }
        if (r.metas_no_detectadas !== undefined && r.metas_no_detectadas > 0) {
            html += '<div style="margin-top:6px;color:#dc2626;font-weight:500;">⚠ ' + r.metas_no_detectadas + ' posibles META no detectados</div>';
            if (r.ejemplo_meta_perdida) {
                html += '<pre style="font-size:0.75rem;max-height:100px;overflow:auto;margin-top:4px;padding:8px;background:#1e293b;color:#fbbf24;border-radius:6px;">' + es(r.ejemplo_meta_perdida) + '</pre>';
            }
        }
        html += '<pre style="font-size:0.75rem;max-height:200px;overflow:auto;margin-top:8px;padding:8px;background:#1e293b;color:#e2e8f0;border-radius:6px;">' + es(r.primeros_300_chars) + '</pre>';
        if (r.partes && r.partes.length > 0) {
            html += '<div style="margin-top:8px;font-size:0.8rem;">';
            r.partes.forEach(function(p) {
                var color = p.tipo ? "#16a34a" : "#94a3b8";
                html += '<div style="padding:4px 0;border-bottom:1px solid #e2e8f0;"><span style="color:' + color + ';font-weight:500;">#' + p.idx + '</span> ';
                html += '<span style="color:' + color + ';">' + (p.tipo || "sin tipo") + '</span> ';
                if (p.dni) html += '<span style="color:#2563eb;">DNI:' + p.dni + '</span> ';
                html += '<span style="color:#64748b;">' + p.len + 'ch</span> ';
                if (p.bloques_personas > 0) html += '<span style="color:#9333ea;">' + p.bloques_personas + ' pers</span> ';
                html += '</div>';
            });
            html += '</div>';
        } else {
            html += '<div style="margin-top:8px;color:#dc2626;">⚠ No se detectaron partes con [#LEDER_BOT]. El texto no tiene el formato esperado.</div>';
        }
        div.innerHTML = html;
    } catch (err) { st(err.message, "error"); }
};

/* ─── Dashboard ─── */
document.getElementById("btn-dashboard").addEventListener("click", function() { cargarDashboard(); });
async function cargarDashboard() {
    om("modal-dashboard");
    var ct = document.getElementById("dashboard-content");
    ct.innerHTML = '<span class="spinner"></span> Cargando stats...';
    try {
        var s = await af(A + "/stats");
        var h = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">';
        h += '<div class="stat-card"><div class="stat-num">' + s.total_personas + '</div><div class="stat-label">Personas</div></div>';
        h += '<div class="stat-card"><div class="stat-num">' + s.total_relaciones + '</div><div class="stat-label">Relaciones</div></div>';
        h += '<div class="stat-card"><div class="stat-num">' + s.total_empresas + '</div><div class="stat-label">Empresas</div></div>';
        h += '<div class="stat-card"><div class="stat-num">' + s.total_persona_empresa + '</div><div class="stat-label">Vínculos</div></div>';
        h += '</div>';
        var chartsCount = 0;
        if (s.personas_por_etiqueta && s.personas_por_etiqueta.length > 0) chartsCount++;
        if (s.personas_por_empresa && s.personas_por_empresa.length > 0) chartsCount++;
        if (s.empresas_por_etiqueta && s.empresas_por_etiqueta.length > 0) chartsCount++;
        if (chartsCount > 0) {
            var cols = Math.min(chartsCount, 3);
            h += '<div style="display:grid;grid-template-columns:repeat(' + cols + ',1fr);gap:16px;">';
            if (s.personas_por_etiqueta && s.personas_por_etiqueta.length > 0) {
                h += '<div><h4 style="margin-bottom:8px;">Personas por Etiqueta</h4><canvas id="chart-tags" height="200"></canvas></div>';
            }
            if (s.personas_por_empresa && s.personas_por_empresa.length > 0) {
                h += '<div><h4 style="margin-bottom:8px;">Personas por Empresa</h4><canvas id="chart-empresas" height="200"></canvas></div>';
            }
            if (s.empresas_por_etiqueta && s.empresas_por_etiqueta.length > 0) {
                h += '<div><h4 style="margin-bottom:8px;">Empresas por Etiqueta</h4><canvas id="chart-emp-tags" height="200"></canvas></div>';
            }
            h += '</div>';
        }
        ct.innerHTML = h;
        setTimeout(function() {
            if (document.getElementById("chart-tags")) {
                var ctx1 = document.getElementById("chart-tags").getContext("2d");
                new Chart(ctx1, { type: "bar", data: { labels: s.personas_por_etiqueta.map(function(x){return x.nombre.substring(0,20)}), datasets: [{ label: "Personas", data: s.personas_por_etiqueta.map(function(x){return x.cantidad}), backgroundColor: "rgba(37,99,235,0.7)" }] }, options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
            }
            if (document.getElementById("chart-empresas") && s.personas_por_empresa.length > 0) {
                var ctx2 = document.getElementById("chart-empresas").getContext("2d");
                new Chart(ctx2, { type: "bar", data: { labels: s.personas_por_empresa.map(function(x){return x.empresa.substring(0,25)}), datasets: [{ label: "Personas", data: s.personas_por_empresa.map(function(x){return x.cantidad}), backgroundColor: "rgba(99,102,241,0.7)" }] }, options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
            }
            if (document.getElementById("chart-emp-tags") && s.empresas_por_etiqueta.length > 0) {
                var ctx3 = document.getElementById("chart-emp-tags").getContext("2d");
                new Chart(ctx3, { type: "bar", data: { labels: s.empresas_por_etiqueta.map(function(x){return x.nombre.substring(0,20)}), datasets: [{ label: "Empresas", data: s.empresas_por_etiqueta.map(function(x){return x.cantidad}), backgroundColor: "rgba(16,185,129,0.7)" }] }, options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
            }
        }, 200);
    } catch (err) { ct.innerHTML = 'Error: ' + es(err.message); }
}

/* ─── Reset DB ─── */
document.getElementById("btn-reset").addEventListener("click", function() {
    if (!esAdmin()) { st("Solo administradores pueden resetear", "error"); return; }
    document.getElementById("reset-confirm-input").value = "";
    document.getElementById("btn-reset-confirm").disabled = true;
    document.getElementById("btn-reset-confirm").style.opacity = "0.5";
    om("modal-reset");
    document.getElementById("reset-confirm-input").focus();
});

document.getElementById("reset-confirm-input").addEventListener("input", function() {
    var btn = document.getElementById("btn-reset-confirm");
    if (this.value === "RESET") { btn.disabled = false; btn.style.opacity = "1"; }
    else { btn.disabled = true; btn.style.opacity = "0.5"; }
});

document.getElementById("btn-reset-confirm").addEventListener("click", async function() {
    var btn = this; btn.disabled = true; btn.textContent = "Reseteando...";
    try {
        var r = await af(A + "/db/reset", { method: "POST", body: JSON.stringify({ confirmacion: "RESET" }) });
        st(r.mensaje, "success"); cm("modal-reset");
        document.getElementById("empty-state").classList.remove("hidden");
        document.getElementById("persona-ficha").classList.add("hidden");
        document.getElementById("empresa-ficha").classList.add("hidden");
    } catch (err) { st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "Resetear Todo";
    document.getElementById("reset-confirm-input").value = "";
    btn.style.opacity = "0.5";
});

/* ─── Enriquecer Empresa desde SUNAT ─── */
async function enriquecerEmpresa(ruc) {
    if (!confirm("Consultar SUNAT para completar datos de " + ruc + "?")) return;
    try {
        var r = await af(A + "/empresas/" + ruc + "/enriquecer", { method: "POST" });
        st(r.mensaje, "success");
        cfEmpresa(ruc);
    } catch (err) { st(err.message, "error"); }
}
window.enriquecerEmpresa = enriquecerEmpresa;

var _pollTimer = null;

async function enriquecerTodasEmpresas() {
    cm("modal-visorempresas");
    om("modal-progreso");
    document.getElementById("progreso-barra").style.width = "0%";
    document.getElementById("progreso-texto").textContent = "0 / 0";
    document.getElementById("progreso-ruc").textContent = "";
    document.getElementById("progreso-errores").innerHTML = "";
    document.getElementById("progreso-mensaje").textContent = "Iniciando...";
    document.getElementById("btn-cancelar-enriquecer").style.display = "inline-flex";

    try {
        var r = await af(A + "/empresas/enriquecer-todas", { method: "POST" });
        var total = r.total_empresas || 0;
        document.getElementById("progreso-texto").textContent = "0 / " + total;

        // Polling cada 1.5 segundos
        _pollTimer = setInterval(pollProgreso, 1500);
        pollProgreso();  // inmediato
    } catch (err) {
        st(err.message, "error");
        cm("modal-progreso");
    }
}

async function pollProgreso() {
    try {
        var p = await af(A + "/empresas/enriquecer-progreso");
        document.getElementById("progreso-barra").style.width = p.porcentaje + "%";
        document.getElementById("progreso-texto").textContent = p.actualizadas + " / " + p.total;
        document.getElementById("progreso-mensaje").textContent = p.mensaje || "Procesando...";
        if (p.ruc_actual) document.getElementById("progreso-ruc").textContent = "RUC: " + p.ruc_actual;
        if (p.errores && p.errores.length > 0) {
            var html = p.errores.slice(-5).map(function(e) {
                return "<div>⚠ " + e.ruc + ": " + e.error + "</div>";
            }).join("");
            document.getElementById("progreso-errores").innerHTML = html;
        }

        if (!p.activo) {
            clearInterval(_pollTimer);
            document.getElementById("btn-cancelar-enriquecer").style.display = "none";
            document.getElementById("progreso-barra").style.background = p.porcentaje === 100 ? "var(--color-success)" : "var(--color-primary)";
            setTimeout(function() { cm("modal-progreso"); st(p.mensaje, "success"); }, 2000);
        }
    } catch (err) {
        // Si hay error al obtener progreso, dejar de poll
        clearInterval(_pollTimer);
    }
}

async function cancelarEnriquecimiento() {
    if (!confirm("Cancelar el enriquecimiento en curso?")) return;
    clearInterval(_pollTimer);
    cm("modal-progreso");
    st("Enriquecimiento cancelado", "info");
}
window.cancelarEnriquecimiento = cancelarEnriquecimiento;

/* ─── Consulta DNI (RENIEC) ─── */
async function consultarDni() {
    var dni = document.getElementById("p-dni").value.trim();
    if (!dni || dni.length !== 8) { st("Ingrese un DNI de 8 dígitos", "error"); return; }
    var btn = document.querySelector("[onclick='consultarDni()']");
    btn.disabled = true; btn.textContent = "🔍...";
    try {
        var d = await af(A + "/consultar/dni?dni=" + encodeURIComponent(dni));
        document.getElementById("p-nombres").value = d.nombres || "";
        document.getElementById("p-ap-paterno").value = d.apellido_paterno || "";
        document.getElementById("p-ap-materno").value = d.apellido_materno || "";
        st("Datos cargados desde RENIEC", "success");
    } catch (err) { st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "🔍 DNI";
}

/* ─── Consulta RUC (SUNAT) ─── */
async function consultarRuc() {
    var ruc = document.getElementById("e-ruc").value.trim();
    if (!ruc || ruc.length !== 11) { st("Ingrese un RUC de 11 dígitos", "error"); return; }
    var btn = document.querySelector("[onclick='consultarRuc()']");
    btn.disabled = true; btn.textContent = "🔍...";
    try {
        var d = await af(A + "/consultar/ruc?ruc=" + encodeURIComponent(ruc));
        document.getElementById("e-nombre").value = d.nombre_o_razon_social || d.nombre || "";
        if (d.direccion) document.getElementById("e-direccion").value = d.direccion;

        // Mostrar representante legal en banner si existe
        var banner = document.getElementById("rep-legal-banner");
        if (!banner) {
            banner = document.createElement("div");
            banner.id = "rep-legal-banner";
            banner.style.cssText = "margin-top:12px;padding:12px;border-radius:8px;font-size:0.9rem;";
            var formEmpresa = document.getElementById("form-empresa");
            formEmpresa.parentNode.insertBefore(banner, formEmpresa.nextSibling);
        }

        if (d.representante_legal && d.representante_legal.dni) {
            var rep = d.representante_legal;
            banner.style.display = "block";
            banner.style.background = "var(--color-success-light)";
            banner.style.border = "1px solid #bbf7d0";
            banner.innerHTML = "<strong>👤 Rep. Legal:</strong> " + es(rep.nombre) +
                " (DNI: " + es(rep.dni) + ")<br>" +
                '<button class="btn btn-primary btn-xs" style="margin-top:8px;" onclick="crearVinculoDesdeConsulta(\x27' + ruc + '\x27, \x27' + rep.dni + '\x27)">🔗 Vincular ' + es(rep.nombre.split(" ").slice(-2).join(" ")) + "</button>";
        } else {
            banner.style.display = "none";
        }

        var estadoMsg = d.estado ? " | " + d.estado : "";
        st("✅ Datos cargados desde SUNAT" + estadoMsg, "success");
    } catch (err) { st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "🔍 RUC";
}

/* ─── Crear vinculo desde consulta RUC ─── */
window.crearVinculoDesdeConsulta = async function(ruc, dniRep) {
    if (!confirm("Crear persona con DNI " + dniRep + " y vincularla a " + ruc + " como representante legal?")) return;
    try {
        // 1. Consultar datos del DNI via apiperu.dev
        var personaData;
        try {
            personaData = await af(A + "/consultar/dni?dni=" + encodeURIComponent(dniRep));
        } catch (e) {
            personaData = { nombres: "", apellido_paterno: "", apellido_materno: "" };
        }

        // 2. Crear la persona
        var newPersona = await af(A + "/personas", {
            method: "POST",
            body: JSON.stringify({
                dni: dniRep,
                nombres: personaData.nombres || "PENDIENTE",
                apellido_paterno: personaData.apellido_paterno || "PENDIENTE",
                apellido_materno: personaData.apellido_materno || null,
            })
        });
        st("Persona creada: " + newPersona.nombre_completo, "success");

        // 3. Vincularla a la empresa como representante legal
        await af(A + "/persona-empresa", {
            method: "POST",
            body: JSON.stringify({
                persona_dni: dniRep,
                empresa_ruc: ruc,
                cargo: "representante legal",
            })
        });
        st("✅ Vinculado como representante legal", "success");
        cm("modal-empresa");
        cf(dniRep);
    } catch (err) { st(err.message, "error"); }
}

/* ─── Verificador de Consistencia ─── */
var _verificarData = null;
document.getElementById("btn-verificador").addEventListener("click", abrirVerificador);
async function abrirVerificador() {
    om("modal-verificador");
    var ct = document.getElementById("verificador-content");
    ct.innerHTML = '<span class="spinner"></span> Analizando base de datos...';
    try {
        var r = await af(A + "/verificar");
        _verificarData = r;
        var h = '<div style="margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">';
        h += '<span style="background:#2563eb;color:white;padding:4px 12px;border-radius:20px;font-size:0.9rem;">' + r.total_personas + ' personas</span>';
        h += '<span style="background:' + (r.total_observaciones > 0 ? "#dc2626" : "#16a34a") + ';color:white;padding:4px 12px;border-radius:20px;font-size:0.9rem;">' + r.total_observaciones + ' observaciones</span>';
        if (r.observaciones.length > 0) {
            h += '<button class="btn btn-primary btn-sm" onclick="corregirTodas()" style="margin-left:auto;">⚡ Corregir todo</button>';
        }
        h += '</div>';
        if (r.observaciones.length === 0) {
            h += '<div style="text-align:center;padding:40px;color:var(--color-success);"><div style="font-size:3rem;margin-bottom:12px;">✅</div><div style="font-weight:600;">Base de datos consistente</div><div style="color:var(--color-text-secondary);font-size:0.9rem;">No se encontraron observaciones.</div></div>';
        } else {
            r.observaciones.forEach(function(o) {
                var color = o.gravedad === "alta" ? "#dc2626" : o.gravedad === "media" ? "#d97706" : "#64748b";
                var icon = o.gravedad === "alta" ? "🔴" : o.gravedad === "media" ? "🟡" : "ℹ️";
                h += '<div id="obs-' + o.id + '" style="padding:12px 16px;margin-bottom:8px;border-radius:8px;border-left:4px solid ' + color + ';background:#f8fafc;">';
                h += '<div style="display:flex;justify-content:space-between;align-items:start;">';
                h += '<div><strong>' + icon + ' ' + es(o.mensaje) + '</strong></div>';
                h += '<div style="display:flex;gap:6px;flex-shrink:0;margin-left:8px;">';
                if (o.dni) h += '<button class="btn btn-outline btn-xs" onclick="cf(\'' + o.dni + '\')">👤</button>';
                if (o.ruc) h += '<button class="btn btn-outline btn-xs" onclick="cfEmpresa(\'' + o.ruc + '\')">🏢</button>';
                if (o.dni_origen) h += '<button class="btn btn-outline btn-xs" onclick="cf(\'' + o.dni_origen + '\')">👤1</button>';
                if (o.dni_destino) h += '<button class="btn btn-outline btn-xs" onclick="cf(\'' + o.dni_destino + '\')">👤2</button>';
                h += '<button class="btn btn-primary btn-xs" onclick="corregirObservacion(' + o.id + ',\'' + o.tipo + '\',\'' + (o.ruc || "") + '\',\'' + (o.dni || "") + '\',' + (o.relacion_id || "null") + ',' + (o.origen_id || "null") + ',' + (o.destino_id || "null") + ',\'' + (o.tipo_relacion || "") + '\')" style="margin-left:4px;">🔧 Corregir</button>';
                h += '</div></div></div>';
            });
        }
        h += '<div style="margin-top:16px;text-align:center;"><button class="btn btn-outline" onclick="abrirVerificador()">🔄 Re-verificar</button></div>';
        ct.innerHTML = h;
    } catch (err) {
        ct.innerHTML = '<div class="no-results">Error: ' + es(err.message) + '</div>';
    }
}

async function corregirObservacion(id, tipo, ruc, dni, relacionId, origenId, destinoId, tipoRelacion) {
    if (!confirm("Corregir esta observacion?")) return;
    var body = { tipo: tipo, ruc: ruc || null, dni: dni || null };
    if (relacionId !== null) body.relacion_id = relacionId;
    if (origenId !== null) body.origen_id = origenId;
    if (destinoId !== null) body.destino_id = destinoId;
    if (tipoRelacion) body.tipo_relacion = tipoRelacion;
    try {
        var resp = await af(A + "/verificar/corregir", { method: "POST", body: JSON.stringify(body) });
        if (resp.corregido) {
            st(resp.mensaje, "success");
            var el = document.getElementById("obs-" + id);
            if (el) el.style.opacity = "0.4";
        } else {
            st(resp.mensaje, "error");
        }
    } catch (err) {
        st(err.message, "error");
    }
}

async function corregirTodas() {
    if (!_verificarData || !_verificarData.observaciones || _verificarData.observaciones.length === 0) return;
    if (!confirm("Corregir las " + _verificarData.observaciones.length + " observaciones automaticamente?")) return;
    var total = _verificarData.observaciones.length;
    var corregidas = 0;
    var errores = 0;
    for (var i = 0; i < total; i++) {
        var o = _verificarData.observaciones[i];
        var el = document.getElementById("obs-" + o.id);
        if (el) el.style.opacity = "0.5";
        try {
            var body = { tipo: o.tipo, ruc: o.ruc || null, dni: o.dni || null };
            if (o.relacion_id !== undefined && o.relacion_id !== null) body.relacion_id = o.relacion_id;
            if (o.origen_id !== undefined && o.origen_id !== null) body.origen_id = o.origen_id;
            if (o.destino_id !== undefined && o.destino_id !== null) body.destino_id = o.destino_id;
            if (o.tipo_relacion) body.tipo_relacion = o.tipo_relacion;
            var resp = await af(A + "/verificar/corregir", { method: "POST", body: JSON.stringify(body) });
            if (resp.corregido) {
                corregidas++;
                if (el) el.style.opacity = "0.3";
                st("[" + (i+1) + "/" + total + "] " + resp.mensaje, "success");
            } else {
                errores++;
                if (el) el.style.opacity = "0.6";
                st("[" + (i+1) + "/" + total + "] " + resp.mensaje, "error");
            }
        } catch (err) {
            errores++;
            st("[" + (i+1) + "/" + total + "] Error: " + err.message, "error");
        }
    }
    st("✅ Correccion masiva: " + corregidas + " corregidas, " + errores + " errores de " + total, corregidas > 0 ? "success" : "error");
}

window.abrirVerificador = abrirVerificador;
window.corregirObservacion = corregirObservacion;
window.corregirTodas = corregirTodas;
