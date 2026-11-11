from odoo import _, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def action_stn_crear_carpetas(self):
        self.ensure_one()
        empresas = self.stn_empresa_grupo_ids or self.env.company.stn_empresa_grupo_ids
        if not empresas:
            raise UserError(_('Primero elige las empresas del grupo que licitan.'))
        self.env.company.stn_empresa_grupo_ids = [(6, 0, empresas.ids)]
        carpetas = self.env['documents.document']._stn_crear_estructura(empresas)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Documentos'), 'type': 'success',
                           'message': _('Carpetas listas: %s (compartidas con el equipo de Licitaciones).',
                                        len(carpetas))}}
