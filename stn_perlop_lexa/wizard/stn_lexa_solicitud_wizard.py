from odoo import _, fields, models
from odoo.exceptions import UserError


class StnLexaSolicitudWizard(models.TransientModel):
    _name = 'stn.lexa.solicitud.wizard'
    _description = 'Pedir trabajo a LEXA'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade')
    tipo = fields.Selection([('matriz', 'Armar la matriz de cotejo'),
                             ('revision', 'Revisar nuestros archivos (cumple / no cumple)')],
                            'Qué se le pide', required=True, default='revision')
    parte = fields.Selection([('legal', 'Legal-administrativa'), ('tecnica', 'Técnica'), ('ambas', 'Legal y técnica')],
                             'Parte', required=True, default='ambas')
    nota = fields.Text('Indicaciones para LEXA')
    modo = fields.Char(compute='_compute_modo')

    def _compute_modo(self):
        modo = self.env['ir.config_parameter'].sudo().get_param('stn_lexa.modo') or 'cola'
        for w in self:
            w.modo = modo

    def action_confirmar(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_param('stn_lexa.activo'):
            raise UserError(_('La integración con LEXA está apagada. Actívala en Ajustes › CRM › LEXA.'))
        partes = ['legal', 'tecnica'] if self.parte == 'ambas' else [self.parte]
        if self.tipo == 'revision':
            con_archivos = [p for p in partes if self.lead_id.stn_requisito_ids.filtered(
                lambda r, p=p: r.pestana == p and r.archivo_ids)]
            if not con_archivos:
                raise UserError(_('Para que LEXA revise, sube nuestros archivos en la pestaña Requerimientos '
                                  '(columna «Nuestros archivos») de la parte que quieres revisar.'))
            partes = con_archivos
        encargos = self.env['stn.lexa.service'].stn_solicitar(self.lead_id, self.tipo, partes, self.nota)
        modo = ICP.get_param('stn_lexa.modo') or 'cola'
        mensaje = _('LEXA ya recibió el encargo y está trabajando.') if modo == 'rutina_api' else \
            _('El encargo quedó en la cola de LEXA: lo toma en su siguiente revisión de pendientes.')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Encargo para LEXA'), 'message': '%s (%s)' % (mensaje, ', '.join(encargos.mapped('name'))),
                       'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}},
        }
