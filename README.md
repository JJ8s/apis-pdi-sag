# APIs PDI/SAG completas

Paquete standalone de APIs simuladas PDI y SAG para el proyecto Los Libertadores Digital.

Archivo principal: `api_server.py`.

Ejecutar:

```bash
pip install -r requirements_api.txt
uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload
```

Documentación local de FastAPI:

```text
http://localhost:8090/docs
```

Lee `README_APIS_COMPLETAS.md` para endpoints, payloads y estados.
