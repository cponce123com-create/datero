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
        var p = await af(A + "/stats").catch(function(){ return null; });
        var personasRes = await fetch(A + "/personas?q=a&limite=1").catch(function(){ return null; });
        if (!personasRes) {
            document.getElementById("network-graph").innerHTML = '<p style="text-align:center;padding:40px;color:var(--color-text-secondary);">Agrega personas y relaciones para ver el grafo</p>';
            return;
        }
        var [personas, relaciones] = await Promise.all([
            af(A + "/db/todas").catch(function(){ return []; }),
            fetch(A + "/relaciones/" + (document.getElementById("search-input") ? "0" : "0")).catch(function(){ return []; })
        ]);
        // Si no tenemos relaciones, mostrar placeholder
        if (!personas || !personas.length) {
            document.getElementById("network-graph").innerHTML = '<p style="text-align:center;padding:40px;color:var(--color-text-secondary);">Aun no hay datos para el grafo</p>';
            return;
        }
        var limited = personas.slice(0, 50);
        var nodes = limited.map(function(p){ return {
            id: p.id, label: (p.nombres + " " + (p.apellido_paterno || "")).trim(),
            shape: "dot", size: 20,
            color: "#2563eb",
            font: { color: "var(--color-text)" }
        }; });
        var edges = [];
        if (typeof relaciones === "object" && relaciones.length) {
            var ids = limited.map(function(p){ return p.id; });
            edges = relaciones.filter(function(r){ return ids.indexOf(r.persona_origen_id) >= 0 && ids.indexOf(r.persona_destino_id) >= 0; })
                .map(function(r){ return {
                    from: r.persona_origen_id, to: r.persona_destino_id,
                    label: r.tipo_relacion || "relacion",
                    arrows: "to", color: { color: "var(--color-border)" }
                }; });
        }
        var container = document.getElementById("network-graph");
        if (typeof vis !== "undefined") {
            var data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
            var options = {
                physics: { stabilization: true, barnesHut: { gravitationalConstant: -2000 } },
                interaction: { hover: true, dragNodes: true },
                edges: { smooth: true, font: { size: 10 } }
            };
            if (networkInstance) networkInstance.destroy();
            networkInstance = new vis.Network(container, data, options);
        }
    } catch(err) { console.warn("Graph error:", err); }
}

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
