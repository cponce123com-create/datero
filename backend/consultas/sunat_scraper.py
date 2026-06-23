"""
sunat_scraper.py — Scraper de SUNAT para consulta gratuita de RUC.

Reemplaza la dependencia de apiperu.dev consultando directamente
el portal público de SUNAT (e-consultaruc).

Flujo:
  1. GET https://e-consultaruc.sunat.gob.pe/ → obtiene cookie y numRnd
  2. POST con numRnd + RUC → obtiene HTML con datos
  3. BeautifulSoup parsea la tabla de resultados

Requerimientos: requests, beautifulsoup4, lxml, cachetools

Documentación técnica: ver docs/SUNAT_SCRAPER.md
"""

import os
import re
import logging
import time
from typing import Optional, Any
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache

# ─── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger("sunat_scraper")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─── Constantes ────────────────────────────────────────────────────────────
BASE_URL = "https://e-consultaruc.sunat.gob.pe"
CONSULTA_URL = BASE_URL + "/cl-ti-itmrconsruc/jcrS00Alias"
TIMEOUT = 30
MAX_RETRIES = 3
CACHE_TTL = timedelta(hours=24)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─── Caché ─────────────────────────────────────────────────────────────────
_cache = TTLCache(maxsize=256, ttl=CACHE_TTL.total_seconds())

# ─── Excepción ─────────────────────────────────────────────────────────────
class SunatScraperError(Exception):
    """Error controlado del scraper SUNAT. No rompe la aplicación."""
    pass


class CaptchaDetectedError(SunatScraperError):
    """SUNAT devolvió un CAPTCHA o bloqueó la consulta."""
    pass


