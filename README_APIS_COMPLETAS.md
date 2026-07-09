# APIs simuladas PDI y SAG - Los Libertadores Digital

Este paquete contiene solo las APIs simuladas PDI/SAG y los servicios necesarios para conectarse a Supabase. No incluye la web NiceGUI ni la app móvil.

## Requisitos

- Python 3.10+
- Supabase con tabla `public.declaraciones`
- Variables de entorno en `.env`

```env
SUPABASE_URL=https://uwciggpqeyftepydjzii.supabase.co
SUPABASE_KEY=TU_SUPABASE_KEY
```

## Instalación

```bash
pip install -r requirements_api.txt
```

## Ejecutar APIs separadas de la web

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload
```

En Windows también puedes ejecutar:

```bat
run_api.bat
```

## Endpoints PDI

### Health

```http
GET /api/pdi/health
```

### Validar PDI

```http
POST /api/pdi/validar
Content-Type: application/json
```

Puede recibir un trámite guardado:

```json
{
  "codigo_tramite": "TRAMITE-123456"
}
```

O un payload directo:

```json
{
  "nombre": "Matias Ignacio",
  "apellido": "Rivera Soto",
  "correo": "matias.rivera.prueba@mail.com",
  "pais_emisor": "Chile",
  "numero_documento": "12345678-K",
  "nacionalidad": "Chilena",
  "fecha_nacimiento": "1994-05-17",
  "fecha_ingreso": "2026-08-15",
  "paso_fronterizo": "Complejo Fronterizo Los Libertadores",
  "proposito_viaje": "turismo",
  "viaja_con_menores": true,
  "lista_menores": [
    {
      "nombre_completo": "Sofia Valentina Rivera Morales",
      "parentesco": "Padre",
      "pais_emisor": "Chile",
      "numero_documento": "24567890-1",
      "tipo_autorizacion": "Autorizacion notarial del padre/madre que no viaja"
    }
  ]
}
```

## Endpoints SAG

### Health

```http
GET /api/sag/health
```

### Validar SAG

```http
POST /api/sag/validar
Content-Type: application/json
```

Puede recibir un trámite guardado:

```json
{
  "codigo_tramite": "TRAMITE-123456"
}
```

O un payload directo:

```json
{
  "codigo_tramite": "TEST-DIRECTO-SAG",
  "declara_alimentos_animales_plantas": true,
  "detalle_productos_sag": "Porto un animal de compañía: perro doméstico. Nombre Luna.",
  "archivo_sag_nombre": "declaracion_sag_animal_prueba.pdf"
}
```

## Flujo completo PDI -> SAG

```http
POST /api/flujo/validar
Content-Type: application/json
```

```json
{
  "codigo_tramite": "TRAMITE-123456"
}
```

Si PDI rechaza, SAG se omite. Si PDI y SAG aprueban, el estado queda `aprobado_entidades`.

## Estados usados

- `pendiente_envio`
- `pdi_aprobado`
- `sag_aprobado`
- `aprobado_entidades`
- `rechazado_pdi`
- `rechazado_sag`
- `paso_pais`

## Puente para app futura de Aduanas

Aunque este paquete es PDI/SAG, mantiene los endpoints de consulta para la app futura:

```http
GET /api/app/aduanero/espera
GET /api/app/aduanero/denegados
GET /api/app/aduanero/historial
POST /api/app/aduanero/tramites/{codigo_tramite}/marcar-paso
```

La app debe leer `espera` para trámites con `aprobado_entidades`, `denegados` para `rechazado_pdi` o `rechazado_sag`, e `historial` para `paso_pais`.

## SQL RLS

Ejecuta `sql/rls_declaraciones.sql` en Supabase si recibes errores `42501`.
