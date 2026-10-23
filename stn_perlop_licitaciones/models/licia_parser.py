"""Normalización de valores de la ficha LICIA.

Funciones puras (sin ORM) para convertir los valores que genera LICIA
("N/A", "SI"/"NO", fechas AAAA-MM-DD HH:MM en hora local, montos sin
signo) a valores de Odoo. Se mantienen aquí para poder probarlas aislada.
"""
import re
import unicodedata
from datetime import datetime, date

import pytz

VACIOS = {'', 'n/a', 'na', 'n.a.', 'none', 'null', '-', '—', 'no aplica', 'sin dato'}

FICHA_VERSION = '1.0'


def norm(texto):
    """Minúsculas, sin acentos ni espacios dobles (para comparar)."""
    if texto is None:
        return ''
    texto = unicodedata.normalize('NFKD', str(texto))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', texto).strip().lower()


def es_vacio(valor):
    if valor is None or valor is False:
        return True
    if isinstance(valor, str) and norm(valor) in VACIOS:
        return True
    return False


def texto(valor):
    if es_vacio(valor):
        return False
    return str(valor).strip()


def booleano(valor):
    """SI/NO/True/False → bool; N/A → None (no tocar el campo)."""
    if isinstance(valor, bool):
        return valor
    if es_vacio(valor):
        return None
    v = norm(valor)
    if v in ('si', 'sí', 'yes', 'true', '1', 'x'):
        return True
    if v.startswith('si ') or v.startswith('si,') or v.startswith('si.'):
        return True
    if v in ('no', 'false', '0') or v.startswith('no ') or v.startswith('no,') or v.startswith('no.'):
        return False
    return None


def numero(valor):
    if es_vacio(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
    m = re.search(r'-?\d+(\.\d+)?', v)
    return float(m.group(0)) if m else None


def entero(valor):
    n = numero(valor)
    return int(n) if n is not None else None


_FORMATOS_FECHA = ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S',
                   '%Y-%m-%d', '%d/%m/%Y %H:%M', '%d/%m/%Y')


def _parse(valor):
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    v = str(valor).strip()
    v = re.sub(r'(Z|[+-]\d{2}:?\d{2})$', '', v)
    for fmt in _FORMATOS_FECHA:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    m = re.match(r'(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?', v)
    if m:
        return datetime.strptime(m.group(1) + ' ' + (m.group(2) or '00:00'), '%Y-%m-%d %H:%M')
    return None


def fecha_hora(valor, tz_name='America/Mexico_City'):
    """Fecha local de la ficha → datetime UTC naive (como guarda Odoo)."""
    if es_vacio(valor):
        return None
    dt = _parse(valor)
    if not dt:
        return None
    tz = pytz.timezone(tz_name or 'America/Mexico_City')
    return tz.localize(dt.replace(tzinfo=None)).astimezone(pytz.utc).replace(tzinfo=None)


def fecha(valor):
    if es_vacio(valor):
        return None
    dt = _parse(valor)
    return dt.date() if dt else None


def mapear(valor, tabla, defecto=False):
    """Busca la primera clave de `tabla` (lista de (patron, codigo)) contenida en el valor."""
    if es_vacio(valor):
        return defecto
    v = norm(valor)
    for patron, codigo in tabla:
        if len(patron) <= 3:
            if v == patron or re.match(r'^%s\b' % re.escape(patron), v):
                return codigo
        elif patron in v:
            return codigo
    return defecto


ACCION = [
    ('descart', 'descartar'),
    ('no perseguir', 'descartar'),
    ('no participar', 'descartar'),
    ('analizar', 'analizar'),
    ('perseguir (con condicion', 'perseguir_condicion'),
    ('con condicion', 'perseguir_condicion'),
    ('perseguir', 'perseguir'),
    ('en espera', 'en_espera'),
    ('vigilar', 'en_espera'),
]

CARACTER = [
    ('tratado', 'internacional_tratados'),
    ('internacional', 'internacional_abierta'),
    ('nacional', 'nacional'),
]

TIPO_REQUISITO = [
    ('legal', 'legal'),
    ('tecnic', 'tecnico'),
    ('econom', 'economico'),
    ('punto', 'puntos'),
    ('operativ', 'operativo'),
    ('forma', 'forma'),
    ('administ', 'legal'),
]

SITUACION = [
    ('no aplica', 'no_aplica'),
    ('tenemos', 'tenemos'),
    ('falta', 'conseguir'),
    ('conseguir', 'conseguir'),
    ('se genera', 'se_genera'),
    ('verificar', 'verificar'),
    ('listo', 'tenemos'),
]

PREGUNTA_ESTADO = [
    ('respond', 'respondida'),
    ('enviad', 'enviada'),
    ('descart', 'descartada'),
    ('sugerid', 'sugerida'),
]

PARTICIPAMOS = [
    ('por decidir', 'por_decidir'),
    ('si', 'si'),
    ('no', 'no'),
]

GANADA = [
    ('parcial', 'parcial'),
    ('si', 'si'),
    ('ganad', 'si'),
    ('no', 'no'),
    ('perdid', 'no'),
]

