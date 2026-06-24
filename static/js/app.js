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

/* ─── Stats (Home) ─── */
async function cargarStats() {
    try {
        var [p, e, r, t] = await Promise.all([
            af(A + "/stats").catch(function(){ return {total_personas:0,total_empresas:0,total_relaciones:0,total_etiquetas:0}; }),
            af(A + "/stats").catch(function(){ return {total_personas:0,total_empresas:0,total_relaciones:0,total_etiquetas:0}; }),
        ]);
        var stats = p;
        ["Personas","Empresas","Relaciones","Etiquetas"].forEach(function(k){
            var el = document.getElementById("total" + k);
            if (el) el.textContent = stats["total_" + k.toLowerCase()] || 0;
        });
    } catch(err) { /* stats no available, show — */ }
}

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
        cargarStats();
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