# ─── Scraper ───────────────────────────────────────────────────────────────
class SunatScraper:
    """
    Scraper oficial de SUNAT para consulta de RUC.

    Uso:
        scraper = SunatScraper()
        data = scraper.consultar_ruc("20123456789")

    Retorna dict con mismos campos que ConsultaPeru.consultar_ruc().
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        })

    # ── Método público ─────────────────────────────────────────────────

    def consultar_ruc(self, ruc: str) -> dict:
        """
        Consulta datos de una empresa por RUC.

        Args:
            ruc: RUC de 11 dígitos.

        Returns:
            Dict con datos normalizados (mismo formato que ConsultaPeru).

        Raises:
            SunatScraperError: Error controlado.
            CaptchaDetectedError: SUNAT bloqueó la consulta.
        """
        ruc = ruc.strip()
        if not ruc.isdigit() or len(ruc) != 11:
            raise SunatScraperError("RUC debe tener 11 dígitos numéricos")

        # Verificar caché
        cache_key = f"ruc_{ruc}"
        if cache_key in _cache:
            logger.info(f"Cache hit para RUC {ruc}")
            return _cache[cache_key]

        # Intentar con reintentos
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Consultando RUC {ruc} (intento {attempt}/{MAX_RETRIES})")
                data = self._consultar(ruc)
                _cache[cache_key] = data
                logger.info(f"RUC {ruc} consultado exitosamente")
                return data
            except (CaptchaDetectedError, SunatScraperError) as e:
                last_error = e
                if isinstance(e, CaptchaDetectedError):
                    logger.warning(f"CAPTCHA detectado para RUC {ruc}")
                    break  # No reintentar si hay CAPTCHA
                logger.warning(f"Error en intento {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.info(f"Esperando {wait}s antes de reintentar...")
                    time.sleep(wait)

        raise last_error or SunatScraperError("No se pudo consultar el RUC")

    # ── Flujo interno ─────────────────────────────────────────────────

    def _consultar(self, ruc: str) -> dict:
        """Ejecuta el flujo completo de consulta.

        Basado en el patrón de la macro VBA de Excel que scrapa SUNAT:
        GET con accion=consPorRuc&actReturn=1&modo=1&nroRuc={ruc}
        """
        # Obtener sesión inicial (cookies F5/Cloudflare)
        try:
            self._session.get(BASE_URL + "/", timeout=TIMEOUT)
        except requests.exceptions.RequestException:
            pass  # La página inicial puede fallar, las cookies persisten

        # Consultar RUC via GET (patrón VBA)
        try:
            resp = self._session.get(
                CONSULTA_URL,
                params={
                    "accion": "consPorRuc",
                    "actReturn": "1",
                    "modo": "1",
                    "nroRuc": ruc,
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise SunatScraperError(f"Error al consultar RUC {ruc}: {e}")

        html = resp.text
        size = len(html)

        if self._es_captcha(html):
            raise CaptchaDetectedError("SUNAT requiere CAPTCHA")

        if size < 500:
            raise SunatScraperError(
                f"Respuesta vacía de SUNAT ({size} bytes)"
            )

        # Verificar que el HTML contenga datos (no solo el formulario vacío)
        # El formulario vacío tiene ~22835 bytes
        # Los datos reales agregan ~5000+ bytes con tablas
        if "No se encontraron resultados" in html:
            raise SunatScraperError(f"No se encontraron datos para el RUC {ruc}")

        logger.info(f"RUC {ruc}: {size} bytes recibidos de SUNAT")
        return self._parsear_html(html, ruc)

    def _parsear_html(self, html: str, ruc: str) -> dict:
        """
        Paso 3: Parsea el HTML de la tabla de resultados.

        Extrae campos del formato típico de SUNAT.
        """
        soup = BeautifulSoup(html, "lxml")

        data = {
            "numero": ruc,
            "nombre_o_razon_social": "",
            "tipo_contribuyente": "",
            "nombre_comercial": "",
            "estado": "",
            "condicion": "",
            "direccion": "",
            "departamento": "",
            "provincia": "",
            "distrito": "",
            "fecha_inscripcion": "",
            "fecha_inicio_actividades": "",
            "sistema_contabilidad": "",
            "actividad_comercio_exterior": "",
            "actividad_economica": "",
            "comprobantes_autorizados": "",
            "sistema_emision": "",
            "afiliado_ple": "",
            "representante_legal": None,  # {nombre, dni, cargo} o None
        }

        # Buscar todas las tablas en la página
        tablas = soup.find_all("table")

        for tabla in tablas:
            filas = tabla.find_all("tr")
            for fila in filas:
                celdas = fila.find_all(["td", "th"])
                texto_celdas = [
                    celda.get_text(strip=True) for celda in celdas
                ]

                if len(texto_celdas) < 2:
                    continue

                label = texto_celdas[0].lower()
                valor = texto_celdas[1] if len(texto_celdas) > 1 else ""

                # Mapeo de campos SUNAT → nuestro formato
                if "razón social" in label or "razon social" in label:
                    data["nombre_o_razon_social"] = valor
                elif "nombre comercial" in label:
                    data["nombre_comercial"] = valor
                elif "tipo de contribuyente" in label:
                    data["tipo_contribuyente"] = valor
                elif "estado" in label and "contribuyente" not in label:
                    data["estado"] = valor
                elif "condición" in label or "condicion" in label:
                    data["condicion"] = valor
                elif "dirección" in label or "direccion" in label:
                    data["direccion"] = valor
                    if len(texto_celdas) >= 5:
                        data["departamento"] = texto_celdas[2]
                        data["provincia"] = texto_celdas[3]
                        data["distrito"] = texto_celdas[4]
                elif "inscripción" in label or "inscripcion" in label:
                    data["fecha_inscripcion"] = valor
                elif "inicio de actividades" in label:
                    data["fecha_inicio_actividades"] = valor
                elif "sistema de contabilidad" in label:
                    data["sistema_contabilidad"] = valor
                elif "comercio exterior" in label:
                    data["actividad_comercio_exterior"] = valor
                elif "actividad" in label and "económica" in label:
                    data["actividad_economica"] = valor
                elif "comprobante" in label:
                    data["comprobantes_autorizados"] = valor
                elif "sistema de emisión" in label or "sistema de emision" in label:
                    data["sistema_emision"] = valor
                elif "ple" in label:
                    data["afiliado_ple"] = valor

        # Si no se encontró razón social, buscar en <strong> o <h3>
        if not data["nombre_o_razon_social"]:
            for tag in soup.find_all(["strong", "h3", "h4"]):
                texto = tag.get_text(strip=True)
                if texto and len(texto) > 5 and not texto.startswith("http"):
                    data["nombre_o_razon_social"] = texto
                    break

        # ── Extraer Representante Legal ────────────────────────────────
        # El bloque de representantes legales suele estar precedido por
        # un encabezado <h3> o <strong> con "Representante Legal"
        for encabezado in soup.find_all(["h3", "h4", "strong"]):
            if "representante" in encabezado.get_text(strip=True).lower():
                # Buscar la tabla siguiente a este encabezado
                tabla_rep = encabezado.find_next("table")
                if tabla_rep:
                    filas_rep = tabla_rep.find_all("tr")
                    for fila_rep in filas_rep:
                        celdas_rep = fila_rep.find_all(["td", "th"])
                        textos = [c.get_text(strip=True) for c in celdas_rep]

                        # Formato típico: Tipo | Apellidos/Nombres | DNI | Cargo | Desde
                        if len(textos) >= 3:
                            # Buscar DNI en las celdas
                            dni_rep = ""
                            nombre_rep = ""
                            cargo_rep = "representante legal"
                            for t in textos:
                                t_clean = t.replace("-", "").strip()
                                if t_clean.isdigit() and len(t_clean) == 8:
                                    dni_rep = t_clean
                                elif not t_clean.isdigit() and len(t_clean) > 5:
                                    nombre_rep = t

                            # Si hay nombre y DNI, guardar
                            if dni_rep and nombre_rep:
                                # Extraer cargo de textos restantes
                                for t in textos:
                                    t_low = t.lower()
                                    if "representante" in t_low or "gerente" in t_low or "apoderado" in t_low or "director" in t_low or "socio" in t_low:
                                        cargo_rep = t

                                data["representante_legal"] = {
                                    "nombre": nombre_rep,
                                    "dni": dni_rep,
                                    "cargo": cargo_rep,
                                }
                                break  # Solo el primer representante legal

        # Si no se encontró en tabla, buscar en texto plano
        # Patrón: DNI seguido de nombre en el texto
        if not data["representante_legal"]:
            import re as re_mod
            body_text = soup.get_text()
            # Buscar patrón: 8 dígitos seguido de nombres
            patron_rep = re_mod.search(
                r'''(?:representante|gerente|apoderado|director)\s*
                    (?:legal|general)?\s*[:\-]?\s*
                    (?:[\w\s]+\s+)?      # nombre
                    (\d{8})\s*[\-]?\s*   # DNI
                    ([\w\sÁÉÍÓÚáéíóúñÑ,]+)  # nombre/apellidos
                ''',
                body_text, re_mod.IGNORECASE | re_mod.VERBOSE
            )
            if patron_rep:
                data["representante_legal"] = {
                    "nombre": patron_rep.group(2).strip(),
                    "dni": patron_rep.group(1),
                    "cargo": "representante legal",
                }

        return data

    def _es_captcha(self, html: str) -> bool:
        """
        Detecta si SUNAT BLOQUEÓ la consulta con CAPTCHA.

        SUNAT carga reCAPTCHA v3 en todas las páginas (no es bloqueo).
        Solo se considera CAPTCHA cuando hay un mensaje explícito de
        bloqueo o challenge.
        """
        html_lower = html.lower()
        indicadores_bloqueo = [
            "cf-challenge",
            "cloudflare",
            "Access denied",
            "captcha de seguridad",
            "resolver captcha",
            "complete el captcha",
        ]
        # Solo detectar si hay indicadores de BLOQUEO real
        # (no solo carga de script reCAPTCHA)
        return any(ind in html_lower for ind in indicadores_bloqueo)


# ─── Función helper para compatibilidad ────────────────────────────────────
def consultar_ruc(ruc: str) -> dict:
    """
    Función de compatibilidad con ConsultaPeru.

    Uso:
        from consultas.sunat_scraper import consultar_ruc
        data = consultar_ruc("20123456789")
    """
    scraper = SunatScraper()
    return scraper.consultar_ruc(ruc)


# ─── Limpiar caché ─────────────────────────────────────────────────────────
def limpiar_cache():
    """Limpia la caché de consultas."""
    _cache.clear()
    logger.info("Caché de SUNAT limpiada")
