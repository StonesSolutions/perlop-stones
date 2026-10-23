from odoo import fields, models


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    stn_es_licitacion = fields.Boolean(
        'Equipo de licitaciones',
        help='Las oportunidades de este equipo muestran las pestañas y campos de licitación.')
