from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StnRequisito(models.Model):
    """El archivo del documento maestro vive en Documentos (fuente única)."""
    _inherit = 'stn.requisito'

    documento_id = fields.Many2one('documents.document', 'Archivo en Documentos', ondelete='set null', tracking=True,
                                   domain="[('type', '!=', 'folder')]")

    def _stn_archivos(self):
        archivos = self.mapped('documento_id.attachment_id')
        return archivos | super()._stn_archivos()

    @api.model
    def _stn_buscar_por_archivo(self, attachment):
        return self.with_context(active_test=False).search(
            ['|', ('documento_id.attachment_id', 'in', attachment.ids), ('attachment_ids', 'in', attachment.ids)])

    def _stn_guardar_archivo(self, nombre, datos, mimetype='application/pdf'):
        """El archivo se guarda en la carpeta Documentos de la empresa y categoría."""
        self.ensure_one()
        if not self.empresa_id:
            return super()._stn_guardar_archivo(nombre, datos, mimetype)
        Doc = self.env['documents.document'].sudo()
        carpeta = Doc._stn_carpeta_categoria(self.empresa_id, self.categoria_id)
        att = self.env['ir.attachment'].sudo().create({'name': nombre, 'raw': datos, 'mimetype': mimetype})
        doc = Doc.with_context(stn_sin_catalogo=True).create(Doc._stn_vals({
            'name': nombre, 'type': 'binary', 'folder_id': carpeta.id, 'attachment_id': att.id,
        }))
        self.documento_id = doc
        return att

    def _stn_quitar_archivos_prueba(self):
        docs = self.mapped('documento_id').sudo()
        super()._stn_quitar_archivos_prueba()
        docs.unlink()

    def action_stn_abrir_documento(self):
        self.ensure_one()
        if not self.documento_id:
            raise UserError(_('Este documento no tiene archivo en Documentos.'))
        return {'type': 'ir.actions.act_window', 'res_model': 'documents.document', 'res_id': self.documento_id.id,
                'view_mode': 'form', 'target': 'current'}

    def action_stn_abrir_carpeta(self):
        self.ensure_one()
        if not self.empresa_id:
            raise UserError(_('Asigna la empresa del grupo para saber en qué carpeta va.'))
        carpeta = self.env['documents.document']._stn_carpeta_categoria(self.empresa_id, self.categoria_id)
        return {'type': 'ir.actions.act_window', 'name': carpeta.name, 'res_model': 'documents.document',
                'view_mode': 'list,form', 'domain': [('folder_id', '=', carpeta.id)],
                'context': {'default_folder_id': carpeta.id}}
