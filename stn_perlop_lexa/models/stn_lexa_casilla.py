from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.stn_perlop_licitaciones.models.crm_lead_lines import PESTANA

ESTADO_CASILLA = [
    ('pendiente', 'Pendiente'),
    ('generado', 'Generado'),
    ('verificado', 'Verificado'),
    ('foliado', 'Foliado'),
    ('subido', 'Subido a ComprasMX'),
]


class StnLexaCasilla(models.Model):
    """Casilla de «Mi proposición» en ComprasMX: dónde se sube cada archivo.

    El orden de las casillas define el nombre del archivo de subida (1.pdf, 2.pdf…) y el
    orden de la matriz. «Subido» solo lo marca una persona.
    """
    _name = 'stn.lexa.casilla'
    _description = 'Casilla de ComprasMX'
    _order = 'lead_id, pestana, orden, id'

    lead_id = fields.Many2one('crm.lead', 'Licitación', required=True, ondelete='cascade', index=True)
    pestana = fields.Selection(PESTANA, 'Pestaña', required=True)
    orden = fields.Integer('Orden', required=True)
    name = fields.Char('Nombre exacto', required=True, help='Tal cual aparece en el pantallazo; va en la portada.')
    obligatoria = fields.Boolean('Obligatoria', default=True)
    estado = fields.Selection(ESTADO_CASILLA, 'Estado', default='pendiente', required=True)
    attachment_id = fields.Many2one('ir.attachment', 'Archivo de subida', ondelete='set null')
    requisito_ids = fields.One2many('stn.licitacion.requisito', 'casilla_id', 'Requisitos')
    requisitos_count = fields.Integer('# Requisitos', compute='_compute_requisitos_count')
    origen = fields.Selection([('lexa', 'LEXA'), ('manual', 'Manual')], default='manual', readonly=True)
    subido_por = fields.Many2one('res.users', 'Subido por', readonly=True)
    subido_fecha = fields.Datetime('Subido el', readonly=True)

    _orden_unico = models.Constraint('UNIQUE(lead_id, pestana, orden)',
                                     'Ya existe una casilla con ese orden en esa pestaña.')

    def _compute_requisitos_count(self):
        for c in self:
            c.requisitos_count = len(c.requisito_ids)

    @api.depends('orden', 'name')
    def _compute_display_name(self):
        for c in self:
            c.display_name = '%s · %s' % (c.orden, c.name or '')

    def write(self, vals):
        if vals.get('estado') == 'subido' and self.env.context.get('stn_lexa_api'):
            vals = {k: v for k, v in vals.items() if k != 'estado'}  # LEXA nunca marca «subido»
        return super().write(vals)

    def action_marcar_subido(self):
        if self.env.context.get('stn_lexa_api'):
            raise UserError(_('«Subido a ComprasMX» solo lo marca una persona.'))
        sin_pdf = self.filtered(lambda c: c.obligatoria and not c.attachment_id)
        if sin_pdf:
            raise UserError(_('Ninguna casilla obligatoria se entrega sin PDF: %s', ', '.join(sin_pdf.mapped('display_name'))))
        self.write({'estado': 'subido', 'subido_por': self.env.user.id, 'subido_fecha': fields.Datetime.now()})
        return True
