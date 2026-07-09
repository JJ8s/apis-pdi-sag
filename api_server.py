"""
Servidor FastAPI standalone para las APIs simuladas PDI/SAG.

Uso opcional si quieres levantar las APIs como backend separado de NiceGUI:

    uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload

La web NiceGUI tambien registra estas mismas rutas en main.py, por lo que no es
obligatorio ejecutar este archivo para pruebas locales simples.
"""

from fastapi import FastAPI

from api import registrar_api_routes_en

app = FastAPI(
    title='APIs Simuladas PDI/SAG - Los Libertadores Digital',
    version='1.0.0',
    description='Backend academico para validar declaraciones de ingreso fronterizo.',
)

registrar_api_routes_en(app)


@app.get('/')
async def root():
    return {
        'ok': True,
        'servicio': 'APIs simuladas PDI/SAG',
        'docs': '/docs',
        'endpoints': [
            '/api/pdi/health',
            '/api/pdi/validar',
            '/api/sag/health',
            '/api/sag/validar',
            '/api/app/tramites',
        ],
    }
