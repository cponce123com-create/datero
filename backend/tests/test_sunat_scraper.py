"""
tests/test_sunat_scraper.py — Tests unitarios para SunatScraper.

Ejecutar:
    cd backend && python -m pytest tests/test_sunat_scraper.py -v
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock

# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_html():
    """HTML simulado de respuesta de SUNAT."""
    return """
    <html>
    <body>
    <table>
        <tr><th>RUC</th><td>20123456789</td></tr>
        <tr><th>Razón Social</th><td>MINERIA PERU S.A.C.</td></tr>
        <tr><th>Nombre Comercial</th><td>MINERIA PERU</td></tr>
        <tr><th>Tipo de Contribuyente</th><td>SOCIEDAD ANONIMA CERRADA</td></tr>
        <tr><th>Estado</th><td>ACTIVO</td></tr>
        <tr><th>Condición</th><td>HABIDO</td></tr>
        <tr><th>Dirección</th><td>AV. PRINCIPAL 123</td><td>LIMA</td><td>LIMA</td><td>MIRAFLORES</td></tr>
        <tr><th>Fecha de Inscripción</th><td>15/03/2010</td></tr>
        <tr><th>Inicio de Actividades</th><td>01/04/2010</td></tr>
        <tr><th>Sistema de Contabilidad</th><td>MANUAL</td></tr>
        <tr><th>Actividad de Comercio Exterior</th><td>SIN ACTIVIDAD</td></tr>
        <tr><th>Actividad Económica</th><td>MINERIA</td></tr>
        <tr><th>Comprobantes Autorizados</th><td>FACTURA, BOLETA</td></tr>
        <tr><th>Sistema de Emisión</th><td>MANUAL</td></tr>
        <tr><th>Afiliado PLE</th><td>NO</td></tr>
    </table>
    </body>
    </html>
    """


@pytest.fixture
def scraper():
    """Instancia de SunatScraper."""
    from consultas.sunat_scraper import SunatScraper
    return SunatScraper()


# ─── Tests de parseo ───────────────────────────────────────────────────────

class TestParseoHTML:
    """Pruebas de parseo del HTML de SUNAT."""

    def test_parsear_html_valido(self, scraper, sample_html):
        """Debe extraer todos los campos correctamente."""
        data = scraper._parsear_html(sample_html, "20123456789")

        assert data["numero"] == "20123456789"
        assert data["nombre_o_razon_social"] == "MINERIA PERU S.A.C."
        assert data["nombre_comercial"] == "MINERIA PERU"
        assert data["tipo_contribuyente"] == "SOCIEDAD ANONIMA CERRADA"
        assert data["estado"] == "ACTIVO"
        assert data["condicion"] == "HABIDO"
        assert "AV. PRINCIPAL 123" in data["direccion"]
        assert data["departamento"] == "LIMA"
        assert data["provincia"] == "LIMA"
        assert data["distrito"] == "MIRAFLORES"
        assert data["fecha_inscripcion"] == "15/03/2010"
        assert data["fecha_inicio_actividades"] == "01/04/2010"
        assert data["sistema_contabilidad"] == "MANUAL"
        assert data["actividad_comercio_exterior"] == "SIN ACTIVIDAD"
        assert data["actividad_economica"] == "MINERIA"
        assert data["comprobantes_autorizados"] == "FACTURA, BOLETA"
        assert data["sistema_emision"] == "MANUAL"
        assert data["afiliado_ple"] == "NO"

    def test_parsear_html_minimo(self, scraper):
        """Debe manejar HTML con datos mínimos (solo razón social)."""
        html = """
        <html><body>
        <h3>EMPRESA DE PRUEBA S.A.</h3>
        <table>
            <tr><th>RUC</th><td>20123456789</td></tr>
            <tr><th>Estado</th><td>ACTIVO</td></tr>
        </table>
        </body></html>
        """
        data = scraper._parsear_html(html, "20123456789")
        assert data["nombre_o_razon_social"] == "EMPRESA DE PRUEBA S.A."
        assert data["estado"] == "ACTIVO"

    def test_parsear_html_vacio(self, scraper):
        """Debe manejar HTML sin datos."""
        html = "<html><body>No se encontraron resultados</body></html>"
        data = scraper._parsear_html(html, "20123456789")
        assert data["numero"] == "20123456789"
        assert data["nombre_o_razon_social"] == ""

    def test_parsear_html_con_acentos(self, scraper):
        """Debe manejar correctamente caracteres con acentos."""
        html = """
        <html><body>
        <table>
            <tr><th>Razón Social</th><td>PERÚ MINERÍA S.A.C.</td></tr>
            <tr><th>Dirección</th><td>AV. LOS OLIVOS 456</td></tr>
        </table>
        </body></html>
        """
        data = scraper._parsear_html(html, "20123456789")
        assert data["nombre_o_razon_social"] == "PERÚ MINERÍA S.A.C."


# ─── Tests de validación ───────────────────────────────────────────────────

class TestValidacion:
    """Pruebas de validación de entrada."""

    def test_ruc_invalido_muy_corto(self, scraper):
        """RUC con menos de 11 dígitos debe lanzar error."""
        from consultas.sunat_scraper import SunatScraperError
        with pytest.raises(SunatScraperError, match="11 dígitos"):
            scraper.consultar_ruc("12345678")

    def test_ruc_invalido_con_letras(self, scraper):
        """RUC con letras debe lanzar error."""
        from consultas.sunat_scraper import SunatScraperError
        with pytest.raises(SunatScraperError, match="11 dígitos"):
            scraper.consultar_ruc("ABCDEFGHIJK")

    def test_ruc_vacio(self, scraper):
        """RUC vacío debe lanzar error."""
        from consultas.sunat_scraper import SunatScraperError
        with pytest.raises(SunatScraperError, match="11 dígitos"):
            scraper.consultar_ruc("")


# ─── Tests de CAPTCHA ──────────────────────────────────────────────────────

class TestCaptcha:
    """Pruebas de detección de CAPTCHA."""

    @pytest.mark.parametrize("html", [
        "<html>captcha</html>",
        "<html>g-recaptcha</html>",
        "<html>Cloudflare challenge</html>",
        "<html>Please enable JavaScript</html>",
        "<html>Access denied</html>",
    ])
    def test_detectar_captcha(self, scraper, html):
        """Debe detectar indicadores de CAPTCHA."""
        assert scraper._es_captcha(html) is True

    def test_sin_captcha(self, scraper, sample_html):
        """HTML normal sin CAPTCHA."""
        assert scraper._es_captcha(sample_html) is False


# ─── Tests de caché ────────────────────────────────────────────────────────

class TestCache:
    """Pruebas del sistema de caché."""

    def test_cache_funciona(self):
        """Consultar mismo RUC dos veces debe usar caché."""
        from consultas.sunat_scraper import SunatScraper, _cache, limpiar_cache
        limpiar_cache()

        scraper = SunatScraper()

        # Mockear _consultar para evitar llamada real
        with patch.object(scraper, '_consultar', return_value={"numero": "20123456789", "test": True}) as mock:
            # Primera llamada
            result1 = scraper.consultar_ruc("20123456789")
            assert mock.call_count == 1
            assert result1["test"] is True

            # Segunda llamada (debe usar caché)
            result2 = scraper.consultar_ruc("20123456789")
            assert mock.call_count == 1  # No se llamó de nuevo
            assert result2["test"] is True


# ─── Tests de compatibilidad ───────────────────────────────────────────────

class TestCompatibilidad:
    """Pruebas de compatibilidad con ConsultaPeru."""

    def test_mismo_formato_dict(self):
        """El dict retornado debe tener los mismos campos clave que ConsultaPeru."""
        from consultas.sunat_scraper import SunatScraper, SunatScraperError
        scraper = SunatScraper()

        # Simular respuesta
        with patch.object(scraper, '_consultar') as mock:
            mock.return_value = {
                "numero": "20123456789",
                "nombre_o_razon_social": "TEST S.A.C.",
                "tipo_contribuyente": "SAC",
                "nombre_comercial": "TEST",
                "estado": "ACTIVO",
                "condicion": "HABIDO",
                "direccion": "AV TEST 123",
                "fecha_inscripcion": "01/01/2020",
            }
            data = scraper.consultar_ruc("20123456789")
            # Campos compatibles con ConsultaPeru
            assert "numero" in data
            assert "nombre_o_razon_social" in data
