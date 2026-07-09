"""
Rutas REST para APIs simuladas PDI y SAG.

NiceGUI usa una app FastAPI internamente, por eso se registran endpoints con
app.add_api_route. Estas rutas quedan disponibles junto con la web.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from services.entidades_service import (
    ESTADO_APROBADO_ENTIDADES,
    ESTADO_PENDIENTE,
    obtener_resumen_validaciones,
    obtener_tramites_aduanero,
    obtener_tramite_aduanero,
    obtener_tramites_para_app,
    marcar_tramite_como_pasado,
    validar_pdi,
    validar_sag,
)


def _respuesta(data: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status_code)


async def _leer_body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def health_pdi() -> JSONResponse:
    return _respuesta({
        'ok': True,
        'entidad': 'PDI',
        'servicio': 'api_simulada_pdi',
        'estado': 'operativo',
        'endpoints': ['/api/pdi/validar', '/api/pdi/health'],
    })


async def health_sag() -> JSONResponse:
    return _respuesta({
        'ok': True,
        'entidad': 'SAG',
        'servicio': 'api_simulada_sag',
        'estado': 'operativo',
        'endpoints': ['/api/sag/validar', '/api/sag/health'],
    })


async def validar_pdi_endpoint(request: Request) -> JSONResponse:
    payload = await _leer_body(request)
    resultado = validar_pdi(payload)
    return _respuesta(resultado, 200 if resultado.get('ok', True) else 404)


async def validar_sag_endpoint(request: Request) -> JSONResponse:
    payload = await _leer_body(request)
    resultado = validar_sag(payload)
    return _respuesta(resultado, 200 if resultado.get('ok', True) else 404)


async def validar_flujo_endpoint(request: Request) -> JSONResponse:
    """Ejecuta PDI y luego SAG para pruebas rapidas del flujo completo."""
    payload = await _leer_body(request)
    resultado_pdi = validar_pdi(payload)

    if not resultado_pdi.get('aprobado'):
        return _respuesta({
            'ok': True,
            'flujo': 'pdi_sag',
            'pdi': resultado_pdi,
            'sag': {
                'ok': True,
                'entidad': 'SAG',
                'aprobado': False,
                'estado': 'omitido',
                'motivos': ['SAG no se ejecuta porque PDI rechazo el tramite.'],
            },
            'estado_final': resultado_pdi.get('estado_revision') or 'rechazado_pdi',
        })

    resultado_sag = validar_sag(payload)
    return _respuesta({
        'ok': True,
        'flujo': 'pdi_sag',
        'pdi': resultado_pdi,
        'sag': resultado_sag,
        'estado_final': resultado_sag.get('estado_revision') or resultado_pdi.get('estado_revision'),
    })


async def obtener_validaciones_endpoint(codigo_tramite: str) -> JSONResponse:
    resultado = obtener_resumen_validaciones(codigo_tramite)
    return _respuesta(resultado, 200 if resultado.get('ok') else 404)


async def tramites_para_app_endpoint(estado: str = '', limite: int = 100) -> JSONResponse:
    """
    Endpoint puente para la app futura de Aduanas.

    Ejemplos:
    - /api/app/tramites?estado=aprobado_entidades
    - /api/app/tramites?estado=rechazado_pdi
    - /api/app/tramites
    """
    limite = max(1, min(int(limite or 100), 500))
    tramites = obtener_tramites_para_app(estado.strip() or None, limite)
    return _respuesta({
        'ok': True,
        'estado_filtrado': estado or 'todos',
        'total': len(tramites),
        'tramites': tramites,
        'estados_utiles_app': [
            ESTADO_PENDIENTE,
            'pdi_aprobado',
            'sag_aprobado',
            ESTADO_APROBADO_ENTIDADES,
            'rechazado_pdi',
            'rechazado_sag',
        ],
    })


async def app_aduanero_health_endpoint() -> JSONResponse:
    return _respuesta({
        'ok': True,
        'servicio': 'api_app_aduanero',
        'estado': 'operativo',
        'ventanas': ['espera', 'denegados', 'historial'],
        'endpoints': [
            '/api/app/aduanero/espera',
            '/api/app/aduanero/denegados',
            '/api/app/aduanero/historial',
            '/api/app/aduanero/tramites/{codigo_tramite}/marcar-paso',
        ],
    })


async def app_aduanero_espera_endpoint(limite: int = 100) -> JSONResponse:
    limite = max(1, min(int(limite or 100), 500))
    tramites = obtener_tramites_aduanero('espera', limite)
    return _respuesta({
        'ok': True,
        'categoria': 'espera',
        'descripcion': 'Aprobados por PDI y SAG, pendientes de paso por Aduanas.',
        'total': len(tramites),
        'tramites': tramites,
    })


async def app_aduanero_denegados_endpoint(limite: int = 100) -> JSONResponse:
    limite = max(1, min(int(limite or 100), 500))
    tramites = obtener_tramites_aduanero('denegados', limite)
    return _respuesta({
        'ok': True,
        'categoria': 'denegados',
        'descripcion': 'Rechazados por PDI o SAG.',
        'total': len(tramites),
        'tramites': tramites,
    })


async def app_aduanero_historial_endpoint(limite: int = 100) -> JSONResponse:
    limite = max(1, min(int(limite or 100), 500))
    tramites = obtener_tramites_aduanero('historial', limite)
    return _respuesta({
        'ok': True,
        'categoria': 'historial',
        'descripcion': 'Viajeros ya marcados como pasaron el pais.',
        'total': len(tramites),
        'tramites': tramites,
    })


async def app_aduanero_detalle_endpoint(codigo_tramite: str) -> JSONResponse:
    tramite = obtener_tramite_aduanero(codigo_tramite)
    if not tramite:
        return _respuesta({'ok': False, 'mensaje': 'Tramite no encontrado.'}, 404)
    return _respuesta({'ok': True, 'tramite': tramite})


async def app_aduanero_marcar_paso_endpoint(codigo_tramite: str) -> JSONResponse:
    resultado = marcar_tramite_como_pasado(codigo_tramite)
    return _respuesta(resultado, 200 if resultado.get('ok') else 400)

def registrar_api_routes_en(api_app) -> None:
    api_app.add_api_route('/api/pdi/health', health_pdi, methods=['GET'])
    api_app.add_api_route('/api/sag/health', health_sag, methods=['GET'])
    api_app.add_api_route('/api/pdi/validar', validar_pdi_endpoint, methods=['POST'])
    api_app.add_api_route('/api/sag/validar', validar_sag_endpoint, methods=['POST'])
    api_app.add_api_route('/api/flujo/validar', validar_flujo_endpoint, methods=['POST'])
    api_app.add_api_route('/api/validaciones/{codigo_tramite}', obtener_validaciones_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/tramites', tramites_para_app_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/health', app_aduanero_health_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/espera', app_aduanero_espera_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/denegados', app_aduanero_denegados_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/historial', app_aduanero_historial_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/tramites/{codigo_tramite}', app_aduanero_detalle_endpoint, methods=['GET'])
    api_app.add_api_route('/api/app/aduanero/tramites/{codigo_tramite}/marcar-paso', app_aduanero_marcar_paso_endpoint, methods=['POST'])


def registrar_api_routes() -> None:
    # Import diferido: evita que api_server.py dependa de NiceGUI cuando se
    # levantan las APIs como FastAPI standalone. En main.py sí existe NiceGUI.
    from nicegui import app as nicegui_app

    registrar_api_routes_en(nicegui_app)
