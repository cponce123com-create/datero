/**
 * app.js — Punto de entrada de la aplicación RedCorruptela.
 */

/* ─── Funciones que ui.js espera ─── */
function hl() {
    var e = document.getElementById("login-overlay");
    if (e) e.classList.add("hidden");
    var w = document.getElementById("app-wrapper");
    if (w) w.style.display = "flex";
    try {
        var u = sessionStorage.getItem("rc_user") || "Admin";
        var r = sessionStorage.getItem("rc_rol") || "admin";
        var av = document.getElementById("sidebar-user-avatar");
        if (av) av.textContent = u.charAt(0).toUpperCase();
        var un = document.getElementById("sidebar-user-name");
        if (un) un.textContent = u;
        var ur = document.getElementById("sidebar-user-rol");
        if (ur) ur.textContent = r;
    } catch(e) {}
}

/* ─── Dark Mode ─── */
function toggleDarkMode() {
    var h = document.documentElement;
    var cur = h.getAttribute("data-theme") || "light";
    var next = cur === "dark" ? "light" : "dark";
    h.setAttribute("data-theme", next);
    localStorage.setItem("rc_theme", next);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = next === "dark" ? "☀️" : "🌙";
}
// Cargar preferencia guardada
(function() {
    var saved = localStorage.getItem("rc_theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = saved === "dark" ? "☀️" : "🌙";
})();

/* ─── Stats (obsoleto, usar cargarKPIs) ─── */
async function cargarStats() {}

/* ─── Login via API JSON ─── */

async function loginAPI(username, password) {
    try {
        var r = await fetch(A + "/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: username, password: password })
        });
        if (!r.ok) {
            var e = await r.json().catch(function(){ return {detail: "Error del servidor"}; });
            throw new Error(e.detail || "Credenciales invalidas");
        }
        var d = await r.json();
        setAuth(d.access_token, d.username, d.rol);
        hl();
        st("Bienvenido, " + d.username, "success");
        _init();
    } catch (err) {
        console.error("[Login]", err);
        st(err.message, "error");
    }
}

/* ─── Grafo de Red (Vis.js) ─── */
var networkInstance = null;

async function drawGraph() {
    try {
        var personas;
        try {
            personas = await af(A + "/db/todas");
        } catch(e) { personas = []; }
        var container = document.getElementById("network-graph");
        if (!personas || !personas.length) {
            if (container) container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:0.9rem;"><i class="fas fa-database" style="margin-right:8px;"></i>Sin datos aun. Importa o registra personas para ver el grafo.</div>';
            return;
        }
        // Show simple count message - graph will show familia relationships per person
        var total = personas.length;
        if (container) container.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text);gap:8px;"><div style="font-size:2.5rem;font-weight:800;color:var(--primary);">' + total + '</div><div style="color:var(--muted);font-size:0.9rem;">personas registradas</div><div style="color:var(--muted);font-size:0.78rem;margin-top:4px;">Usa la barra de busqueda o ve a Personas/Empresas para explorar</div></div>';
    } catch(err) { console.warn("Graph error:", err); }
}

/* ─── Family Chart (integrador) ─── */
var fcInstance = null;

function convertToFamilyChart(persona, relaciones) {
    // Convierte datos de la API al formato family-chart Datum[]
    var nodes = {};
    var data = [];

    // Persona principal
    if (!nodes[persona.dni]) {
        nodes[persona.dni] = {
            id: persona.dni,
            data: { gender: (persona.genero || "DESCONOCIDO") === "MASCULINO" ? "M" : "F" },
            rels: { parents: [], spouses: [], children: [] },
            info: persona.nombres + " " + (persona.apellido_paterno || "")
        };
    }

    // Procesar relaciones
    for (var i = 0; i < relaciones.length; i++) {
        var r = relaciones[i];
        var p = r.persona_relacionada || {};
        if (!p.dni) continue;

        if (!nodes[p.dni]) {
            nodes[p.dni] = {
                id: p.dni,
                data: { gender: (p.genero || "DESCONOCIDO") === "MASCULINO" ? "M" : "F" },
                rels: { parents: [], spouses: [], children: [] },
                info: p.nombres + " " + (p.apellido_paterno || "")
            };
        }

        var tipo = r.tipo_relacion || "";
        if (tipo === "padre" || tipo === "madre") {
            nodes[persona.dni].rels.parents.push(p.dni);
            nodes[p.dni].rels.children.push(persona.dni);
        } else if (tipo === "conyuge") {
            nodes[persona.dni].rels.spouses.push(p.dni);
            nodes[p.dni].rels.spouses.push(persona.dni);
        } else if (tipo === "hijo" || tipo === "hija") {
            nodes[persona.dni].rels.children.push(p.dni);
            nodes[p.dni].rels.parents.push(persona.dni);
        }
    }

    for (var k in nodes) data.push(nodes[k]);
    return data;
}

