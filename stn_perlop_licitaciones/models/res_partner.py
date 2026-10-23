from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    stn_es_convocante = fields.Boolean('Dependencia convocante / unidad compradora')
    stn_es_competidor = fields.Boolean('Competidor en licitaciones')
    stn_competidor_ids = fields.One2many('stn.licitacion.competidor', 'partner_id', 'Participaciones como competidor')
