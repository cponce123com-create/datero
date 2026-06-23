/**
 * state.js — Estado global de la aplicación.
 * 
 * Implementa un observer simple para notificar cambios de estado.
 */
var AppState = {
    _listeners: [],
    _state: {
        editandoDni: null,
        editandoEmpresaRuc: null,
        searchTimer: null,
        empresaSearchTimer: null,
        toastTimer: null,
    },

    get: function(key) {
        return this._state[key];
    },

    set: function(key, value) {
        this._state[key] = value;
        this._notify(key, value);
    },

    on: function(callback) {
        this._listeners.push(callback);
    },

    _notify: function(key, value) {
        this._listeners.forEach(function(cb) { cb(key, value); });
    }
};