async function showFamilyTree(dni) {
    if (!dni) {
        dni = prompt("Ingrese DNI de la persona para ver su arbol familiar:");
        if (!dni || dni.length !== 8) { st("DNI invalido", "error"); return; }
    }
    try {
        var persona = await af(A + "/personas/" + dni);
        var relaciones = persona.relaciones || [];
        var data = convertToFamilyChart(persona.persona, relaciones);

        if (data.length < 2) {
            st("Esta persona no tiene familiares registrados", "info");
            return;
        }

        // Mostrar modal con el arbol
        var modal = document.getElementById("modal-family-chart");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "modal-family-chart";
            modal.className = "modal-overlay";
            modal.innerHTML = '<div class="modal" style="width:90%;max-width:1000px;height:80vh;"><div class="modal-header"><h3>🌳 Arbol familiar</h3><button class="btn btn-ghost" onclick="this.closest(\'.modal-overlay\').classList.add(\'hidden\')">✕</button></div><div id="family-chart-container" style="width:100%;height:calc(100% - 50px);"></div></div>';
            document.body.appendChild(modal);
            modal.addEventListener("click", function(e) {
                if (e.target === modal) modal.classList.add("hidden");
            });
        }
        modal.classList.remove("hidden");

        var container = document.getElementById("family-chart-container");
        container.innerHTML = "";

        if (fcInstance) fcInstance.destroy();
        fcInstance = family_chart.default.createChart(container, data, {
            template: "pattern1",
            width: "100%",
            height: "100%"
        });
        fcInstance.render();

        st("Arbol cargado: " + data.length + " personas", "success");
    } catch(err) {
        console.error("Family chart error:", err);
        st("Error al cargar arbol: " + err.message, "error");
    }
}

// Exponer globalmente
window.showFamilyTree = showFamilyTree;

/* ─── Busqueda Predictiva ─── */
var _searchTimer = null;
document.addEventListener("DOMContentLoaded", function(){
    var si = document.getElementById("globalSearchInput");
    var sb = document.getElementById("suggestions-box");
    if (!si) return;
    si.addEventListener("input", function(){
        clearTimeout(_searchTimer);
        var q = this.value.trim();
        if (q.length < 2) { var sb = document.getElementById("searchSuggestions"); if (sb) sb.style.display = "none"; return; }
        _searchTimer = setTimeout(async function(){
            try {
                var r = await af(A + "/search?q=" + encodeURIComponent(q));
                var sb = document.getElementById("searchSuggestions");
                if (!sb) return;
                if (!r || !r.length) { sb.style.display = "none"; return; }
                sb.innerHTML = r.map(function(item){
                    return '<div class="suggestion-item" data-id="' + item.id + '" data-type="' + item.tipo + '">' +
                        '<span><strong>' + item.nombres + '</strong> ' + (item.apellido_paterno || "") + ' &middot; ' + (item.dni || "") + '</span>' +
                        '<span class="suggestion-badge">' + (item.tipo || "persona") + '</span></div>';
                }).join("");
                sb.style.display = "block";
                sb.querySelectorAll(".suggestion-item").forEach(function(el){
                    el.addEventListener("click", function(){
                        sb.style.display = "none";
                        si.value = "";
                        var dni = this.querySelector("span").textContent.split("·")[1] ? this.querySelector("span").textContent.split("·")[1].trim() : "";
                        if (dni && dni.length === 8) { cf(dni); }
                    });
                });
            } catch(err) { console.warn("Search error:", err); }
        }, 350);
    });
    document.addEventListener("click", function(e){
        if (!e.target.closest(".search-section")) {
            var sb = document.getElementById("searchSuggestions");
            if (sb) sb.style.display = "none";
        }
    });
});

/* ─── Init ─── */

async function _init() {
    try {
        await af(A + "/health");
        console.log("RedCorruptela API v0.3 - sesion activa");
        cargarKPIs();
        setTimeout(drawGraph, 500);
    } catch (err) {
        console.warn("API no disponible:", err.message);
    }
}

/* ─── Logout (cierra sesion y oculta app) ─── */
function sl() {
    var e = document.getElementById("login-overlay");
    if (e) e.classList.remove("hidden");
    var w = document.getElementById("app-wrapper");
    if (w) w.style.display = "none";
}

/* ─── Start ─── */

var savedToken = getAuth();
if (savedToken) {
    hl();
    _init();
} else {
    var q = new URLSearchParams(window.location.search);
    var t = q.get("token");
    if (t) {
        setAuth(t, q.get("user"), q.get("rol"));
        window.history.replaceState({}, "", "/");
        hl();
        _init();
    }
}

