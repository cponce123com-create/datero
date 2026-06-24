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

/* ─── Init ─── */

async function _init() {
    try {
        await af(A + "/health");
        console.log("RedCorruptela API v0.3 - sesion activa");
        cargarStats();
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