RESULTADO = [
    ('parcial', 'parcial'),
    ('desiert', 'desierta'),
    ('cancel', 'cancelada'),
    ('no particip', 'no_participada'),
    ('perd', 'perdida'),
    ('desech', 'perdida'),
    ('gan', 'ganada'),
    ('adjudic', 'ganada'),
]

EVENTO = [
    ('publicac', 'publicacion'),
    ('pregunta', 'limite_preguntas'),
    ('cierre', 'cierre_junta'),
    ('junta', 'junta'),
    ('aclarac', 'junta'),
    ('visita', 'visita'),
    ('muestra', 'muestras'),
    ('apertura', 'apertura'),
    ('presentac', 'apertura'),
    ('fallo', 'fallo'),
    ('firma', 'firma'),
    ('inicio', 'inicio_contrato'),
]

# Campos planos de fechas de la ficha → tipo de evento
FECHAS_EVENTO = [
    ('fecha_publicacion', 'publicacion'),
    ('fecha_limite_preguntas', 'limite_preguntas'),
    ('fecha_junta', 'junta'),
    ('fecha_cierre_junta', 'cierre_junta'),
    ('fecha_visita', 'visita'),
    ('fecha_muestras', 'muestras'),
    ('fecha_apertura', 'apertura'),
    ('fecha_fallo', 'fallo'),
    ('fecha_inicio_contrato', 'inicio_contrato'),
]

RE_UNIDAD_COMPRADORA = re.compile(r'^\s*(\d{3}[A-Z]{3}\d{3})\b\s*(.*)$')


def separar_unidad_compradora(valor):
    """'050GYR018 Jefatura de ...' → ('050GYR018', 'Jefatura de ...')."""
    v = texto(valor)
    if not v:
        return False, False
    m = RE_UNIDAD_COMPRADORA.match(v)
    if m:
        return m.group(1), (m.group(2).strip(' -·,') or m.group(1))
    return False, v


def parse_clave_valor(cuerpo):
    """Respaldo: lee el bloque 'clave: valor' del correo cuando no viene JSON."""
    datos = {}
    if not cuerpo:
        return datos
    actual = None
    for linea in cuerpo.splitlines():
        m = re.match(r'^\s*([a-z][a-z0-9_]{2,60})\s*:\s*(.*)$', linea)
        if m:
            actual = m.group(1)
            datos[actual] = m.group(2).strip()
        elif actual and linea.strip() and actual == 'url_ficha' and not datos[actual]:
            datos[actual] = linea.strip()
        elif actual and linea.strip() and not re.match(r'^\s*[A-Z]', linea) and actual in ('objeto', 'nombre_oportunidad', 'unidad_compradora'):
            datos[actual] = (datos[actual] + ' ' + linea.strip()).strip()
    return datos


# ----------------------------------------------------------------------
# Número de procedimiento (Anexo 7 del glosario Perlop)
#   LA-50-GYR-050GYR075-N-151-2026
#   L/I/A = licitación / invitación / adjudicación; A = LAASSP
#   50 = ramo, GYR = institución, 050GYR075 = unidad compradora,
#   N = carácter, 151 = consecutivo, 2026 = año
# ----------------------------------------------------------------------
RE_PROCEDIMIENTO = re.compile(
    r'^(?P<tipo>[LIA])(?P<ley>[A-Z])-(?P<ramo>[0-9A-Z]{2,3})-(?P<inst>[0-9A-Z]{2,4})-'
    r'(?P<uc>[0-9A-Z]{6,12})-(?P<caracter>[A-Z])-(?P<consecutivo>\d+)-(?P<anio>\d{4})$')

TIPO_POR_LETRA = {'L': 'LA', 'I': 'IA', 'A': 'AA'}
CARACTER_POR_LETRA = {'N': 'nacional', 'T': 'internacional_tratados', 'I': 'internacional_abierta',
                      'E': 'internacional_abierta'}


def leer_numero_procedimiento(numero):
    """Devuelve dict con tipo (código LA/IA/AA), carácter, clave de UC, ramo y año, o {}."""
    v = texto(numero)
    if not v:
        return {}
    m = RE_PROCEDIMIENTO.match(v.strip().upper())
    if not m:
        return {}
    return {
        'tipo_codigo': TIPO_POR_LETRA.get(m.group('tipo')),
        'caracter': CARACTER_POR_LETRA.get(m.group('caracter')),
        'uc': m.group('uc'),
        'ramo': m.group('ramo'),
        'institucion': m.group('inst'),
        'anio': int(m.group('anio')),
    }


def antiguedad_dias(valor):
    """'3 meses (desde 2026-07-15)' → 90; '30 días' → 30; 'menos de 6 meses' → 180."""
    if es_vacio(valor):
        return 0
    v = norm(valor)
    m = re.search(r'(\d+)\s*(mes|dia|semana|ano|año)', v)
    if not m:
        return 0
    n = int(m.group(1))
    unidad = m.group(2)
    return n * {'mes': 30, 'dia': 1, 'semana': 7, 'ano': 365, 'año': 365}[unidad]
