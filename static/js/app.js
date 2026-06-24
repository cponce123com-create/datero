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

/* ─── Start ─── */
if (getAuth()) { hl(); _init(); } else { sl(); }
