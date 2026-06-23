# SunatScraper — Documentación Técnica

## Descripción

Scraper oficial de SUNAT para consulta gratuita de RUC.
Reemplaza la dependencia de `apiperu.dev` (servicio externo pago)
por scraping directo del portal público `e-consultaruc.sunat.gob.pe`.

## Flujo de Consulta

```
┌──────────┐     ┌──────────────────┐     ┌──────────┐
│ Usuario   │────▶│ SunatScraper      │────▶│ SUNAT    │
│ (FastAPI) │     │ requests+BS4      │     │ Portal   │
└──────────┘     └──────────────────┘     └──────────┘
```

### Paso a paso:

1. **GET** `https://e-consultaruc.sunat.gob.pe/`
   - Obtiene cookie de sesión
   - Extrae `numRnd` del formulario oculto

2. **POST** `https://e-consultaruc.sunat.gob.pe/`
   - Envía: `numRnd`, `ruc`, `accion=buscarPorRuc`
   - Recibe HTML con tabla de resultados

3. **Parseo** con BeautifulSoup + lxml
   - Extrae campos de las tablas HTML
   - Normaliza nombres de campos

## API Endpoints

### `GET /api/consultar/ruc?ruc=20123456789`

Respuesta exitosa:
```json
{
  "numero": "20123456789",
  "nombre_o_razon_social": "MINERIA PERU S.A.C.",
  "tipo_contribuyente": "SOCIEDAD ANONIMA CERRADA",
  "nombre_comercial": "MINERIA PERU",
  "estado": "ACTIVO",
  "condicion": "HABIDO",
  "direccion": "AV. PRINCIPAL 123",
  "departamento": "LIMA",
  "provincia": "LIMA",
  "distrito": "MIRAFLORES",
  "fecha_inscripcion": "15/03/2010",
  "fecha_inicio_actividades": "01/04/2010",
  "sistema_contabilidad": "MANUAL",
  "actividad_comercio_exterior": "SIN ACTIVIDAD",
  "actividad_economica": "MINERIA",
  "comprobantes_autorizados": "FACTURA, BOLETA",
  "sistema_emision": "MANUAL",
  "afiliado_ple": "NO"
}
```

### `GET /api/consultar-ruc/{ruc}` (alias)

## Caché

- **cachetools.TTLCache** con 256 entradas máximas
- **TTL**: 24 horas
- Se limpia automáticamente al expirar
- Función `limpiar_cache()` para limpieza manual

## Puntos de Falla Conocidos

| Problema | Síntoma | Manejo |
|----------|---------|--------|
| SUNAT cambia HTML | No se encuentra `numRnd` o tabla | `SunatScraperError` con mensaje claro |
| CAPTCHA/Cloudflare | `captcha`, `g-recaptcha` en HTML | `CaptchaDetectedError` (no reintenta) |
| Timeout | Conexión lenta o caída | Reintento automático hasta 3 veces |
| RUC no existe | "No se encontraron resultados" | `SunatScraperError` |
| Bloqueo por IP | Acceso denegado | Espera exponencial entre reintentos |

## Mantenimiento Futuro

### Si SUNAT cambia el parámetro `numRnd`:
1. Revisar `_obtener_num_rnd()` - buscar nuevo patrón en HTML
2. Actualizar regex: `r'name=["']numRnd["'][^>]*value=["']([^"']+)["']'`

### Si SUNAT cambia la tabla de resultados:
1. Revisar `_parsear_html()` - mapeo de labels
2. Actualizar diccionario de mapeo

### Si SUNAT agrega CAPTCHA permanente:
1. El scraper ya detecta CAPTCHA automáticamente
2. Evaluar alternativas: apiperu.dev como fallback

## Ejecución de Tests

```bash
cd backend
python -m pytest tests/test_sunat_scraper.py -v
```

## Dependencias

```txt
requests>=2.28.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
cachetools>=5.3.0
```

## Comparación con apiperu.dev

| Aspecto | apiperu.dev | SunatScraper |
|---------|-------------|--------------|
| Costo | Token (plan free 50/día) | Gratuito |
| Fuente | API privada | SUNAT directo |
| Campos DNI | ✅ | ❌ (solo RUC) |
| Campos RUC | ✅ Básicos | ✅ Completos (18 campos) |
| Velocidad | ~200ms | ~2-3s |
| Confiabilidad | Alta (servicio dedicado) | Media (depende de SUNAT) |
| Mantenimiento | Ninguno (tercero) | Manual (SUNAT cambia HTML) |
