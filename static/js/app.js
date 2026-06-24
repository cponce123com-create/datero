/**
 * app.js — Punto de entrada de la aplicación RedCorruptela.
 *
 * Inicializa la app: verifica sesión, configura eventos globales,
 * y maneja el login via API JSON (en lugar del form redirect).
 *
 * Dependencias:
 *   - state.js (AppState)
 *   - api.js (A, getAuth, setAuth, logout, af, esAdmin, _redirectLogin)
 *   - ui.js (st, om, cm, sl, hl, ds, cf, cv, etc.)
 */

/* ─── Login via API JSON (evita redirect) ─── */

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
        st(err.message, "error");
    }
}

/* ─── Interceptar submit del form de login ─── */

document.addEventListener("DOMContentLoaded", function() {
    var form = document.getElementById("form-login");
    if (form) {
        form.addEventListener("submit", function(e) {
            e.preventDefault();
            var u = document.getElementById("login-user").value.trim();
            var p = document.getElementById("login-pass").value;
            if (!u || !p) { st("Ingrese usuario y contrasena", "error"); return; }
            loginAPI(u, p);
        });
    }
});

/* ─── Init ─── */

async function _init() {
    try {
        await af(A + "/health");
        console.log("✅ RedCorruptela API v0.3 - sesion activa");
    } catch (err) {
        console.warn("⚠ API no disponible:", err.message);
        st("No se pudo conectar con el servidor", "error");
    }
}

/* ─── Start ─── */

var savedToken = getAuth();
if (savedToken) {
    hl();
    _init();
} else {
    // Token en URL? (desde redirect del login-form)
    var q = new URLSearchParams(window.location.search);
    var t = q.get("token");
    if (t) {
        setAuth(t, q.get("user"), q.get("rol"));
        window.history.replaceState({}, "", "/");
        hl();
        _init();
    }
    // else: mostrar login overlay (por defecto visible)
}
