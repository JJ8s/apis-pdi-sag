"""
Servicios para APIs simuladas PDI y SAG.

Estas funciones permiten validar una declaracion guardada en Supabase o un
payload directo enviado por POST. El objetivo es academico: simular el flujo
PDI -> SAG -> Aduanas sin conectar entidades reales.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from services.supabase_service import supabase
from services.tramite_service import TABLA_DECLARACIONES, _normalizar_declaracion

logger = logging.getLogger(__name__)

ESTADO_PENDIENTE = 'pendiente_envio'
ESTADO_PDI_APROBADO = 'pdi_aprobado'
ESTADO_SAG_APROBADO = 'sag_aprobado'
ESTADO_APROBADO_ENTIDADES = 'aprobado_entidades'
ESTADO_RECHAZADO_PDI = 'rechazado_pdi'
ESTADO_RECHAZADO_SAG = 'rechazado_sag'
ESTADO_PASO_PAIS = 'paso_pais'

PAISES_VALIDOS = {'chile', 'argentina', 'peru', 'perú', 'bolivia'}
PROPOSITOS_VALIDOS = {'turismo', 'negocios', 'carga', 'residencia'}
PASOS_FRONTERIZOS_VALIDOS = {
    'complejo fronterizo los libertadores',
    'complejo los libertadores',
    'los libertadores',
    'paso los libertadores',
    'sistema integrado cristo redentor',
    'cristo redentor',
}
DOCUMENTO_CHILE = re.compile(r'^\d{7,8}-[0-9Kk]$')
DOCUMENTO_NUMERICO_7_8 = re.compile(r'^\d{7,8}$')
DOCUMENTO_NUMERICO_8 = re.compile(r'^\d{8}$')
DOCUMENTO_NUMERICO_5_9 = re.compile(r'^\d{5,9}$')

PRODUCTOS_SAG_RIESGO = [
    'carne cruda',
    'fruta fresca',
    'semilla',
    'semillas',
    'planta con tierra',
    'tierra',
    'queso artesanal',
    'lacteo sin sellar',
    'lácteo sin sellar',
]


def _safe_str(valor: Any) -> str:
    return str(valor or '').strip()


def _normalizar_texto(valor: Any) -> str:
    texto = _safe_str(valor).lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r'\s+', ' ', texto).strip()


def _bool_estricto(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() in {'true', '1', 'si', 'sí', 's', 'yes', 'declaro'}
    return bool(valor)


def _parse_fecha(fecha_texto: Any) -> Optional[date]:
    texto = _safe_str(fecha_texto).replace('/', '-')
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


def _es_mayor_de_edad(fecha_nacimiento: Any) -> bool:
    nacimiento = _parse_fecha(fecha_nacimiento)
    if not nacimiento:
        return False
    hoy = date.today()
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return nacimiento <= hoy and edad >= 18


def _fecha_no_pasada(fecha_texto: Any) -> bool:
    fecha = _parse_fecha(fecha_texto)
    return bool(fecha and fecha >= date.today())


def _codigo_desde_payload(payload: Dict[str, Any]) -> str:
    return _safe_str(
        payload.get('codigo_tramite')
        or payload.get('codigo')
        or payload.get('id_tramite')
        or payload.get('tramite_codigo')
    )


def obtener_declaracion_raw(codigo_tramite: str) -> Optional[dict]:
    if not codigo_tramite:
        return None
    resultado = (
        supabase
        .table(TABLA_DECLARACIONES)
        .select('*')
        .eq('codigo', codigo_tramite)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def obtener_declaracion_normalizada(codigo_tramite: str) -> Optional[dict]:
    row = obtener_declaracion_raw(codigo_tramite)
    return _normalizar_declaracion(row) if row else None


def _payload_para_validar(payload: Dict[str, Any]) -> Tuple[Optional[dict], Optional[dict], str]:
    """
    Devuelve (row_raw, datos_normalizados, codigo).
    Si el payload trae codigo_tramite, se consulta Supabase.
    Si no trae codigo, se valida el body directo.
    """
    codigo = _codigo_desde_payload(payload)
    if codigo:
        row = obtener_declaracion_raw(codigo)
        if not row:
            return None, None, codigo
        return row, _normalizar_declaracion(row), codigo
    return None, dict(payload), ''


def _validar_documento(pais: Any, documento: Any) -> Tuple[bool, str]:
    pais_norm = _normalizar_texto(pais)
    documento = _safe_str(documento).replace('.', '').replace(' ', '').upper()

    if pais_norm not in PAISES_VALIDOS:
        return False, 'Pais emisor no soportado para esta simulacion.'

    if pais_norm == 'chile':
        # Acepta 12345678-K y tambien 12345678K para que la API sea tolerante
        # con integraciones externas. El formulario web ya normaliza con guion.
        if '-' not in documento and re.fullmatch(r'\d{7,8}[0-9K]', documento):
            documento = f'{documento[:-1]}-{documento[-1]}'
        if not DOCUMENTO_CHILE.fullmatch(documento):
            return False, 'Documento chileno invalido. Formato esperado: 12345678-K.'
        return True, ''

    if pais_norm in {'peru', 'perú'}:
        if not DOCUMENTO_NUMERICO_8.fullmatch(documento):
            return False, 'Documento peruano invalido. Debe tener 8 numeros.'
        return True, ''

    if pais_norm == 'argentina':
        if not DOCUMENTO_NUMERICO_7_8.fullmatch(documento):
            return False, 'Documento argentino invalido. Debe tener 7 a 8 numeros.'
        return True, ''

    if pais_norm == 'bolivia':
        if not DOCUMENTO_NUMERICO_5_9.fullmatch(documento):
            return False, 'Documento boliviano invalido. Debe tener 5 a 9 numeros.'
        return True, ''

    return False, 'Pais emisor no soportado.'


def _validar_menores(datos: Dict[str, Any]) -> List[str]:
    errores: List[str] = []
    viaja_con_menores = _bool_estricto(datos.get('viaja_con_menores'))
    lista_menores = datos.get('lista_menores') or datos.get('menores') or []

    if isinstance(lista_menores, dict):
        lista_menores = [lista_menores]
    if not isinstance(lista_menores, list):
        lista_menores = []

    if viaja_con_menores and not lista_menores:
        errores.append('Debe existir al menos un menor registrado.')
        return errores

    if not viaja_con_menores:
        return errores

    for indice, menor in enumerate(lista_menores, start=1):
        menor = menor or {}
        nombre = _safe_str(menor.get('nombre') or menor.get('nombre_completo'))
        parentesco = _safe_str(menor.get('parentesco') or menor.get('relacion'))
        pais = _safe_str(menor.get('pais_emisor') or menor.get('pais'))
        documento = _safe_str(menor.get('numero_documento') or menor.get('documento'))
        autorizacion = _safe_str(menor.get('tipo_autorizacion') or menor.get('autorizacion'))

        if not nombre:
            errores.append(f'Menor {indice}: falta nombre completo.')
        if not parentesco:
            errores.append(f'Menor {indice}: falta parentesco o relacion.')
        if not documento:
            errores.append(f'Menor {indice}: falta numero de documento.')
        if pais and documento:
            doc_ok, doc_msg = _validar_documento(pais, documento)
            if not doc_ok:
                errores.append(f'Menor {indice}: {doc_msg}')
        elif not pais:
            errores.append(f'Menor {indice}: falta pais emisor del documento.')
        if not autorizacion:
            errores.append(f'Menor {indice}: falta documento/autorizacion de viaje.')

    return errores


def _estado_final_por_validaciones(bienes: dict, entidad_actual: str, aprobado: bool) -> str:
    """
    Calcula el estado global sin perder rechazos previos.

    Antes, si PDI rechazaba y luego alguien ejecutaba SAG manualmente, el estado
    podia quedar como sag_aprobado, ocultando el rechazo PDI. Para la app futura
    de Aduanas eso es peligroso: un tramite con cualquier entidad rechazada debe
    seguir apareciendo como rechazado hasta que esa misma entidad sea corregida y
    revalidada como aprobada.
    """
    validaciones = bienes.get('validaciones') or {}
    pdi = dict(validaciones.get('pdi') or {})
    sag = dict(validaciones.get('sag') or {})

    if entidad_actual == 'pdi':
        pdi['aprobado'] = bool(aprobado)
    if entidad_actual == 'sag':
        sag['aprobado'] = bool(aprobado)

    if pdi.get('aprobado') is False:
        return ESTADO_RECHAZADO_PDI
    if sag.get('aprobado') is False:
        return ESTADO_RECHAZADO_SAG

    if pdi.get('aprobado') is True and sag.get('aprobado') is True:
        return ESTADO_APROBADO_ENTIDADES
    if pdi.get('aprobado') is True:
        return ESTADO_PDI_APROBADO
    if sag.get('aprobado') is True:
        return ESTADO_SAG_APROBADO

    return ESTADO_PENDIENTE


def _actualizar_resultado_entidad(row: dict, entidad: str, resultado: dict) -> None:
    bienes = deepcopy(row.get('bienes') or {})
    bienes.setdefault('flujo_simulado', {})
    bienes.setdefault('validaciones', {})

    aprobado = bool(resultado.get('aprobado'))
    bienes['flujo_simulado'][entidad] = 'aprobado' if aprobado else 'rechazado'
    bienes['validaciones'][entidad] = {
        'aprobado': aprobado,
        'estado': resultado.get('estado'),
        'motivos': resultado.get('motivos', []),
        'advertencias': resultado.get('advertencias', []),
        'entidad': resultado.get('entidad', entidad.upper()),
        'fecha_validacion': datetime.now().isoformat(timespec='seconds'),
        'modo': 'api_simulada',
    }

    nuevo_estado = _estado_final_por_validaciones(bienes, entidad, aprobado)
    supabase.table(TABLA_DECLARACIONES).update({
        'bienes': bienes,
        'estado_revision': nuevo_estado,
    }).eq('codigo', row.get('codigo')).execute()

    resultado['estado_revision'] = nuevo_estado
    resultado['flujo_simulado'] = bienes.get('flujo_simulado', {})


def validar_pdi(payload: Dict[str, Any]) -> dict:
    row, datos, codigo = _payload_para_validar(payload or {})
    if codigo and not datos:
        return {
            'ok': False,
            'entidad': 'PDI',
            'aprobado': False,
            'estado': 'rechazado',
            'codigo_tramite': codigo,
            'motivos': ['No existe una declaracion guardada con ese codigo.'],
            'advertencias': [],
        }

    datos = datos or {}
    motivos: List[str] = []
    advertencias: List[str] = []

    nombre = _safe_str(datos.get('nombre'))
    apellido = _safe_str(datos.get('apellido'))
    correo = _safe_str(datos.get('correo'))
    pais = _safe_str(datos.get('pais_emisor') or datos.get('pais'))
    documento = _safe_str(datos.get('numero_documento') or datos.get('dni'))
    nacionalidad = _safe_str(datos.get('nacionalidad'))
    fecha_nacimiento = _safe_str(datos.get('fecha_nacimiento'))
    fecha_ingreso = _safe_str(datos.get('fecha_ingreso'))
    paso_fronterizo = _safe_str(datos.get('paso_fronterizo'))
    proposito = _normalizar_texto(datos.get('proposito_viaje') or datos.get('proposito'))

    if not nombre:
        motivos.append('Falta nombre del viajero.')
    if not apellido:
        motivos.append('Falta apellido del viajero.')
    if not correo or '@' not in correo:
        motivos.append('Correo invalido o ausente.')
    if not nacionalidad:
        motivos.append('Falta nacionalidad.')

    if documento:
        doc_ok, doc_msg = _validar_documento(pais, documento)
        if not doc_ok:
            motivos.append(doc_msg)
    else:
        motivos.append('Falta numero de documento del viajero.')

    if not fecha_nacimiento or not _es_mayor_de_edad(fecha_nacimiento):
        motivos.append('La persona responsable debe ser mayor de 18 anos y tener fecha de nacimiento valida.')

    if not fecha_ingreso or not _fecha_no_pasada(fecha_ingreso):
        motivos.append('La fecha estimada de ingreso debe ser valida y no pasada.')

    if not paso_fronterizo:
        motivos.append('Falta paso fronterizo.')
    elif _normalizar_texto(paso_fronterizo) not in PASOS_FRONTERIZOS_VALIDOS:
        advertencias.append('Paso fronterizo no coincide exactamente con Los Libertadores; se permite para demo si el resto del flujo es valido.')

    if proposito not in PROPOSITOS_VALIDOS:
        motivos.append('Proposito de viaje no valido. Debe ser turismo, negocios, carga o residencia.')

    motivos.extend(_validar_menores(datos))

    aprobado = len(motivos) == 0
    resultado = {
        'ok': True,
        'entidad': 'PDI',
        'aprobado': aprobado,
        'estado': 'aprobado' if aprobado else 'rechazado',
        'codigo_tramite': codigo or datos.get('codigo_tramite') or datos.get('codigo'),
        'motivos': motivos if motivos else ['Control PDI aprobado para simulacion.'],
        'advertencias': advertencias,
        'siguiente': 'validar_sag' if aprobado else 'corregir_datos_pdi',
    }

    if row:
        _actualizar_resultado_entidad(row, 'pdi', resultado)

    return resultado


def validar_sag(payload: Dict[str, Any]) -> dict:
    row, datos, codigo = _payload_para_validar(payload or {})
    if codigo and not datos:
        return {
            'ok': False,
            'entidad': 'SAG',
            'aprobado': False,
            'estado': 'rechazado',
            'codigo_tramite': codigo,
            'motivos': ['No existe una declaracion guardada con ese codigo.'],
            'advertencias': [],
        }

    datos = datos or {}
    motivos: List[str] = []
    advertencias: List[str] = []

    declara_productos = _bool_estricto(datos.get('declara_alimentos_animales_plantas') or datos.get('declara_productos'))
    detalle = _safe_str(datos.get('detalle_productos_sag') or datos.get('detalle_productos'))
    archivo = _safe_str(datos.get('archivo_sag_nombre') or datos.get('archivo_declaracion'))
    texto_detalle = _normalizar_texto(detalle)

    if declara_productos:
        if not detalle:
            motivos.append('Si declara SAG, debe detallar alimentos, animales, plantas o derivados.')
        if not archivo:
            advertencias.append('No se recibio nombre de documento SAG adjunto. Para demo se permite si el detalle es suficiente.')
        if any(item in texto_detalle for item in PRODUCTOS_SAG_RIESGO):
            motivos.append('Producto SAG de alto riesgo detectado. Requiere revision manual en esta simulacion.')
    else:
        if detalle and detalle.lower() not in {'no aplica', 'n/a', 'ninguno'}:
            advertencias.append('Existe detalle SAG, pero la declaracion esta marcada como No declaro.')

    aprobado = len(motivos) == 0
    resultado = {
        'ok': True,
        'entidad': 'SAG',
        'aprobado': aprobado,
        'estado': 'aprobado' if aprobado else 'rechazado',
        'codigo_tramite': codigo or datos.get('codigo_tramite') or datos.get('codigo'),
        'motivos': motivos if motivos else ['Control SAG aprobado para simulacion.'],
        'advertencias': advertencias,
        'siguiente': 'enviar_aduanas_app' if aprobado else 'corregir_declaracion_sag',
    }

    if row:
        _actualizar_resultado_entidad(row, 'sag', resultado)

    return resultado


def obtener_tramites_para_app(estado: Optional[str] = None, limite: int = 100) -> list:
    query = supabase.table(TABLA_DECLARACIONES).select('*').order('created_at', desc=True).limit(limite)
    if estado:
        query = query.eq('estado_revision', estado)
    resultado = query.execute()
    return [_normalizar_declaracion(row) for row in (resultado.data or [])]



# ============================================================================
# PUENTE PARA APP MOVIL DEL ADUANERO
# ============================================================================

ESTADOS_APP_ESPERA = {ESTADO_APROBADO_ENTIDADES}
ESTADOS_APP_DENEGADOS = {ESTADO_RECHAZADO_PDI, ESTADO_RECHAZADO_SAG}
ESTADOS_APP_HISTORIAL = {ESTADO_PASO_PAIS, 'historial_aduanas', 'pasado'}


def _rechazo_por_estado(estado_revision: str) -> str:
    estado = _normalizar_texto(estado_revision)
    if 'pdi' in estado:
        return 'PDI'
    if 'sag' in estado:
        return 'SAG'
    return ''


def _rechazo_por_validaciones(validaciones: Dict[str, Any], estado_revision: str) -> str:
    rechazadas: List[str] = []
    pdi = validaciones.get('pdi') or {}
    sag = validaciones.get('sag') or {}
    if pdi.get('aprobado') is False:
        rechazadas.append('PDI')
    if sag.get('aprobado') is False:
        rechazadas.append('SAG')
    if rechazadas:
        return ' y '.join(rechazadas)
    return _rechazo_por_estado(estado_revision)


def _resumen_personal_para_aduanero(declaracion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Devuelve solo los datos que necesita la app movil del aduanero:
    datos personales basicos, estado y documento de identidad.

    No expone detalle SAG, Aduanas, productos, animales, dinero ni carga.
    """
    bienes = declaracion.get('bienes') or {}
    validaciones = bienes.get('validaciones') or {}
    estado_revision = _safe_str(declaracion.get('estado_revision') or declaracion.get('estado'))
    rechazo_por = _rechazo_por_validaciones(validaciones, estado_revision)

    motivos_rechazo: List[str] = []
    for entidad_key in ('pdi', 'sag'):
        datos_entidad = validaciones.get(entidad_key) or {}
        if datos_entidad.get('aprobado') is False or entidad_key in _normalizar_texto(estado_revision):
            motivos = datos_entidad.get('motivos') or []
            if isinstance(motivos, list):
                motivos_rechazo.extend(_safe_str(m) for m in motivos if _safe_str(m))

    return {
        'codigo_tramite': _safe_str(declaracion.get('codigo_tramite') or declaracion.get('codigo')),
        'estado_revision': estado_revision,
        'fecha_creacion': _safe_str(declaracion.get('created_at') or declaracion.get('fecha_creacion')),
        'nombre': _safe_str(declaracion.get('nombre')),
        'apellido': _safe_str(declaracion.get('apellido')),
        'nombre_completo': _safe_str(declaracion.get('nombre_completo')) or f"{_safe_str(declaracion.get('nombre'))} {_safe_str(declaracion.get('apellido'))}".strip(),
        'correo': _safe_str(declaracion.get('correo')),
        'nacionalidad': _safe_str(declaracion.get('nacionalidad')),
        'fecha_nacimiento': _safe_str(declaracion.get('fecha_nacimiento')),
        'documento_identidad': {
            'tipo': _safe_str(declaracion.get('tipo_documento')) or 'Cedula de identidad',
            'pais_emisor': _safe_str(declaracion.get('pais_emisor') or declaracion.get('pais')),
            'numero': _safe_str(declaracion.get('numero_documento') or declaracion.get('dni')),
        },
        'rechazo_por': rechazo_por,
        'motivos_rechazo': motivos_rechazo,
    }


