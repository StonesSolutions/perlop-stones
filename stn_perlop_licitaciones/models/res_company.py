from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    stn_usuarios_nueva_ids = fields.Many2many(
        'res.users', 'stn_company_users_nueva_rel', 'company_id', 'user_id',
        string='Notificar nueva licitación')
    stn_usuarios_analisis_ids = fields.Many2many(
        'res.users', 'stn_company_users_analisis_rel', 'company_id', 'user_id',
        string='Notificar paso a análisis')
    stn_usuarios_gerencia_ids = fields.Many2many(
        'res.users', 'stn_company_users_gerencia_rel', 'company_id', 'user_id',
        string='Gerencia (escalamiento de vencidos)')
    stn_licia_estado_ids = fields.Many2many(
        'res.country.state', 'stn_company_state_rel', 'company_id', 'state_id',
        string='Estados donde operamos')
    stn_licia_tipo_servicio_ids = fields.Many2many(
        'stn.tipo.servicio', 'stn_company_tipo_servicio_rel', 'company_id', 'tipo_id',
        string='Segmentos de interés')
