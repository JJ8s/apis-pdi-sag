import logging
import os
from typing import Any, List

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '').strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        'Faltan SUPABASE_URL o SUPABASE_KEY. '
        'Configúralas en un archivo .env local o en las variables de entorno de Render.'
    )

logger.info('Inicializando cliente Supabase: %s', SUPABASE_URL)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def obtener_usuarios(limite: int = 50) -> List[dict[str, Any]]:
    """Consulta simple usada por test_supabase.py para verificar conexión."""
    try:
        resultado = supabase.table('usuarios').select('id,nombre,correo,rol').limit(limite).execute()
        return resultado.data or []
    except Exception as exc:
        logger.error('Error obteniendo usuarios desde Supabase: %s', exc)
        return []
