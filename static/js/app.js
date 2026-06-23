/**
 * app.js — Punto de entrada de la aplicación.
 * 
 * Carga los módulos (state.js, api.js, ui.js) e inicializa la app.
 * Dependencias: Chart.js (cargado desde CDN en index.html)
 */

/* ─── Init ─── */
async function _init() {
    try { await af(A + "/health"); console.log("✅ RedCorruptela API v0.3"); }
    catch (err) { console.warn("⚠", err.message); }
}

function sl() { var e = document.getElementById("login-overlay"); if (e) e.classList.remove("hidden"); }
function hl() { var e = document.getElementById("login-overlay"); if (e) e.classList.add("hidden"); }

/* ─── Query params (redirect desde login-form) ─── */
(function() {
    var p = new URLSearchParams(window.location.search);
    var token = p.get("token");
    var user = p.get("user");
    var rol = p.get("rol");
    if (token) {
        setAuth(token, user, rol);
        window.history.replaceState({}, "", "/");  // limpia URL
        hl();
        _init();
        return;
    }
    var error = p.get("error");
    if (error) {
        st("Usuario o contraseña incorrectos", "error");
        window.history.replaceState({}, "", "/");
    }
})();

/* ─── Start ─── */
if (getAuth()) { hl(); _init(); } else { sl(); }
