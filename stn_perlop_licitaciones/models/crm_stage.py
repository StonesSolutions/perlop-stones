from odoo import fields, models

CODIGOS_ETAPA = [
    ('nueva', 'Nueva (detectada)'),
    ('analisis', 'Análisis y decisión'),
    ('preparacion', 'Preparación técnica, legal y económica'),
    ('revision_ia', 'Revisión IA'),
    ('revision', 'Revisión'),
    ('presentada', 'Presentada en plataforma'),
    ('evaluacion', 'En evaluación'),
    ('ganado', 'Ganado'),
]

# Etapa → campo de fecha que se sella al entrar (seguimiento interno)
SELLO_ETAPA = {
    'analisis': 'stn_fecha_analisis',
    'preparacion': 'stn_fecha_aprobacion',
    'revision_ia': 'stn_fecha_propuesta_terminada',
    'revision': 'stn_fecha_revision',
    'presentada': 'stn_fecha_presentacion',
    'evaluacion': 'stn_fecha_evaluacion',
}


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    stn_codigo = fields.Selection(
        CODIGOS_ETAPA, string='Código de etapa (licitaciones)',
        help='Identifica la etapa para las reglas del módulo (botones, sellos de fecha, LICIA). '
             'Permite renombrar la etapa sin romper la lógica.')
