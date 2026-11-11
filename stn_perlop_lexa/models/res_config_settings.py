from odoo import api, fields, models

P = 'stn_lexa.'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    stn_lexa_activo = fields.Boolean('Integración con LEXA', config_parameter=P + 'activo')
    stn_lexa_token = fields.Char('Token de LEXA', config_parameter=P + 'token', groups='base.group_system')
    stn_lexa_modo = fields.Selection(
        [('cola', 'Cola: LEXA consulta los pendientes (LEXA en la Mac)'),
         ('rutina_api', 'Tarea de Claude: Odoo dispara a LEXA (LEXA en la nube)')],
        'Cómo recibe LEXA los encargos', config_parameter=P + 'modo', default='cola')
    stn_lexa_routine_url = fields.Char('URL del activador API (LEXA)', config_parameter=P + 'claude_routine_url')
    stn_lexa_routine_token = fields.Char('Token del activador API (LEXA)', config_parameter=P + 'claude_routine_token',
                                         groups='base.group_system')
    stn_lexa_beta = fields.Char('Encabezado anthropic-beta', config_parameter=P + 'claude_beta')
    stn_lexa_url_base = fields.Char('Dirección para LEXA', compute='_compute_stn_lexa_url_base')

    @api.depends('stn_lexa_activo')
    def _compute_stn_lexa_url_base(self):
        base = self.env['stn.lexa.service']._base_url()
        for s in self:
            s.stn_lexa_url_base = '%s/stn/lexa/' % base

    def action_stn_lexa_generar_token(self):
        self.env['stn.lexa.service']._generar_token()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
