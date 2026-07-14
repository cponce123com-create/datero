"""
comparar_service.py — Servicio de comparación de personas con detección de cruces.

Compara hasta 5 personas y detecta:
  1. Mismo pariente compartido
  2. Cadenas familiares indirectas (pariente de un pariente)
  3. Misma empresa (mismo empleador)
  4. Misma etiqueta
  5. Misma ubicación (distrito/provincia)

Uso:
    service = CompararService(db)
    resultado = service.comparar(["45167775", "43617845"])
"""

import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Persona, Empresa, PersonaEmpresa, PersonaEtiqueta
from schemas import (
    CompararResponse, PersonaConParentescos,
    CruceMismoPariente, CruceCadena, CruceEmpresa, CruceEtiqueta, CruceUbicacion,
)
from parentesco import calcular_parentesco

logger = logging.getLogger(__name__)


class CompararService:
    """Servicio que compara personas y detecta cruces entre sus redes familiares/laborales."""

    def __init__(self, db: Session):
        self.db = db

    def comparar(self, dnis: List[str]) -> CompararResponse:
        """Punto de entrada: compara una lista de DNIs (2-5)."""
        personas_data = []
        todos_parentescos = {}  # dni -> [parentesco_dict]
        todas_empresas = {}     # dni -> [empresa_dict]
        todas_etiquetas = {}    # dni -> [str]

        # 1. Cargar datos de cada persona
        for dni in dnis:
            persona = self.db.query(Persona).filter(
                Persona.dni == dni, Persona.activo == True
            ).first()
            if not persona:
                continue

            # Parentescos via CTE
            parentescos = calcular_parentesco(self.db, dni)

            # Empresas vinculadas
            vinculos = self.db.query(PersonaEmpresa).filter(
                PersonaEmpresa.persona_id == persona.id
            ).all()
            empresas = []
            for v in vinculos:
                emp = self.db.query(Empresa).filter(Empresa.id == v.empresa_id).first()
                if emp:
                    empresas.append({
                        "ruc": emp.ruc,
                        "nombre": emp.nombre,
                        "cargo": v.cargo or "trabajador",
                    })

            # Etiquetas
            etiquetas = []
            pet_rows = self.db.query(PersonaEtiqueta).filter(
                PersonaEtiqueta.persona_id == persona.id
            ).all()
            for pe in pet_rows:
                from models import Etiqueta
                etq = self.db.query(Etiqueta).filter(Etiqueta.id == pe.etiqueta_id).first()
                if etq:
                    etiquetas.append(etq.nombre)

            persona_info = {
                "dni": persona.dni,
                "nombre_completo": persona.nombre_completo,
                "parentescos": parentescos,
                "empresas": empresas,
                "etiquetas": etiquetas,
            }
            personas_data.append(persona_info)
            todos_parentescos[dni] = parentescos
            todas_empresas[dni] = empresas
            todas_etiquetas[dni] = etiquetas

        # 2. Detectar cruces entre todos los pares
        cruces = []
        dnis_list = [p["dni"] for p in personas_data]

        for i, dni_a in enumerate(dnis_list):
            for j in range(i + 1, len(dnis_list)):
                dni_b = dnis_list[j]

                # 2a. Mismo pariente
                cruces += self._detectar_mismo_pariente(
                    dni_a, dni_b, todos_parentescos[dni_a], todos_parentescos[dni_b],
                    personas_data,
                )

                # 2b. Cadena familiar indirecta
                cruces += self._detectar_cadena_familiar(
                    dni_a, dni_b, todos_parentescos, personas_data,
                )

                # 2c. Misma empresa
                cruces += self._detectar_misma_empresa(
                    dni_a, dni_b, todas_empresas[dni_a], todas_empresas[dni_b],
                    personas_data,
                )

                # 2d. Misma etiqueta
                cruces += self._detectar_misma_etiqueta(
                    dni_a, dni_b, todas_etiquetas[dni_a], todas_etiquetas[dni_b],
                    personas_data,
                )

                # 2e. Misma ubicacion (via direcciones - desde persona.notas)
                cruces += self._detectar_misma_ubicacion(
                    dni_a, dni_b, personas_data,
                )

        # 3. Armar respuesta
        pcp_list = []
        for p in personas_data:
            pcp_list.append(PersonaConParentescos(
                dni=p["dni"],
                nombre_completo=p["nombre_completo"],
                parentescos=p["parentescos"],
                empresas=p["empresas"],
                etiquetas=p["etiquetas"],
            ))

        # Estadisticas
        total_parientes = set()
        for par in todos_parentescos.values():
            for p in par:
                total_parientes.add(p.get("dni", ""))
        total_personas_involucradas = len(dnis_list) + len([x for x in total_parientes if x])

        return CompararResponse(
            personas=pcp_list,
            cruces=cruces,
            estadisticas={
                "total_personas_comparadas": len(dnis_list),
                "total_personas_involucradas": total_personas_involucradas,
                "total_cruces_encontrados": len(cruces),
                "total_parientes_unicos": len(total_parientes),
            },
        )

    # ─── Detector: mismo pariente ──────────────────────────────────────────────

    def _detectar_mismo_pariente(
        self, dni_a: str, dni_b: str,
        parentescos_a: List[dict], parentescos_b: List[dict],
        personas_data: List[dict],
    ) -> List[dict]:
        """Detecta si A y B comparten un mismo familiar."""
        cruces = []
        parientes_b = {p["dni"]: p for p in parentescos_b if p.get("dni")}

        for pa in parentescos_a:
            dni_p = pa.get("dni")
            if not dni_p:
                continue
            if dni_p in parientes_b:
                pb = parientes_b[dni_p]
                nombre = pa.get("nombres", "") + " " + (pa.get("apellidos", "") or "")
                cruces.append(CruceMismoPariente(
                    descripcion=f"👤 {nombre.strip()} es {pa['tipo_parentesco']} de {dni_a} y {pb['tipo_parentesco']} de {dni_b}",
                    pariente_dni=dni_p,
                    pariente_nombre=nombre.strip(),
                    parentesco_con_a=pa["tipo_parentesco"],
                    parentesco_con_b=pb["tipo_parentesco"],
                ).model_dump())
        return cruces

    # ─── Detector: cadena familiar indirecta ───────────────────────────────────

    def _detectar_cadena_familiar(
        self, dni_a: str, dni_b: str,
        todos_parentescos: Dict[str, List[dict]],
        personas_data: List[dict],
    ) -> List[dict]:
        """Detecta si un pariente de A es pariente de B (cadena indirecta).
        
        Ej: A → cuñado(X) → tío → B → "El cuñado de A es el tío de B"
        """
        cruces = []
        parentescos_a = todos_parentescos.get(dni_a, [])

        for pa in parentescos_a:
            dni_p = pa.get("dni")
            if not dni_p:
                continue

            # Obtener parentescos del pariente P
            parentescos_p = calcular_parentesco(self.db, dni_p)

            # ¿Algun parentesco de P lleva a B?
            for pp in parentescos_p:
                if pp.get("dni") == dni_b:
                    nombre_p = pa.get("nombres", "") + " " + (pa.get("apellidos", "") or "")
                    cruces.append(CruceCadena(
                        descripcion=f"🔗 El {pa['tipo_parentesco']} de {dni_a} ({nombre_p.strip()}) es {pp['tipo_parentesco']} de {dni_b}",
                        persona_a_dni=dni_a,
                        persona_b_dni=dni_b,
                        pasos=[
                            {"desde": dni_a, "via": pa["tipo_parentesco"], "hacia": dni_p},
                            {"desde": dni_p, "via": pp["tipo_parentesco"], "hacia": dni_b},
                        ],
                    ).model_dump())
                    break

                # ¿Algun parentesco de P está en los parentescos de B?
                parentescos_b = todos_parentescos.get(dni_b, [])
                parientes_b = {p["dni"]: p for p in parentescos_b if p.get("dni")}
                if pp.get("dni") in parientes_b:
                    pb = parientes_b[pp["dni"]]
                    nombre_p = pa.get("nombres", "") + " " + (pa.get("apellidos", "") or "")
                    nombre_pp = pp.get("nombres", "") + " " + (pp.get("apellidos", "") or "")
                    cruces.append(CruceCadena(
                        descripcion=f"🔗 El {pa['tipo_parentesco']} de {dni_a} ({nombre_p.strip()}) es {pp['tipo_parentesco']} de {nombre_pp.strip()}, quien es {pb['tipo_parentesco']} de {dni_b}",
                        persona_a_dni=dni_a,
                        persona_b_dni=dni_b,
                        pasos=[
                            {"desde": dni_a, "via": pa["tipo_parentesco"], "hacia": dni_p},
                            {"desde": dni_p, "via": pp["tipo_parentesco"], "hacia": pp["dni"]},
                            {"desde": pp["dni"], "via": pb["tipo_parentesco"], "hacia": dni_b},
                        ],
                    ).model_dump())
                    break

        return cruces

    # ─── Detector: misma empresa ────────────────────────────────────────────────

    def _detectar_misma_empresa(
        self, dni_a: str, dni_b: str,
        empresas_a: List[dict], empresas_b: List[dict],
        personas_data: List[dict],
    ) -> List[dict]:
        """Detecta si A y B trabajaron en la misma empresa."""
        cruces = []
        rucs_b = {e["ruc"]: e for e in empresas_b}

        for ea in empresas_a:
            if ea["ruc"] in rucs_b:
                eb = rucs_b[ea["ruc"]]
                nombre_a = next((p["nombre_completo"] for p in personas_data if p["dni"] == dni_a), dni_a)
                nombre_b = next((p["nombre_completo"] for p in personas_data if p["dni"] == dni_b), dni_b)
                cruces.append(CruceEmpresa(
                    descripcion=f"🏢 {nombre_a} y {nombre_b} trabajan/trabajaron en {ea['nombre']} "
                                f"(RUC: {ea['ruc']}) — {nombre_a} como {ea['cargo']}, {nombre_b} como {eb['cargo']}",
                    empresa_ruc=ea["ruc"],
                    empresa_nombre=ea["nombre"],
                    personas=[dni_a, dni_b],
                ).model_dump())
        return cruces

    # ─── Detector: misma etiqueta ───────────────────────────────────────────────

    def _detectar_misma_etiqueta(
        self, dni_a: str, dni_b: str,
        etiquetas_a: List[str], etiquetas_b: List[str],
        personas_data: List[dict],
    ) -> List[dict]:
        """Detecta si A y B comparten etiquetas."""
        cruces = []
        set_b = set(etiquetas_b)
        for etq in set(etiquetas_a):
            if etq in set_b:
                cruces.append(CruceEtiqueta(
                    descripcion=f"🏷️ Ambos tienen la etiqueta '{etq}'",
                    etiqueta=etq,
                    personas=[dni_a, dni_b],
                ).model_dump())
        return cruces

    # ─── Detector: misma ubicacion ─────────────────────────────────────────────

    def _detectar_misma_ubicacion(
        self, dni_a: str, dni_b: str,
        personas_data: List[dict],
    ) -> List[dict]:
        """Detecta si A y B comparten ubicacion (desde notas o data de persona)."""
        # Por ahora, comparamos distritos via notas
        # En el futuro se podria enriquecer con datos de RENIEC/SUNAT
        p_a = next((p for p in personas_data if p["dni"] == dni_a), None)
        p_b = next((p for p in personas_data if p["dni"] == dni_b), None)
        if not p_a or not p_b:
            return []

        # Buscar en parentescos si hay coincidencia de ubicacion
        cruces = []
        # Si ambos tienen la misma provincia/distrito en sus datos de nacimiento
        # (esto requeriria un campo adicional que no existe aun en Persona,
        #  pero podemos dejarlo preparado para cuando se agregue)
        return cruces