def obtener_tramites_aduanero(categoria: str, limite: int = 100) -> List[Dict[str, Any]]:
    """
    Categorias:
    - espera: aprobados por PDI y SAG, pendientes de pasar por Aduanas.
    - denegados: rechazados por PDI o SAG.
    - historial: viajeros ya marcados como pasaron el pais.
    """
    categoria_norm = _normalizar_texto(categoria)
    limite = max(1, min(int(limite or 100), 500))

    if categoria_norm in {'espera', 'en espera', 'pendientes'}:
        estados = ESTADOS_APP_ESPERA
    elif categoria_norm in {'denegados', 'rechazados'}:
        estados = ESTADOS_APP_DENEGADOS
    elif categoria_norm in {'historial', 'pasados'}:
        estados = ESTADOS_APP_HISTORIAL
    else:
        estados = ESTADOS_APP_ESPERA | ESTADOS_APP_DENEGADOS | ESTADOS_APP_HISTORIAL

    declaraciones: List[Dict[str, Any]] = []
    for estado in sorted(estados):
        resultado = (
            supabase
            .table(TABLA_DECLARACIONES)
            .select('*')
            .eq('estado_revision', estado)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
        )
        declaraciones.extend(_normalizar_declaracion(row) for row in (resultado.data or []))

    declaraciones.sort(key=lambda d: _safe_str(d.get('created_at') or d.get('fecha_creacion')), reverse=True)
    return [_resumen_personal_para_aduanero(d) for d in declaraciones[:limite]]


