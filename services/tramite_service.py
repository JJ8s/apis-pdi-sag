"""
SERVICIO DE TRAMITE - Portal Viajero
=====================================
Versión corregida para Supabase usando SOLO la tabla public.declaraciones.

Tabla esperada en Supabase:
- declaraciones:
  codigo, nombre, apellido, dni, pais, nacionalidad, fecha_nacimiento,
  correo, proposito, menores, bienes, estado_revision, created_at.

Importante:
- NO usa la tabla antigua public.tramite.
- La fecha de vencimiento del documento ya no es obligatoria.
"""

import uuid
from datetime import date, datetime
import logging
import re
from services.supabase_service import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLA_DECLARACIONES = 'declaraciones'
ESTADO_INICIAL = 'pendiente_envio'


def _safe_strip(valor) -> str:
    return str(valor or '').strip()


def _es_mayor_de_edad(fecha_texto):
    try:
        nacimiento = datetime.strptime(_safe_strip(fecha_texto), '%Y-%m-%d').date()
    except ValueError:
        return False

    hoy = date.today()
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return nacimiento <= hoy and edad >= 18




def _fecha_no_pasada(fecha_texto):
    try:
        fecha = datetime.strptime(_safe_strip(fecha_texto), '%Y-%m-%d').date()
    except ValueError:
        return False
    return fecha >= date.today()


