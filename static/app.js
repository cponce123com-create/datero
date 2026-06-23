/**
 * app.js — Frontend de RedCorruptela
 * SPA con login overlay, search, fichas, BD visor y CSV import.
 */
(function () {
"use strict";

var A = "/api";

/* Auth */
function ga() { return sessionStorage.getItem("rc_auth"); }
function sa(u, p) { sessionStorage.setItem("rc_auth", btoa(u + ":" + p)); }
function sl() { var e = document.getElementById("login-overlay"); if (e) e.classList.remove("hidden"); }
function hl() { var e = document.getElementById("login-overlay"); if (e) e.classList.add("hidden"); }

async function af(url, o) {
    o = o || {};
    var a = ga();
    if (!a) { sl(); throw new Error("Sin sesion"); }
    var h = { Authorization: "Basic " + a, "Content-Type": "application/json" };
    if (o.headers) Object.assign(h, o.headers);
    var r = await fetch(url, { method: o.method, headers: h, body: o.body });
    if (r.status === 401) { sessionStorage.removeItem("rc_auth"); sl(); throw new Error("Credenciales invalidas"); }
    if (!r.ok) { var d = await r.json().catch(function() { return {}; }); throw new Error(d.detail || "Error " + r.status); }
    if (r.status === 204) return null;
    return r.json();
}

/* Login */
document.getElementById("form-login").addEventListener("submit", function(e) {
    e.preventDefault();
    var u = document.getElementById("login-user").value.trim();
    var p = document.getElementById("login-pass").value.trim();
    if (!u || !p) return;
    sa(u, p); hl(); _init();
});

/* Toast */
var tt = null;
function st(msg, type) {
    type = type || "info";
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.className = "toast toast-" + type;
    t.classList.remove("hidden");
    if (tt) clearTimeout(tt);
    tt = setTimeout(function() { t.classList.add("hidden"); }, 4000);
}

/* Modals */
function om(id) { document.getElementById(id).classList.remove("hidden"); }
function cm(id) { document.getElementById(id).classList.add("hidden"); }
document.addEventListener("click", function(e) {
    if (e.target.dataset.close) cm(e.target.dataset.close);
    if (e.target.classList.contains("modal-overlay")) { var m = e.target.closest(".modal"); if (m) m.classList.add("hidden"); }
});
document.addEventListener("keydown", function(e) { if (e.key === "Escape") document.querySelectorAll(".modal:not(.hidden)").forEach(function(m) { m.classList.add("hidden"); }); });

/* Escape */
function es(s) { if (!s) return ""; var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

/* Search */
var si = document.getElementById("search-input");
var sb = document.getElementById("search-btn");
var sr = document.getElementById("search-results");
sb.addEventListener("click", ds);
si.addEventListener("keydown", function(e) { if (e.key === "Enter") ds(); });

async function ds() {
    var q = si.value.trim(); if (!q) return;
    try {
        var d = await af(A + "/personas?q=" + encodeURIComponent(q));
        if (d.total === 0) { sr.innerHTML = '<div class="no-results">Sin resultados</div>'; sr.classList.remove("hidden"); return; }
        if (d.total === 1) { sr.classList.add("hidden"); cf(d.resultados[0].dni); return; }
        sr.innerHTML = d.resultados.map(function(p) { return '<div class="search-result-item" data-dni="' + p.dni + '"><span><strong>' + es(p.nombre_completo) + '</strong></span><span class="search-result-dni">DNI: ' + es(p.dni) + '</span></div>'; }).join("");
        sr.querySelectorAll(".search-result-item").forEach(function(it) { it.addEventListener("click", function() { sr.classList.add("hidden"); si.value = ""; cf(it.dataset.dni); }); });
        sr.classList.remove("hidden");
    } catch (err) { st(err.message, "error"); }
}

/* Ficha */
async function cf(dni) {
    var fd = document.getElementById("persona-ficha");
    var es_ = document.getElementById("empty-state");
    fd.innerHTML = '<div class="loading-text"><span class="spinner"></span> Cargando...</div>';
    fd.classList.remove("hidden"); es_.classList.add("hidden");
    try { var d = await af(A + "/personas/" + dni); rf(d); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (err) { fd.innerHTML = '<div class="no-results">Error: ' + es(err.message) + '</div>'; }
}

function rf(d) {
    var p = d.persona, fd = document.getElementById("persona-ficha");
    var fn = p.fecha_nacimiento ? new Date(p.fecha_nacimiento + "T00:00:00").toLocaleDateString("es-PE") : "\u2014";
    var h = "";
    h += '<div class="ficha-header"><div><div class="ficha-nombre">' + es(p.nombre_completo) + '</div><div class="ficha-dni">DNI: ' + es(p.dni) + '</div><div class="ficha-meta"><span>📅 Nacimiento: ' + fn + '</span>';
    if (p.foto_url) h += '<span>🖼 <a href="' + es(p.foto_url) + '" target="_blank">Ver foto</a></span>';
    h += '</div></div><div class="ficha-actions"><button class="btn btn-outline btn-sm" onclick="cargarArbol(\x27' + es(p.dni) + '\x27)">🌳 Árbol</button> <button class="btn btn-outline btn-sm" onclick="abrirEtiqueta(\x27' + es(p.dni) + '\x27)">🏷 Etiquetar</button> <button class="btn btn-outline btn-sm" onclick="editarPersona(\x27' + es(p.dni) + '\x27)">✏️ Editar</button> <button class="btn btn-ghost btn-sm btn-delete-persona" data-dni="' + es(p.dni) + '">🗑 Eliminar</button></div></div><div class="ficha-body">';
    if (p.notas) h += '<div class="ficha-notas">📝 ' + es(p.notas) + '</div>';
    h += '<div class="section"><div class="section-title">👥 Familiares Directos <span class="section-badge">' + d.relaciones_directas.length + '</span></div>';
    if (d.relaciones_directas.length === 0) { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin relaciones.</p>'; }
    else { h += '<div class="relaciones-list">'; d.relaciones_directas.forEach(function(r) { h += '<div class="relacion-card"><div class="relacion-info"><div class="relacion-tipo">' + es(r.tipo_relacion) + '</div><div class="relacion-nombre" data-dni="' + es(r.persona_relacionada.dni) + '">' + es(r.persona_relacionada.nombre_completo) + '</div><div class="relacion-certeza">' + es(r.certeza) + (r.notas ? " — " + es(r.notas) : "") + '</div></div><button class="relacion-delete" data-id="' + r.id + '" title="Eliminar">✕</button></div>'; }); h += '</div>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🧠 Parentescos Inferidos <span class="section-badge">' + d.parentescos_inferidos.length + '</span></div>';
    if (d.parentescos_inferidos.length === 0) { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">No se encontraron parentescos inferidos.</p>'; }
    else { h += '<div class="parentesco-list">'; d.parentescos_inferidos.forEach(function(inf) { h += '<div class="parentesco-card"><div class="parentesco-header"><span class="parentesco-badge">inferido</span><span class="parentesco-tipo">' + es(inf.tipo_parentesco) + ':</span><span class="parentesco-nombre" data-dni="' + es(inf.persona.dni) + '">' + es(inf.persona.nombre_completo) + '</span></div><div class="parentesco-camino">' + es(inf.camino) + '</div></div>'; }); h += '</div>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🏢 Lugares de Trabajo <span class="section-badge">' + (d.trabajos ? d.trabajos.length : 0) + '</span></div>';
    if (d.trabajos && d.trabajos.length > 0) {
        h += '<div style="display:flex;flex-wrap:wrap;gap:8px;">';
        d.trabajos.forEach(function(t) { h += '<div class="tag-item"><span class="tag-nombre">' + es(t.empresa_nombre) + '</span></div>'; });
        h += '</div>';
    } else { h += '<p style="color:var(--color-text-secondary);font-size:0.9rem;">Sin trabajos registrados.</p>'; }
    h += '</div>';
    h += '<div class="section"><div class="section-title">🏷 Etiquetas <span class="section-badge">' + d.etiquetas.length + '</span></div><div class="tags-list">';
    d.etiquetas.forEach(function(et) { h += '<div class="tag-item"><span class="tag-nombre">' + es(et.etiqueta.nombre) + '</span>'; if (et.observacion) h += '<span class="tag-obs" title="' + es(et.observacion) + '">' + es(et.observacion) + '</span>'; h += '<button class="tag-remove" data-etiqueta="' + es(et.etiqueta.nombre) + '" title="Quitar">✕</button></div>'; });
    h += '<button class="tag-add-btn" data-dni="' + es(p.dni) + '">+ Agregar etiqueta</button></div></div>';
    h += '<div id="arbol-container-' + p.dni + '" class="tree-section hidden"><div class="section-title">🌳 Árbol Genealógico</div><div class="tree-container" id="tree-content-' + p.dni + '"></div></div>';
    h += '</div>';
    fd.innerHTML = h;
    fd.querySelectorAll(".relacion-nombre, .parentesco-nombre").forEach(function(el) { el.addEventListener("click", function() { cf(el.dataset.dni); }); });
    fd.querySelectorAll(".relacion-delete").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); if (!confirm("Eliminar relacion?")) return; try { await af(A + "/relaciones/" + btn.dataset.id, { method: "DELETE" }); st("Relacion eliminada", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } }); });
    fd.querySelectorAll(".tag-remove").forEach(function(btn) { btn.addEventListener("click", async function(e) { e.stopPropagation(); try { await af(A + "/personas/" + p.dni + "/etiquetas/" + encodeURIComponent(btn.dataset.etiqueta), { method: "DELETE" }); st("Etiqueta removida", "success"); cf(p.dni); } catch (err) { st(err.message, "error"); } }); });
    var ta_ = fd.querySelector(".tag-add-btn"); if (ta_) ta_.addEventListener("click", function() { abrirEtiqueta(p.dni); });
    var db_ = fd.querySelector(".btn-delete-persona"); if (db_) db_.addEventListener("click", async function() { if (!confirm("Eliminar a " + p.nombre_completo + "?")) return; try { await af(A + "/personas/" + p.dni, { method: "DELETE" }); st("Persona eliminada", "success"); fd.classList.add("hidden"); document.getElementById("empty-state").classList.remove("hidden"); } catch (err) { st(err.message, "error"); } });
}

/* Tree */
window.cargarArbol = async function(dni) {
    var c = document.getElementById("arbol-container-" + dni), ct_ = document.getElementById("tree-content-" + dni);
    if (!c.classList.contains("hidden")) { c.classList.add("hidden"); return; }
    c.classList.remove("hidden"); ct_.innerHTML = '<span class="spinner"></span> Cargando...';
    try {
        var d = await af(A + "/personas/" + dni + "/arbol?profundidad=3");
        var t = "👤 " + d.raiz.nombre_completo + " (DNI: " + d.raiz.dni + ")\n";
        if (d.ascendentes.length > 0) { t += "\n▲ ASCENDENTES:\n"; d.ascendentes.forEach(function(n) { t += fan(n, "", true); }); }
        if (d.descendentes.length > 0) { t += "\n▼ DESCENDENTES:\n"; d.descendentes.forEach(function(n) { t += fan(n, "", false); }); }
        ct_.textContent = t;
    } catch (err) { ct_.textContent = "Error: " + err.message; }
};

function fan(no, px, ia) {
    var r = no.tipo_relacion ? "[" + no.tipo_relacion + "] " : "";
    var l = px + (px ? "├─ " : "") + r + no.persona.nombre_completo + "\n";
    if (no.hijos && no.hijos.length > 0) { no.hijos.forEach(function(ch, i) { var il = i === no.hijos.length - 1; var np = px + (il ? "   " : "│  "); l += fan(ch, np, ia); }); }
    return l;
}

/* Etiqueta */
function abrirEtiqueta(dni) { document.getElementById("e-dni").value = dni; document.getElementById("e-nombre").value = ""; document.getElementById("e-obs").value = ""; om("modal-etiqueta"); }
window.abrirEtiqueta = abrirEtiqueta;

window.editarPersona = function(dni) {
    document.getElementById("modal-persona-title").textContent = "Editar Persona";
    var btn = document.querySelector("#form-persona button[type=submit]");
    btn.textContent = "Guardar Cambios";
    document.getElementById("p-dni").disabled = true;
    window.editandoDni = null;
    af(A + "/personas/" + dni).then(function(d) {
        var p = d.persona;
        window.editandoDni = dni;
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

/* Forms */
document.getElementById("form-persona").addEventListener("submit", async function(e) { e.preventDefault(); var b = { nombres: document.getElementById("p-nombres").value.trim(), apellido_paterno: document.getElementById("p-ap-paterno").value.trim(), apellido_materno: document.getElementById("p-ap-materno").value.trim() || null, fecha_nacimiento: document.getElementById("p-fecha-nac").value || null, foto_url: document.getElementById("p-foto").value.trim() || null, notas: document.getElementById("p-notas").value.trim() || null }; if (editandoDni) { b.dni = document.getElementById("p-dni").value.trim(); try { await af(A + "/personas/" + editandoDni, { method: "PUT", body: JSON.stringify(b) }); st("Persona actualizada", "success"); cm("modal-persona"); document.getElementById("form-persona").reset(); editandoDni = null; document.getElementById("modal-persona-title").textContent = "Nueva Persona"; document.querySelector("#form-persona button[type=submit]").textContent = "Guardar Persona"; document.getElementById("p-dni").disabled = false; cf(b.dni); } catch (err) { st(err.message, "error"); } } else { b.dni = document.getElementById("p-dni").value.trim(); try { await af(A + "/personas", { method: "POST", body: JSON.stringify(b) }); st("Persona creada", "success"); cm("modal-persona"); document.getElementById("form-persona").reset(); cf(b.dni); } catch (err) { st(err.message, "error"); } } });
document.getElementById("form-relacion").addEventListener("submit", async function(e) { e.preventDefault(); var b = { persona_origen_dni: document.getElementById("r-origen").value.trim(), persona_destino_dni: document.getElementById("r-destino").value.trim(), tipo_relacion: document.getElementById("r-tipo").value, certeza: document.getElementById("r-certeza").value, notas: document.getElementById("r-notas").value.trim() || null }; try { var r_ = await af(A + "/relaciones", { method: "POST", body: JSON.stringify(b) }); st(r_.mensaje || "Relacion creada", "success"); cm("modal-relacion"); document.getElementById("form-relacion").reset(); var fd = document.getElementById("persona-ficha"); if (!fd.classList.contains("hidden")) { var dn = fd.querySelector(".ficha-dni"); if (dn) cf(dn.textContent.replace("DNI: ", "")); } } catch (err) { st(err.message, "error"); } });
document.getElementById("form-etiqueta").addEventListener("submit", async function(e) { e.preventDefault(); var dni = document.getElementById("e-dni").value; var b = { etiqueta_nombre: document.getElementById("e-nombre").value.trim(), observacion: document.getElementById("e-obs").value.trim() || null }; try { await af(A + "/personas/" + dni + "/etiquetas", { method: "POST", body: JSON.stringify(b) }); st("Etiqueta asignada", "success"); cm("modal-etiqueta"); document.getElementById("form-etiqueta").reset(); cf(dni); } catch (err) { st(err.message, "error"); } });

/* Header */
document.getElementById("btn-nueva-persona").addEventListener("click", function() { document.getElementById("form-persona").reset(); editandoDni = null; document.getElementById("p-dni").disabled = false; document.getElementById("modal-persona-title").textContent = "Nueva Persona"; document.querySelector("#form-persona button[type=submit]").textContent = "Guardar Persona"; om("modal-persona"); });
document.getElementById("btn-nueva-relacion").addEventListener("click", function() { document.getElementById("form-relacion").reset(); om("modal-relacion"); });
document.getElementById("btn-etiquetas").addEventListener("click", async function() { om("modal-lista-etiquetas"); var ct = document.getElementById("lista-etiquetas-content"); ct.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando...</p>'; try { var ets = await af(A + "/etiquetas"); if (ets.length === 0) { ct.innerHTML = '<p class="no-results">No hay etiquetas.</p>'; return; } ct.innerHTML = ets.map(function(et) { return '<div class="etiqueta-list-item" data-nombre="' + es(et.nombre) + '"><span>🏷 <strong>' + es(et.nombre) + '</strong></span><span style="color:var(--color-text-secondary);font-size:0.82rem;">Click →</span></div>'; }).join(""); ct.querySelectorAll(".etiqueta-list-item").forEach(function(it) { it.addEventListener("click", async function() { var n = it.dataset.nombre; try { var pl = await af(A + "/etiquetas/" + encodeURIComponent(n) + "/personas"); if (pl.length === 0) { st('Ninguna persona con "' + n + '"', "info"); return; } cm("modal-lista-etiquetas"); if (pl.length === 1) { cf(pl[0].dni); return; } sr.innerHTML = pl.map(function(p) { return '<div class="search-result-item" data-dni="' + p.dni + '"><span><strong>' + es(p.nombre_completo) + '</strong></span><span class="search-result-dni">DNI: ' + es(p.dni) + '</span></div>'; }).join(""); sr.querySelectorAll(".search-result-item").forEach(function(el) { el.addEventListener("click", function() { sr.classList.add("hidden"); cf(el.dataset.dni); }); }); sr.classList.remove("hidden"); } catch (err) { st(err.message, "error"); } }); }); } catch (err) { ct.innerHTML = '<p class="no-results">Error: ' + es(err.message) + '</p>'; } });

/* DB Visor */
document.getElementById("btn-visorbd").addEventListener("click", function() { cv(); });

function cv() {
    om("modal-visorbd");
    var ct = document.getElementById("visorbd-content");
    ct.innerHTML = '<p class="loading-text"><span class="spinner"></span> Cargando BD...</p>';
    af(A + "/db/todas").then(function(ps) {
        if (ps.length === 0) { ct.innerHTML = '<p class="no-results">BD vacía.</p>'; return; }
        var h = '<p style="margin-bottom:12px;color:var(--color-text-secondary);">' + ps.length + ' personas</p><div style="overflow-x:auto;"><table class="db-table"><thead><tr><th>DNI</th><th>Nombre</th><th>Nacimiento</th><th>Notas</th><th></th><th></th></tr></thead><tbody>';
        ps.forEach(function(p) {
            var fn = p.fecha_nacimiento ? new Date(p.fecha_nacimiento + "T00:00:00").toLocaleDateString("es-PE") : "—";
            h += '<tr><td>' + es(p.dni) + '</td><td><strong>' + es(p.nombre_completo) + '</strong></td><td>' + fn + '</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (p.notas ? es(p.notas) : "—") + '</td>';
            h += '<td><button class="btn btn-primary btn-xs btn-ver-bd" data-dni="' + es(p.dni) + '">Ver</button></td>';
            h += '<td><button class="btn btn-danger btn-xs btn-del-bd" data-dni="' + es(p.dni) + '" title="Eliminar">🗑</button></td></tr>';
        });
        h += '</tbody></table></div>';
        ct.innerHTML = h;
        ct.querySelectorAll(".btn-ver-bd").forEach(function(btn) { btn.addEventListener("click", function() { cm("modal-visorbd"); cf(btn.dataset.dni); }); });
        ct.querySelectorAll(".btn-del-bd").forEach(function(btn) { btn.addEventListener("click", async function() { if (!confirm("Eliminar a " + btn.dataset.dni + "?")) return; try { await af(A + "/personas/" + btn.dataset.dni, { method: "DELETE" }); st("Persona eliminada", "success"); cv(); } catch (err) { st(err.message, "error"); } }); });
    }).catch(function(err) { ct.innerHTML = '<p class="no-results">Error: ' + es(err.message) + '</p>'; });
}

/* CSV Import */
document.getElementById("btn-importar").addEventListener("click", function() { document.getElementById("form-importar").reset(); om("modal-importar"); });
document.getElementById("form-importar").addEventListener("submit", async function(e) {
    e.preventDefault();
    var raw = document.getElementById("csv-textarea").value.trim();
    if (!raw) return;
    var lines = raw.split("\n");
    var ps = [];
    for (var i = 0; i < lines.length; i++) { var ln = lines[i].trim(); if (!ln) continue; var p = ln.split(","); if (p.length < 3) continue; ps.push({ dni: (p[0]||"").trim(), nombres: (p[1]||"").trim(), apellido_paterno: (p[2]||"").trim(), apellido_materno: (p[3]||"").trim()||null, fecha_nacimiento: null, foto_url: null, notas: null }); }
    if (ps.length === 0) { st("No hay datos CSV validos", "error"); return; }
    var ob = document.querySelector("#form-importar button[type=submit]");
    ob.disabled = true; ob.textContent = "Importando...";
    try {
        var r = await af(A + "/db/importar", { method: "POST", body: JSON.stringify(ps) });
        var m = r.mensaje + "\nCreados: " + r.creados;
        if (r.errores && r.errores.length > 0) m += "\nErrores: " + r.errores.length;
        st(m, r.errores && r.errores.length > 0 ? "error" : "success");
        cm("modal-importar"); document.getElementById("csv-textarea").value = "";
    } catch (err) { st(err.message, "error"); }
    ob.disabled = false; ob.textContent = "Importar";
});

/* Smart Import (LEDER DATA) */
document.getElementById("btn-importar-inteligente").addEventListener("click", function() {
    document.getElementById("form-importar-inteligente").reset();
    document.getElementById("si-resultado").classList.add("hidden");
    om("modal-importar-inteligente");
});

document.getElementById("form-importar-inteligente").addEventListener("submit", async function(e) {
    e.preventDefault();
    var raw = document.getElementById("si-textarea").value.trim();
    if (!raw) return;
    var btn = document.querySelector("#form-importar-inteligente button[type=submit]");
    btn.disabled = true; btn.textContent = "Procesando...";
    try {
        var r = await af(A + "/db/importar-inteligente", { method: "POST", body: JSON.stringify({ texto: raw }) });
        var div = document.getElementById("si-resultado");
        div.classList.remove("hidden");
        var msgClass = r.errores && r.errores.length > 0 ? "error" : "success";
        div.style.background = msgClass === "error" ? "var(--color-danger-light)" : "var(--color-success-light)";
        div.style.borderColor = msgClass === "error" ? "#fca5a5" : "#bbf7d0";
        div.innerHTML = "<strong>" + r.mensaje + "</strong>";
        if (r.errores && r.errores.length > 0) {
            div.innerHTML += "<br><small style=\"color:var(--color-danger);\">Errores: " + r.errores.slice(0,3).join(", ") + "</small>";
        }
        div.innerHTML += "<br><button class=\"btn btn-outline btn-xs\" style=\"margin-top:8px;\" onclick=\"cm('modal-importar-inteligente'); cf('" + r.persona_dni + "')\">Ver ficha de " + r.persona_dni + "</button>";
    } catch (err) { st(err.message, "error"); }
    btn.disabled = false; btn.textContent = "Importar Inteligentemente";
});

/* Init */
async function _init() {
    try { await af(A + "/health"); console.log("✅ RedCorruptela API"); }
    catch (err) { console.warn("⚠", err.message); sl(); }
}

/* Start */
if (ga()) { hl(); _init(); } else { sl(); }
})();
