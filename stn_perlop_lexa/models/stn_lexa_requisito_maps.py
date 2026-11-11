"""Textos que LEXA puede mandar → valores de Odoo (se comparan sin acentos ni mayúsculas)."""

PARTE_MAP = [('legal', 'legal'), ('admin', 'legal'), ('tecnic', 'tecnica')]
PESTANA_MAP = [('legal', 'legal'), ('admin', 'legal'), ('tecnic', 'tecnica'), ('econom', 'economica')]
CLASE_MAP = [('oficial', 'oficial'), ('libre', 'libre'), ('solo_portada', 'solo_portada'),
             ('solo portada', 'solo_portada'), ('portada', 'solo_portada'), ('soporte', 'soporte'),
             ('no_se_elabora', 'no_se_elabora'), ('no se elabora', 'no_se_elabora'), ('no_aplica', 'no_aplica'),
             ('no aplica', 'no_aplica')]
QUIEN_MAP = [('lexa_portada_empresa_anexa', 'lexa_portada_empresa_anexa'), ('anexa', 'lexa_portada_empresa_anexa'),
             ('empresa', 'empresa'), ('lexa', 'lexa')]
SEMAFORO_MAP = [('bloquea', 'bloquea'), ('🛑', 'bloquea'), ('confirmar', 'confirmar'), ('🟡', 'confirmar'),
                ('cerrado', 'cerrado'), ('sin pendientes', 'cerrado'), ('✅', 'cerrado'), ('aviso', 'aviso'),
                ('➡', 'aviso')]
FIRMA_MAP = [('representante', 'representante_legal'), ('autografa', 'autografa_posterior'),
             ('no_aplica', 'no_aplica'), ('no aplica', 'no_aplica')]
DICTAMEN_MAP = [('no cumple', 'no_cumple'), ('no_cumple', 'no_cumple'), ('incumple', 'no_cumple'),
                ('parcial', 'parcial'), ('cumple', 'cumple'), ('ok', 'cumple')]
