/**
 * api.js — Capa de comunicación con la API REST.
 * 
 * Maneja autenticación JWT, fetch wrapper con interceptores,
 * detección de 401 (token expirado) y redirección al login.
 */
var A = "/api";

/* ─── Auth JWT ─── */
function getAuth() { return sessionStorage.getItem("rc_token"); }
function setAuth(token, username, rol) {
    sessionStorage.setItem("rc_token", token);
    if (username) sessionStorage.setItem("rc_user", username);
    if (rol) sessionStorage.setItem("rc_rol", rol);
}
function logout() { sessionStorage.clear(); location.reload(); }
function esAdmin() { return sessionStorage.getItem("rc_rol") === "admin"; }

/* ─── Interceptor de sesión expirada ─── */
function _redirectLogin() {
    sessionStorage.clear();
    var e = document.getElementById("login-overlay");
    if (e) e.classList.remove("hidden");
    st("Sesión expirada. Ingrese nuevamente.", "error");
}

/* ─── Fetch wrapper con Bearer token ─── */
async function af(url, o) {
    o = o || {};
    var token = getAuth();
    if (!token) {
        _redirectLogin();
        throw new Error("Sin sesion");
    }
    var h = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
    if (o.headers) Object.assign(h, o.headers);
    var r = await fetch(url, { method: o.method, headers: h, body: o.body });
    if (r.status === 401) {
        _redirectLogin();
        throw new Error("Sesion expirada");
    }
    if (!r.ok) {
        var d = await r.json().catch(function() { return {}; });
        throw new Error(d.detail || "Error " + r.status);
    }
    if (r.status === 204) return null;
    return r.json();
}
