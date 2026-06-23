"""
reniec_sunat.py — Cliente para consulta de DNI (RENIEC) y RUC (SUNAT).

Usa apiperu.dev como proveedor.
Token configurable via variable de entorno CONSULTA_TOKEN.

Uso:
    from consultas.reniec_sunat import ConsultaPeru

    api = ConsultaPeru()
    persona = api.consultar_dni("09603457")
    empresa = api.consultar_ruc("20123456789")
"""

import os
import requests
from typing import Optional, Dict, Any

CONSULTA_TOKEN = os.getenv("CONSULTA_TOKEN", "")

API_BASE = "https://apiperu.dev/api"


class ConsultaPeruError(Exception):
    """Error al consultar la API externa."""
    pass


class ConsultaPeru:
    """
    Cliente para consultar DNI y RUC usando apiperu.dev.

    Los métodos retornan dict con los datos normalizados
    o lanzan ConsultaPeruError si algo falla.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or CONSULTA_TOKEN
        if not self.token:
            raise ConsultaPeruError(
                "CONSULTA_TOKEN no configurado. "
                "Regístrate en https://apiperu.dev y agrega el token a .env"
            )

    def _request(self, endpoint: str, numero: str) -> Dict[str, Any]:
        """Ejecuta la consulta HTTP contra apiperu.dev."""
        url = f"{API_BASE}/{endpoint}/{numero}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise ConsultaPeruError(f"Error de conexión: {e}")

    def consultar_dni(self, dni: str) -> Dict[str, Any]:
        """
        Consulta datos de una persona por DNI.

        Retorna:
            numero: DNI
            nombre_completo: Nombres y apellidos completos
            nombres: Nombres
            apellido_paterno: Apellido paterno
            apellido_materno: Apellido materno
            codigo_verificacion: Dígito verificador
        """
        dni = dni.strip()
        if not dni.isdigit() or len(dni) != 8:
            raise ConsultaPeruError("DNI debe tener 8 dígitos numéricos")

        data = self._request("dni", dni)

        if not data.get("success"):
            msg = data.get("message", "DNI no encontrado")
            raise ConsultaPeruError(msg)

        return data["data"]

    def consultar_ruc(self, ruc: str) -> Dict[str, Any]:
        """
        Consulta datos de una empresa por RUC.

        Retorna:
            numero: RUC
            nombre_o_razon_social: Razón social
            tipo_contribuyente: Tipo de contribuyente
            nombre_comercial: Nombre comercial
            estado: Estado del contribuyente (ACTIVO, etc.)
            direccion: Dirección fiscal
            departamento, provincia, distrito: Ubigeo
        """
        ruc = ruc.strip()
        if not ruc.isdigit() or len(ruc) != 11:
            raise ConsultaPeruError("RUC debe tener 11 dígitos numéricos")

        data = self._request("ruc", ruc)

        if not data.get("success"):
            msg = data.get("message", "RUC no encontrado")
            raise ConsultaPeruError(msg)

        return data["data"]
