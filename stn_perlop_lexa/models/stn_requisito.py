from odoo import fields, models

LEGIBILIDAD = [('legible', 'Legible'), ('dudosa', 'Dudosa'), ('ilegible', 'Ilegible')]


class StnRequisito(models.Model):
    """Lo que LEXA lee dentro del documento maestro (no del nombre del archivo)."""
    _inherit = 'stn.requisito'

    lexa_rfc_leido = fields.Char('RFC leído por LEXA', readonly=True)
    lexa_fecha_emision_leida = fields.Date('Fecha de emisión leída', readonly=True,
                                           help='La que trae el documento por dentro; puede no coincidir con el nombre.')
    lexa_fecha_sello = fields.Date('Fecha del sello', readonly=True)
    lexa_folio = fields.Char('Folio / número', readonly=True)
    lexa_legibilidad = fields.Selection(LEGIBILIDAD, 'Legibilidad', readonly=True)
    lexa_contradiccion = fields.Text('Contradice lo declarado', readonly=True)
    lexa_observacion = fields.Text('Observación de LEXA', readonly=True)
    lexa_alerta = fields.Boolean('Alerta de LEXA', readonly=True,
                                 help='RFC de otra empresa, fecha distinta, documento dudoso o contradicción.')
    lexa_fecha_revision = fields.Datetime('Revisado por LEXA el', readonly=True)