def _bool_estricto(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() in {'true', '1', 'si', 'sí', 's', 'yes'}
    return bool(valor)

def _normalizar_declaracion(row: dict) -> dict:
    """
    Convierte una fila de public.declaraciones al formato que varias pantallas
    antiguas podrían esperar: codigo_tramite, numero_documento, pais_emisor, etc.
    """
    row = row or {}
    bienes = row.get('bienes') or {}
    pdi = bienes.get('pdi') or {}
    viaje = bienes.get('viaje') or {}
    sag = bienes.get('sag') or {}
    aduanas = bienes.get('aduanas') or {}
    menores_data = bienes.get('menores') or {}
    vehiculo = bienes.get('vehiculo') or {}

    normalizado = dict(row)
    normalizado.update({
        'codigo_tramite': row.get('codigo', ''),
        'tipo_documento': pdi.get('tipo_documento', ''),
        'pais_emisor': row.get('pais', ''),
        'numero_documento': row.get('dni', ''),
        'proposito_viaje': row.get('proposito', ''),
        'fecha_ingreso': viaje.get('fecha_ingreso', ''),
        'paso_fronterizo': viaje.get('paso_fronterizo', ''),
        'direccion_estadia': viaje.get('direccion_estadia', ''),
        'declara_alimentos_animales_plantas': bool(sag.get('declara_productos', False)),
        'detalle_productos_sag': sag.get('detalle_productos', ''),
        'declara_divisas_mayor_10k': bool(aduanas.get('declara_divisas_mayor_10k', False)),
        'monto_divisas': aduanas.get('monto_divisas', ''),
        'moneda_divisas': aduanas.get('moneda_divisas', ''),
        'origen_fondos': aduanas.get('origen_fondos', ''),
        'viaja_con_menores': bool(row.get('menores', False)),
        'detalle_menores': menores_data.get('detalle_menores', ''),
        'lista_menores': menores_data.get('lista_menores', []),
        'patente_vehiculo': vehiculo.get('patente_vehiculo', ''),
        'marca_vehiculo': vehiculo.get('marca_vehiculo', ''),
        'modelo_vehiculo': vehiculo.get('modelo_vehiculo', ''),
        'estado': row.get('estado_revision', ESTADO_INICIAL),
        'fecha_creacion': row.get('created_at', ''),
        'nombre_completo': f"{row.get('nombre', '')} {row.get('apellido', '')}".strip(),
        'archivo_sag_nombre': sag.get('archivo_declaracion', ''),
    })
    return normalizado


def _normalizar_lista_declaraciones(rows) -> list:
    return [_normalizar_declaracion(row) for row in (rows or [])]


# ============================================================================
# FUNCIONES PRINCIPALES
# ============================================================================

def guardar_tramite(datos: dict) -> dict:
    """
    Guarda el trámite en Supabase usando la tabla public.declaraciones.
    """
    try:
        if not datos.get('consentimiento_datos'):
            return {
                'exito': False,
                'mensaje': '❌ Debes aceptar el uso de datos personales antes de enviar el trámite',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        numero_doc = _safe_strip(datos.get('numero_documento'))
        if not numero_doc:
            return {
                'exito': False,
                'mensaje': '❌ El número de documento es obligatorio',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        if not re.fullmatch(r'[A-Za-z0-9-]{5,20}', numero_doc):
            return {
                'exito': False,
                'mensaje': '❌ Documento inválido. Usa solo letras, números y guion cuando corresponda',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        if not _safe_strip(datos.get('tipo_documento')):
            return {
                'exito': False,
                'mensaje': '❌ El tipo de documento es obligatorio',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        correo = _safe_strip(datos.get('correo'))
        if not correo or '@' not in correo:
            return {
                'exito': False,
                'mensaje': '❌ Correo inválido o vacío',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        campos_obligatorios = [
            ('pais_emisor', 'país emisor'),
            ('nombre', 'nombre'),
            ('apellido', 'apellido'),
            ('nacionalidad', 'nacionalidad'),
            ('fecha_nacimiento', 'fecha de nacimiento'),
            ('fecha_ingreso', 'fecha de ingreso'),
            ('paso_fronterizo', 'paso fronterizo'),
            ('direccion_estadia', 'dirección o lugar de estadía'),
            ('proposito_viaje', 'propósito de viaje'),
        ]

        for campo, etiqueta in campos_obligatorios:
            if not _safe_strip(datos.get(campo)):
                return {
                    'exito': False,
                    'mensaje': f'❌ Debes ingresar {etiqueta}',
                    'codigo_tramite': None,
                    'datos_retorno': None,
                }

        if not _es_mayor_de_edad(datos.get('fecha_nacimiento', '')):
            return {
                'exito': False,
                'mensaje': '❌ La fecha de nacimiento debe ser válida y corresponder a una persona mayor de 18 años',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        if not _fecha_no_pasada(datos.get('fecha_ingreso', '')):
            return {
                'exito': False,
                'mensaje': '❌ La fecha estimada de ingreso debe ser válida y no puede ser anterior a hoy',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        proposito = _safe_strip(datos.get('proposito_viaje')).lower()
        propositos_validos = {'turismo', 'negocios', 'carga', 'residencia'}
        if proposito not in propositos_validos:
            return {
                'exito': False,
                'mensaje': '❌ El propósito de viaje debe ser turismo, negocios, carga o residencia',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        codigo_tramite = str(uuid.uuid4())

        lista_menores = datos.get('menores') or datos.get('lista_menores') or []
        if not isinstance(lista_menores, list):
            lista_menores = []

        viaja_con_menores = _bool_estricto(datos.get('viaja_con_menores', False))
        if viaja_con_menores and not lista_menores:
            return {
                'exito': False,
                'mensaje': '❌ Si viajas con menores, debes registrar al menos un menor',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        declara_sag = _bool_estricto(datos.get('declara_alimentos_animales_plantas', False))
        detalle_sag = _safe_strip(datos.get('detalle_productos_sag'))
        if declara_sag and not detalle_sag:
            return {
                'exito': False,
                'mensaje': '❌ Si declaras SAG, debes detallar los productos, animales, plantas o derivados',
                'codigo_tramite': None,
                'datos_retorno': None,
            }

        declara_divisas = _bool_estricto(datos.get('declara_divisas_mayor_10k', False))
        monto_divisas = _safe_strip(datos.get('monto_divisas'))
        moneda_divisas = _safe_strip(datos.get('moneda_divisas')) or 'USD'
        origen_fondos = _safe_strip(datos.get('origen_fondos'))
        if declara_divisas:
            try:
                monto_num = float(monto_divisas.replace(',', '.'))
            except ValueError:
                monto_num = 0
            if monto_num <= 10000:
                return {
                    'exito': False,
                    'mensaje': '❌ Si declaras divisas, el monto debe ser numérico y mayor a USD 10.000 o equivalente',
                    'codigo_tramite': None,
                    'datos_retorno': None,
                }
            if not origen_fondos:
                return {
                    'exito': False,
                    'mensaje': '❌ Debes indicar el origen o motivo del transporte de fondos',
                    'codigo_tramite': None,
                    'datos_retorno': None,
                }
        else:
            monto_divisas = '0'
            moneda_divisas = moneda_divisas or 'USD'
            origen_fondos = origen_fondos or 'No aplica'

        flujo_simulado = {
            'pdi': 'pendiente_envio',
            'sag': 'pendiente_envio',
            'aduanas': 'pendiente_envio',
            'descripcion': 'Flujo preparado para orquestación con n8n o APIs simuladas.',
        }

        bienes_json = {
            'pdi': {
                'tipo_documento': _safe_strip(datos.get('tipo_documento')),
                'pais_emisor': _safe_strip(datos.get('pais_emisor')),
                'numero_documento': numero_doc,
            },
            'viaje': {
                'fecha_ingreso': _safe_strip(datos.get('fecha_ingreso')),
                'paso_fronterizo': _safe_strip(datos.get('paso_fronterizo')),
                'direccion_estadia': _safe_strip(datos.get('direccion_estadia')),
                'proposito_viaje': proposito,
            },
            'sag': {
                'declara_productos': declara_sag,
                'detalle_productos': detalle_sag if declara_sag else 'No aplica',
                'archivo_declaracion': _safe_strip(datos.get('archivo_sag_nombre')),
            },
            'aduanas': {
                'declara_divisas_mayor_10k': declara_divisas,
                'monto_divisas': monto_divisas,
                'moneda_divisas': moneda_divisas,
                'origen_fondos': origen_fondos,
            },
            'menores': {
                'viaja_con_menores': viaja_con_menores,
                'detalle_menores': _safe_strip(datos.get('detalle_menores')),
                'lista_menores': lista_menores,
            },
            'vehiculo': {
                'patente_vehiculo': _safe_strip(datos.get('patente_vehiculo')),
                'marca_vehiculo': _safe_strip(datos.get('marca_vehiculo')),
                'modelo_vehiculo': _safe_strip(datos.get('modelo_vehiculo')),
            },
            'consentimiento': {
                'aceptado': bool(datos.get('consentimiento_datos', False)),
                'fecha': datos.get('fecha_consentimiento', datetime.now().isoformat()),
                'finalidad': datos.get('finalidad_datos', 'Gestión académica simulada de ingreso fronterizo'),
                'ley_referencia': 'Ley 21.719',
            },
            'flujo_simulado': flujo_simulado,
        }

        declaracion_data = {
            'codigo': codigo_tramite,
            'nombre': _safe_strip(datos.get('nombre')),
            'apellido': _safe_strip(datos.get('apellido')),
            'dni': numero_doc,
            'pais': _safe_strip(datos.get('pais_emisor')),
            'nacionalidad': _safe_strip(datos.get('nacionalidad')),
            'fecha_nacimiento': _safe_strip(datos.get('fecha_nacimiento')),
            'correo': correo,
            'proposito': proposito,
            'menores': viaja_con_menores,
            'bienes': bienes_json,
            'estado_revision': ESTADO_INICIAL,
        }

        logger.info(f"Insertando declaración {codigo_tramite} en public.{TABLA_DECLARACIONES} para {correo}...")
        resultado = supabase.table(TABLA_DECLARACIONES).insert(declaracion_data).execute()

        data_insertada = resultado.data[0] if resultado.data else declaracion_data
        data_insertada = _normalizar_declaracion(data_insertada)

        logger.info(f"✅ Trámite {codigo_tramite} guardado exitosamente en {TABLA_DECLARACIONES}")
        return {
            'exito': True,
            'codigo_tramite': codigo_tramite,
            'mensaje': f'✅ Trámite guardado exitosamente (Código: {codigo_tramite})',
            'datos_retorno': data_insertada,
            'tabla': TABLA_DECLARACIONES,
        }

    except ConnectionError as e:
        logger.error(f"❌ Error de conexión a Supabase: {str(e)}")
        return {
            'exito': False,
            'mensaje': '❌ Error de conexión. Verifica tu internet y reinténtalo.',
            'codigo_tramite': None,
            'datos_retorno': None,
        }

    except Exception as e:
        logger.error(f"❌ Error inesperado al guardar trámite: {str(e)}")
        return {
            'exito': False,
            'mensaje': f'❌ Error: {str(e)[:180]}',
            'codigo_tramite': None,
            'datos_retorno': None,
        }


def obtener_tramites_usuario(correo: str) -> list:
    try:
        logger.info(f"Consultando declaraciones para {correo}...")
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('correo', correo)
            .order('created_at', desc=True)
            .execute()
        )
        return _normalizar_lista_declaraciones(resultado.data)
    except Exception as e:
        logger.error(f"❌ Error obteniendo declaraciones del usuario: {str(e)}")
        return []


def actualizar_estado_tramite(codigo_tramite: str, nuevo_estado: str) -> bool:
    try:
        logger.info(f"Actualizando estado de {codigo_tramite} a '{nuevo_estado}'...")
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .update({'estado_revision': nuevo_estado})
            .eq('codigo', codigo_tramite)
            .execute()
        )
        return bool(resultado.data)
    except Exception as e:
        logger.error(f"❌ Error actualizando estado: {str(e)}")
        return False


# ============================================================================
# CONSULTAS AUXILIARES
# ============================================================================

def obtener_tramite_por_codigo(codigo_tramite: str) -> dict:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('codigo', codigo_tramite)
            .execute()
        )
        return _normalizar_declaracion(resultado.data[0]) if resultado.data else {}
    except Exception as e:
        logger.error(f"Error obteniendo trámite {codigo_tramite}: {str(e)}")
        return {}


def obtener_tramites_por_estado(estado: str, limite: int = 100) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('estado_revision', estado)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        return _normalizar_lista_declaraciones(resultado.data)
    except Exception as e:
        logger.error(f"Error obteniendo trámites en estado {estado}: {str(e)}")
        return []


def obtener_tramites_por_proposito(proposito: str, limite: int = 100) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('proposito', proposito)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        return _normalizar_lista_declaraciones(resultado.data)
    except Exception as e:
        logger.error(f"Error obteniendo trámites por propósito: {str(e)}")
        return []


def obtener_declaraciones_sag_pendientes(limite: int = 50) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('estado_revision', ESTADO_INICIAL)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        declaraciones = _normalizar_lista_declaraciones(resultado.data)
        return [d for d in declaraciones if d.get('declara_alimentos_animales_plantas')]
    except Exception as e:
        logger.error(f"Error obteniendo declaraciones SAG: {str(e)}")
        return []


def obtener_declaraciones_aduanas_alerta(limite: int = 50) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('estado_revision', ESTADO_INICIAL)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        declaraciones = _normalizar_lista_declaraciones(resultado.data)
        return [d for d in declaraciones if d.get('declara_divisas_mayor_10k')]
    except Exception as e:
        logger.error(f"Error obteniendo declaraciones de aduanas: {str(e)}")
        return []


def obtener_tramites_con_vehiculo(limite: int = 50) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        declaraciones = _normalizar_lista_declaraciones(resultado.data)
        return [d for d in declaraciones if d.get('patente_vehiculo')]
    except Exception as e:
        logger.error(f"Error obteniendo trámites con vehículo: {str(e)}")
        return []




def obtener_todas_declaraciones(limite: int = 1000) -> list:
    try:
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        return _normalizar_lista_declaraciones(resultado.data)
    except Exception as e:
        logger.error(f"Error obteniendo todas las declaraciones: {str(e)}")
        return []


# Alias de compatibilidad para scripts antiguos.
obtener_tramite = obtener_tramite_por_codigo

def obtener_estadisticas_tramites() -> dict:
    try:
        todos = supabase.table(TABLA_DECLARACIONES).select('id', count='exact').execute()
        total = todos.count if hasattr(todos, 'count') else 0

        pendientes = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('id', count='exact')
            .eq('estado_revision', ESTADO_INICIAL)
            .execute()
        )
        pendientes_count = pendientes.count if hasattr(pendientes, 'count') else 0

        aprobados = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('id', count='exact')
            .eq('estado_revision', 'aprobado')
            .execute()
        )
        aprobados_count = aprobados.count if hasattr(aprobados, 'count') else 0

        rechazados = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('id', count='exact')
            .eq('estado_revision', 'rechazado')
            .execute()
        )
        rechazados_count = rechazados.count if hasattr(rechazados, 'count') else 0

        return {
            'total': total,
            'pendientes': pendientes_count,
            'aprobados': aprobados_count,
            'rechazados': rechazados_count,
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return {
            'total': 0,
            'pendientes': 0,
            'aprobados': 0,
            'rechazados': 0,
        }
