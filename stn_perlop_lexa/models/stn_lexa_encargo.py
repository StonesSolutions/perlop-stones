from odoo import _, api, fields, models
from odoo.exceptions import UserError

PARTE = [('legal', 'Legal-administrativa'), ('tecnica', 'Técnica')]
TIPO_ENCARGO = [('matriz', 'Armar matriz de cotejo'), ('revision', 'Revisar nuestros archivos')]
ESTADO_ENCARGO = [
    ('solicitado', 'Solicitado a LEXA'),
    ('en_proceso', 'LEXA trabajando'),
    ('matriz_lista', 'Matriz por aprobar'),
    ('aprobada', 'Matriz aprobada'),
    ('revisado', 'Revisado por LEXA'),
    ('requiere_regenerar', 'Requiere regenerar'),
    ('error', 'Error'),
    ('cancelado', 'Cancelado'),
]
GROUP_DIRECTORES = 'stn_perlop_licitaciones.group_licitaciones_director'


class StnLexaEncargo(models.Model):
    """Encargo de LEXA para una licitación: armar la matriz (legal o técnica) o revisar
    nuestros archivos. Llave: número de procedimiento + empresa + parte + versión de matriz."""
    _name = 'stn.lexa.encargo'
    _description = 'Encargo de LEXA'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Encargo', compute='_compute_name', store=True)
    lead_id = fields.Many2one('crm.lead', 'Licitación', required=True, ondelete='cascade', index=True)
    numero = fields.Char(related='lead_id.stn_no_procedimiento', string='No. de procedimiento', store=True)
    empresa = fields.Char('Empresa (según LEXA)', readonly=True)
    parte = fields.Selection(PARTE, 'Parte', required=True)
    tipo = fields.Selection(TIPO_ENCARGO, 'Tipo de encargo', required=True, default='matriz')
    version_matriz = fields.Integer('Versión de matriz', default=1)
    estado = fields.Selection(ESTADO_ENCARGO, 'Estado', default='solicitado', required=True, tracking=True)
    nota = fields.Text('Indicaciones para LEXA')
    solicitado_por = fields.Many2one('res.users', 'Solicitado por', default=lambda s: s.env.user, readonly=True)
    fecha_solicitud = fields.Datetime('Solicitado el', default=fields.Datetime.now, readonly=True)
    fecha_respuesta = fields.Datetime('Respuesta de LEXA', readonly=True)
    resumen = fields.Text('Resumen de LEXA', readonly=True)
    advertencias = fields.Text('Advertencias', readonly=True)
    matriz_attachment_id = fields.Many2one('ir.attachment', 'Matriz (archivo)', readonly=True, ondelete='set null')
    # Aprobación humana: LEXA nunca la escribe (la API no toca estos campos)
    matriz_aprobada_por = fields.Many2one('res.users', 'Matriz aprobada por', readonly=True, tracking=True)
    matriz_aprobada_fecha = fields.Datetime('Matriz aprobada el', readonly=True)
    revisados = fields.Integer('Revisados', readonly=True)
    cumplen = fields.Integer('Cumplen', readonly=True)
    no_cumplen = fields.Integer('No cumplen', readonly=True)
    parciales = fields.Integer('Parciales', readonly=True)
    payload = fields.Text('Último JSON de LEXA', readonly=True)
    sesion_url = fields.Char('Sesión de Claude', readonly=True)

    @api.depends('lead_id.stn_no_procedimiento', 'parte', 'tipo', 'version_matriz')
    def _compute_name(self):
        partes = dict(PARTE)
        for e in self:
            tipo = _('Matriz') if e.tipo == 'matriz' else _('Revisión')
            e.name = '%s · %s %s · v%s' % (e.lead_id.stn_no_procedimiento or e.lead_id.name or '', tipo,
                                           (partes.get(e.parte) or '').lower(), e.version_matriz)

    def write(self, vals):
        campos_aprobacion = {'matriz_aprobada_por', 'matriz_aprobada_fecha'} & set(vals)
        if campos_aprobacion and not self.env.context.get('stn_lexa_aprobando'):
            raise UserError(_('La aprobación de la matriz solo se marca con el botón «Aprobar matriz».'))
        return super().write(vals)

    def _stn_puede_aprobar(self):
        self.ensure_one()
        return self.env.user.has_group(GROUP_DIRECTORES) or self.env.user == self.lead_id.stn_lider_id \
            or self.env.su

    def action_aprobar_matriz(self):
        """Compuerta humana: sin matriz aprobada, LEXA no elabora ningún documento."""
        if self.env.context.get('stn_lexa_api'):
            raise UserError(_('La aprobación de la matriz la marca una persona en Odoo; LEXA nunca la escribe.'))
        for e in self:
            if e.tipo != 'matriz' or e.estado not in ('matriz_lista', 'requiere_regenerar'):
                raise UserError(_('Solo se aprueba una matriz que LEXA ya entregó («Matriz por aprobar»).'))
            if not e._stn_puede_aprobar():
                raise UserError(_('Aprueba la matriz el líder de proyecto o un Director de licitaciones.'))
            e.with_context(stn_lexa_aprobando=True).write({
                'estado': 'aprobada', 'matriz_aprobada_por': self.env.user.id,
                'matriz_aprobada_fecha': fields.Datetime.now()})
            resumen = _('Aprobar matriz de LEXA (%s)', dict(PARTE)[e.parte].lower())
            e.lead_id.activity_ids.filtered(lambda a: a.summary == resumen).action_feedback(
                feedback=_('Aprobada por %s', self.env.user.name))
            e.lead_id.message_post(
                body=_('Matriz de LEXA aprobada: %(enc)s, por %(user)s. LEXA ya puede elaborar los documentos.',
                       enc=e.name, user=self.env.user.name),
                message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    def action_devolver(self):
        """Pedir cambios a LEXA: nuevo encargo de matriz (versión siguiente) con indicaciones."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pedir cambios a LEXA'),
            'res_model': 'stn.lexa.solicitud.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_id': self.lead_id.id, 'default_tipo': 'matriz', 'default_parte': self.parte},
        }

    def action_cancelar(self):
        self.filtered(lambda e: e.estado in ('solicitado', 'en_proceso', 'error')).write({'estado': 'cancelado'})
        return True