/* ─── New Layout Navigation ─── */
document.addEventListener("DOMContentLoaded", function(){
    // Sidebar toggle
    var st = document.getElementById("sidebar-toggle");
    if (st) st.addEventListener("click", function(){
        document.getElementById("sidebar").classList.toggle("collapsed");
    });

    // Navigation
    document.querySelectorAll(".sidebar-link[data-view]").forEach(function(btn){
        btn.addEventListener("click", function(){
            var view = btn.dataset.view;
            document.querySelectorAll(".sidebar-link[data-view]").forEach(function(b){ b.classList.remove("active"); });
            btn.classList.add("active");
            document.querySelectorAll(".view").forEach(function(v){ v.classList.remove("active"); });
            var target = document.getElementById("view-" + view);
            if (target) target.classList.add("active");
            // Load dynamic content if needed
            if (view === "etiquetas") cargarListaEtiquetas();
            if (view === "dashboard") cargarDashboard();
            // Auto-search on Personas/Empresas
            if (view === "personas") {
                setTimeout(function(){
                    var si = document.getElementById("search-input");
                    if (si) si.focus();
                    // Auto-list all personas
                    listarTodasPersonas();
                }, 300);
            }
            if (view === "empresas") {
                setTimeout(function(){
                    var esi = document.getElementById("search-empresa-input");
                    if (esi) esi.focus();
                    listarTodasEmpresas();
                }, 300);
            }
        });
    });

    // Topbar search focus shortcut
    var ts = document.getElementById("topbar-search-input");
    if (ts) {
        ts.addEventListener("keydown", function(e){
            if (e.key === "Enter" && this.value.trim()) {
                // Switch to personas view and search
                var q = this.value.trim();
                document.querySelector('.sidebar-link[data-view="personas"]').click();
                var si = document.getElementById("search-input");
                if (si) { si.value = q; buscarPersonas(); }
            }
        });
    }
});

/* ─── Auto-list all Personas ─── */
async function listarTodasPersonas() {
    try {
        var sr = document.getElementById("search-results");
        if (!sr) return;
        var d = await af(A + "/db/todas");
        if (!d || !d.length) {
            sr.innerHTML = '<div class="no-results" style="padding:20px;text-align:center;color:var(--muted);">No hay personas registradas. Usa Importar o el boton +Nuevo.</div>';
            sr.classList.remove("hidden");
            return;
        }
        sr.innerHTML = d.map(function(p){
            return '<div class="search-result-item" data-dni="' + p.dni + '"><span><strong>' + es(p.nombre_completo) + '</strong></span><span class="search-result-dni">DNI: ' + es(p.dni) + '</span></div>';
        }).join("");
        sr.querySelectorAll(".search-result-item").forEach(function(it){
            it.addEventListener("click", function(){ sr.classList.add("hidden"); cf(it.dataset.dni); });
        });
        sr.classList.remove("hidden");
    } catch(e) { console.warn("listarPersonas error:", e); }
}

/* ─── Auto-list all Empresas ─── */
async function listarTodasEmpresas() {
    try {
        var esr = document.getElementById("search-empresa-results");
        if (!esr) return;
        var d = await af(A + "/empresas/todas");
        if (!d || !d.length) {
            esr.innerHTML = '<div class="no-results" style="padding:20px;text-align:center;color:var(--muted);">No hay empresas registradas. Usa Importar o el boton +Nuevo.</div>';
            esr.classList.remove("hidden");
            return;
        }
        esr.innerHTML = d.map(function(e){
            return '<div class="search-result-item" data-ruc="' + e.ruc + '"><span><strong>' + es(e.nombre) + '</strong></span><span class="search-result-dni">RUC: ' + es(e.ruc) + '</span></div>';
        }).join("");
        esr.querySelectorAll(".search-result-item").forEach(function(it){
            it.addEventListener("click", function(){ esr.classList.add("hidden"); cfEmpresa(it.dataset.ruc); });
        });
        esr.classList.remove("hidden");
    } catch(e) { console.warn("listarEmpresas error:", e); }
}

/* ─── KPI Loader ─── */
async function cargarKPIs() {
    try {
        var [p, e, et] = await Promise.all([
            af(A + "/db/todas").then(function(d){ return Array.isArray(d) ? d.length : 0; }).catch(function(){ return "—"; }),
            af(A + "/empresas/todas").then(function(d){ return Array.isArray(d) ? d.length : 0; }).catch(function(){ return "—"; }),
            af(A + "/etiquetas").then(function(d){ return Array.isArray(d) ? d.length : 0; }).catch(function(){ return "—"; }),
        ]);
        var el1 = document.getElementById("kpi-personas"); if (el1) el1.textContent = p;
        var el2 = document.getElementById("kpi-empresas"); if (el2) el2.textContent = e;
        var el4 = document.getElementById("kpi-etiquetas"); if (el4) el4.textContent = et;
    } catch(ex) {}
}

/* ─── Re-export functions that ui.js calls ─── */
function abrirModalPersona() { om("modal-persona"); }
function abrirModalImportar() { om("modal-importar"); }
function toggleDarkMode() {
    var html = document.documentElement;
    var t = html.getAttribute("data-theme");
    html.setAttribute("data-theme", t === "dark" ? "light" : "dark");
    localStorage.setItem("rc_theme", t === "dark" ? "light" : "dark");
}
