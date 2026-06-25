"""
pedigree.py — Wrapper tipo Pedigree (inspirado en LineageKit) sobre parentesco.py.

Proporciona una API orientada a objetos para navegar el árbol familiar,
usando la CTE de PostgreSQL como backend. No requiere networkx ni numpy.

Uso:
  p = Pedigree(db)
  padres = p.get_parents("12345678")
  abuelos = p.get_grandparents("12345678")
  hermanos = p.get_siblings("12345678")
  arbol = p.get_full_tree("12345678", max_depth=3)
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from models import Persona
from parentesco import calcular_parentesco


class Pedigree:
    """
    Árbol genealógico social (no genético).
    Cada persona puede tener múltiples padres, madres, cónyuges, etc.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Query helpers ─────────────────────────────────────────────────

    def get_persona(self, dni: str) -> Optional[Persona]:
        return self.db.query(Persona).filter(
            Persona.dni == dni, Persona.activo == True
        ).first()

    def get_parentescos(self, dni: str) -> List[Dict]:
        """Retorna TODOS los parientes con tipo y pasos."""
        return calcular_parentesco(self.db, dni)

    # ── Filtros por tipo ──────────────────────────────────────────────

    def get_parents(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("padre", "madre")]

    def get_children(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("hijo", "hija")]

    def get_siblings(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("hermano", "hermana")]

    def get_grandparents(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("abuelo", "abuela")]

    def get_grandchildren(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("nieto", "nieta")]

    def get_uncles_aunts(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("tio", "tia")]

    def get_cousins(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] == "primo"
                or r["tipo_parentesco"] == "prima"]

    def get_spouses(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] == "conyuge"]

    def get_in_laws(self, dni: str) -> List[Dict]:
        return [r for r in self.get_parentescos(dni)
                if r["tipo_parentesco"] in ("suegro", "suegra", "cunado", "cunada", "yerno", "nuera")]

    # ── Árbol completo (multi-nivel) ──────────────────────────────────

    def get_full_tree(self, dni: str, max_depth: int = 3) -> Dict:
        """
        Retorna un árbol jerárquico con todos los parientes hasta max_depth.

        Formato:
        {
          "persona": { "dni": "...", "nombre": "..." },
          "parientes": [
            {"tipo": "padre", "persona": {...}, "pasos": 1,
             "parientes": [ ... hijos de ese padre ... ]},
            ...
          ]
        }
        """
        persona = self.get_persona(dni)
        if not persona:
            return {}

        parientes = self.get_parentescos(dni)
        return self._build_tree(dni, parientes, max_depth, visited=set())

    def _build_tree(self, dni: str, parientes: List[Dict],
                    max_depth: int, visited: set) -> Dict:
        if max_depth <= 0 or dni in visited:
            return {"dni": dni, "tipo": "self", "parientes": []}

        visited.add(dni)
        persona = self.get_persona(dni)
        node = {
            "dni": dni,
            "nombre": persona.nombre_completo if persona else dni,
            "parientes": [],
        }

        for p in parientes:
            if p["pasos"] == 1:  # Solo parientes directos
                # Obtener los parientes reales de cada persona en cada nivel
                parientes_hijo = self.get_parentescos(p["dni"])
                child_tree = self._build_tree(
                    p["dni"], parientes_hijo, max_depth - 1, visited
                )
                if child_tree:
                    child_tree["tipo_relacion"] = p["tipo_parentesco"]
                    node["parientes"].append(child_tree)

        return node
