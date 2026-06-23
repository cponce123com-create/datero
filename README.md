# RedCorruptela 🔍

**Sistema de inteligencia para detección de redes de corrupción y favoritismo político.**

Aplicación web para periodistas de investigación que permite construir una base de datos de personas (con DNI), registrar relaciones familiares y de afinidad, y **deducir automáticamente parentescos complejos** (abuelos, tíos, cuñados, suegros, etc.) mediante consultas recursivas a PostgreSQL.

Además, incorpora un sistema de **etiquetas** para marcar a personas con cargos, sospechas o categorías de investigación (ej. "contratado 2024", "proveedor municipalidad", "familiar de alcalde").

---

## 🏗 Arquitectura

```
├── backend/
│   ├── main.py          # FastAPI app y endpoints REST
│   ├── database.py      # Conexión PostgreSQL (SQLAlchemy + psycopg2)
│   ├── models.py        # Modelos ORM (Persona, Relacion, Etiqueta)
│   ├── schemas.py       # Esquemas Pydantic (validación)
│   ├── crud.py          # Operaciones CRUD
│   ├── parentesco.py    # Motor de inferencia de parentescos
│   ├── auth.py          # HTTP Basic Auth
│   └── requirements.txt
├── static/
│   ├── index.html       # Frontend SPA
│   ├── style.css        # Estilos responsive
│   └── app.js           # Lógica del cliente (vanilla JS)
└── README.md
```

## 🚀 Despliegue

### Requisitos previos

- Cuenta en [Neon](https://neon.tech) (PostgreSQL serverless gratuito)
- Cuenta en [Render](https://render.com) (Web service gratuito)
- Repositorio Git con este código

### Paso 1: Crear la base de datos en Neon

1. Regístrate en [neon.tech](https://neon.tech)
2. Crea un nuevo proyecto
3. Crea una base de datos llamada `redcorruptela`
4. Copia la **connection string** (DATABASE_URL). Se verá así:
   ```
   postgresql://usuario:password@ep-xxxx.us-east-2.aws.neon.tech/redcorruptela?sslmode=require
   ```

### Paso 2: Configurar Render

1. Regístrate en [render.com](https://render.com)
2. Conecta tu cuenta de GitHub/GitLab
3. Crea un nuevo **Web Service**:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Root Directory:** _(dejar vacío o `redcorruptela`)_

4. Agrega las **variables de entorno**:
   | Variable | Descripción |
   |---|---|
   | `DATABASE_URL` | La URL de conexión de Neon (con `?sslmode=require` al final) |
   | `AUTH_USERS` | Usuarios en formato `usuario:contraseña` (ej: `periodista:MiClaveSegura2024`) |

5. Haz clic en **Deploy**

### Paso 3: Acceder a la aplicación

Una vez desplegada, Render te dará una URL tipo `https://redcorruptela.onrender.com`.

Al abrirla, el navegador pedirá credenciales (HTTP Basic Auth). Usa las definidas en `AUTH_USERS`.

### Desarrollo local

```bash
# Clonar el repositorio
git clone <repo-url>
cd redcorruptela

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r backend/requirements.txt

# Configurar variables de entorno
export DATABASE_URL="postgresql://..."
export AUTH_USERS="admin:admin123"

# Iniciar el servidor
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Abrir http://localhost:8000 en el navegador.

---

## 📡 API Endpoints

Todos los endpoints requieren autenticación **HTTP Basic Auth**.

### Personas

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/personas` | Crear persona |
| `GET` | `/api/personas?q=texto` | Buscar por nombre/DNI |
| `GET` | `/api/personas/{dni}` | Ficha completa (datos, relaciones, parentescos, etiquetas) |
| `PUT` | `/api/personas/{dni}` | Actualizar persona |
| `DELETE` | `/api/personas/{dni}` | Baja lógica |
| `GET` | `/api/personas/{dni}/arbol?profundidad=2` | Árbol genealógico |

### Relaciones

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/relaciones` | Crear relación dirigida |
| `GET` | `/api/relaciones/{dni}` | Relaciones directas de una persona |
| `DELETE` | `/api/relaciones/{id}` | Eliminar relación |

### Parentescos (inferencia)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/parentesco?dni=X&tipo=abuelo` | Inferir parentesco específico |

**Tipos soportados:** `abuelo`, `abuela`, `nieto`, `nieta`, `hermano`, `hermana`, `tio`, `tia`, `sobrino`, `sobrina`, `cunado`, `cunada`, `suegro`, `suegra`, `yerno`, `nuera`.

### Etiquetas

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/etiquetas` | Crear etiqueta |
| `GET` | `/api/etiquetas` | Listar todas |
| `GET` | `/api/etiquetas/{nombre}/personas` | Personas con esa etiqueta |
| `POST` | `/api/personas/{dni}/etiquetas` | Asignar etiqueta |
| `DELETE` | `/api/personas/{dni}/etiquetas/{nombre}` | Quitar etiqueta |

---

## 🧠 Motor de inferencia

El sistema deduce parentescos analizando los caminos en el grafo de relaciones. Ejemplos:

- **Abuelo:** Pedro es padre de Juan → Juan es padre de Dubal → Pedro es **abuelo** de Dubal
- **Cuñado:** Carlos es cónyuge de María → María es hermana de Dubal → Carlos es **cuñado** de Dubal
- **Tío:** José comparte padres con Juan → Juan es padre de Dubal → José es **tío** de Dubal
- **Suegro:** Ana es madre de Pedro → Pedro es cónyuge de María → Ana es **suegra** de María

Las inferencias se calculan **en tiempo real** mediante consultas SQL; no se almacenan.

---

## 🏷 Sistema de etiquetas

Las etiquetas permiten categorizar personas para la investigación:

- `contratado 2024`
- `proveedor municipalidad`
- `familiar de alcalde`
- `investigación abierta`
- `contrato sospechoso`

Cada asignación puede incluir una observación (ej: "Contrato N° 123-2024-MDP por S/ 45,000").

---

## 🔒 Seguridad

- **HTTP Basic Auth** en todos los endpoints
- **Parámetros enlazados** en todas las consultas SQL (previene inyección)
- **Comparación segura** de contraseñas (`secrets.compare_digest`)
- **DNI como identificador único** con índice en base de datos
- **Baja lógica** (no se borran datos permanentemente)

---

## 📝 Licencia

Uso interno. Código confidencial para el periodista investigador.
