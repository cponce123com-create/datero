/**
 * app.js — Punto de entrada de la aplicación RedCorruptela.
 */

/* ─── Funciones que ui.js espera ─── */
function sl() { var e = document.getElementById("login-overlay"); if (e) e.classList.remove("hidden"); }
function hl() { var e = document.getElementById("login-overlay"); if (e) e.classList.add("hidden"); }

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
        if (!personas || !personas.length) {
            document.getElementById("network-graph").innerHTML = '<p style="text-align:center;padding:40px;color:var(--color-text-secondary);">Agrega personas para ver el grafo. <button class="btn btn-primary btn-sm" onclick="showFamilyTree()" style="margin-left:8px;">Probar arbol familiar</button></p>';
            return;
        }
        // version friendly: mostrar boton para arbol familiar
        document.getElementById("network-graph").innerHTML = '<p style="text-align:center;padding:20px;color:var(--color-text-secondary);">Selecciona una persona y haz clic en "Arbol familiar" en su ficha.</p>';
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

/* ─── Override hl() and sl() ─── */
var _origHl2 = window.hl;
window.hl = function() {
    if (_origHl2) _origHl2();
    var w = document.getElementById("app-wrapper");
    if (w) w.style.display = "flex";
    // Update sidebar user
    try {
        var u = sessionStorage.getItem("rc_user") || "Admin";
        var r = sessionStorage.getItem("rc_rol") || "admin";
        var av = document.getElementById("sidebar-user-avatar");
        if (av) av.textContent = u.charAt(0).toUpperCase();
        var un = document.getElementById("sidebar-user-name");
        if (un) un.textContent = u;
        var ur = document.getElementById("sidebar-user-rol");
        if (ur) ur.textContent = r;
    } catch(e){}
    // Load stats
    setTimeout(cargarKPIs, 300);
};

var _origSl2 = window.sl;
window.sl = function() {
    if (_origSl2) _origSl2();
    var w = document.getElementById("app-wrapper");
    if (w) w.style.display = "none";
};

/* ─── KPI Loader ─── */
async function cargarKPIs() {
    try {
        var [p, e, et] = await Promise.all([
            af(A + "/personas?q=a&limite=1").then(function(d){ return d.total || 0; }).catch(function(){ return "—"; }),
            af(A + "/db/todas").then(function(d){ return Array.isArray(d) ? d.length : 0; }).catch(function(){ return "—"; }),
            af(A + "/etiquetas").then(function(d){ return Array.isArray(d) ? d.length : 0; }).catch(function(){ return "—"; }),
        ]);
        // Relaciones usa /api/stats silenciosamente
        var r = "—";
        try {
            var token = getAuth();
            if (token) {
                var resp = await fetch("/api/stats", { headers: { Authorization: "Bearer " + token } });
                if (resp.ok) { var d = await resp.json(); r = d.total_relaciones || "—"; }
            }
        } catch(e) {}
        var el1 = document.getElementById("kpi-personas"); if (el1) el1.textContent = p;
        var el2 = document.getElementById("kpi-empresas"); if (el2) el2.textContent = e;
        var el3 = document.getElementById("kpi-relaciones"); if (el3) el3.textContent = r;
        var el4 = document.getElementById("kpi-etiquetas"); if (el4) el4.textContent = et;
    } catch(ex) { console.warn("KPI error:", ex); }
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