def obtener_tramite_aduanero(codigo_tramite: str) -> Dict[str, Any]:
    row = obtener_declaracion_raw(codigo_tramite)
    if not row:
        return {}
    return _resumen_personal_para_aduanero(_normalizar_declaracion(row))


def marcar_tramite_como_pasado(codigo_tramite: str) -> Dict[str, Any]:
    """Marca un tramite aprobado por PDI/SAG como ya pasado por Aduanas."""
    row = obtener_declaracion_raw(codigo_tramite)
    if not row:
        return {
            'ok': False,
            'mensaje': 'Tramite no encontrado.',
            'codigo_tramite': codigo_tramite,
        }

    estado_actual = _safe_str(row.get('estado_revision'))
    if estado_actual in ESTADOS_APP_DENEGADOS:
        return {
            'ok': False,
            'mensaje': 'No se puede marcar como pasado un tramite rechazado por PDI o SAG.',
            'codigo_tramite': codigo_tramite,
            'estado_actual': estado_actual,
        }

    if estado_actual not in ESTADOS_APP_ESPERA and estado_actual not in ESTADOS_APP_HISTORIAL:
        return {
            'ok': False,
            'mensaje': 'El tramite aun no esta aprobado por PDI y SAG.',
            'codigo_tramite': codigo_tramite,
            'estado_actual': estado_actual,
        }

    bienes = deepcopy(row.get('bienes') or {})
    bienes.setdefault('flujo_simulado', {})
    bienes['flujo_simulado']['aduanas'] = ESTADO_PASO_PAIS
    bienes['aduanero_app'] = {
        'estado': ESTADO_PASO_PAIS,
        'fecha_marcado': datetime.now().isoformat(timespec='seconds'),
        'accion': 'viajero_paso_pais',
        'operador': 'app_aduanero_sin_login',
    }

    supabase.table(TABLA_DECLARACIONES).update({
        'estado_revision': ESTADO_PASO_PAIS,
        'bienes': bienes,
    }).eq('codigo', codigo_tramite).execute()

    actualizado = obtener_tramite_aduanero(codigo_tramite)
    return {
        'ok': True,
        'mensaje': 'Tramite marcado como pasado por Aduanas.',
        'codigo_tramite': codigo_tramite,
        'estado_anterior': estado_actual,
        'estado_revision': ESTADO_PASO_PAIS,
        'tramite': actualizado,
    }

def obtener_resumen_validaciones(codigo_tramite: str) -> dict:
    row = obtener_declaracion_raw(codigo_tramite)
    if not row:
        return {'ok': False, 'mensaje': 'Tramite no encontrado', 'codigo_tramite': codigo_tramite}
    bienes = row.get('bienes') or {}
    return {
        'ok': True,
        'codigo_tramite': codigo_tramite,
        'estado_revision': row.get('estado_revision'),
        'flujo_simulado': bienes.get('flujo_simulado', {}),
        'validaciones': bienes.get('validaciones', {}),
        'datos': _normalizar_declaracion(row),
    }
