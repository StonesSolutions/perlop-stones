from odoo import _, api, fields, models

ESTADO_FALTANTE = [
    ('abierto', 'Abierto'),
    ('en_tramite', 'En trámite'),
    ('resuelto', 'Resuelto'),
    ('no_aplica', 'No aplica'),
]


class StnLexaFaltante(models.Model):
    """Lo que LEXA no encontró, con dónde lo buscó (sin eso no se puede declarar «falta»)."""
    _name = 'stn.lexa.faltante'
    _description = 'Faltante de la proposición'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'desecha desc, fecha_limite, id'

    lead_id = fields.Many2one('crm.lead', 'Licitación', required=True, ondelete='cascade', index=True)
    encargo_id = fields.Many2one('stn.lexa.encargo', 'Encargo', ondelete='set null')
    requisito_id = fields.Many2one('stn.licitacion.requisito', 'Requisito', ondelete='set null',
                                   domain="[('lead_id', '=', lead_id)]")
    name = fields.Char('Documento', required=True)
    dato = fields.Char('Dato faltante', help='Visible en el documento como [FALTA: …].')
    donde_se_busco = fields.Text('Dónde se buscó')
    lugar = fields.Char('Lugar en el documento')
    consecuencia = fields.Text('Consecuencia')
    desecha = fields.Boolean('Desecha', help='Si desecha es bloqueante: se insiste antes de la apertura.')
    solicitado_a_id = fields.Many2one('res.users', 'Solicitado a', tracking=True)
    estado = fields.Selection(ESTADO_FALTANTE, 'Estado', default='abierto', required=True, tracking=True)
    fecha_limite = fields.Date('Fecha límite', tracking=True)
    origen = fields.Selection([('lexa', 'LEXA'), ('manual', 'Manual')], default='manual', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for f in recs:
            if not f.fecha_limite and f.lead_id.stn_fecha_limite_interna:
                f.fecha_limite = fields.Date.to_date(f.lead_id.stn_fecha_limite_interna)
            f._stn_avisar()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if 'solicitado_a_id' in vals:
            self._stn_avisar()
        return res

    def _stn_avisar(self):
        for f in self.filtered(lambda x: x.solicitado_a_id and x.estado in ('abierto', 'en_tramite')):
            resumen = _('Faltante: %s', f.name)
            if not f.lead_id.activity_ids.filtered(lambda a: a.summary == resumen and a.user_id == f.solicitado_a_id):
                f.lead_id.activity_schedule(
                    'mail.mail_activity_data_todo', summary=resumen, user_id=f.solicitado_a_id.id,
                    date_deadline=f.fecha_limite or fields.Date.context_today(f),
                    note=_('%(dato)s%(desecha)s', dato=f.dato or f.name,
                           desecha=_(' · DESECHA si falta') if f.desecha else ''))
