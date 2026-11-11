from odoo import api, fields, models

CLASE_FORMATO = [
    ('oficial', 'Formato oficial'),
    ('libre', 'Formato libre'),
    ('soporte', 'Soporte'),
    ('solo_portada', 'Solo portada'),
    ('no_se_elabora', 'No se elabora'),
    ('no_aplica', 'No aplica'),
]
QUIEN = [
    ('lexa', 'LEXA'),
    ('empresa', 'La empresa'),
    ('lexa_portada_empresa_anexa', 'LEXA portada · la empresa anexa'),
]
SEMAFORO_LEXA = [
    ('bloquea', '🛑 Falta dato o decisión'),
    ('confirmar', '🟡 Falta confirmación'),
    ('cerrado', '✅ Sin pendientes'),
    ('aviso', '➡️ Aviso'),
]
FIRMA = [
    ('representante_legal', 'Representante legal'),
    ('no_aplica', 'No aplica'),
    ('autografa_posterior', 'Autógrafa posterior'),
]
DICTAMEN = [
    ('sin_revisar', 'Sin revisar'),
    ('cumple', 'Cumple'),
    ('parcial', 'Cumple parcialmente'),
    ('no_cumple', 'No cumple'),
]


class StnLicitacionRequisito(models.Model):
    """Renglón de la matriz de cotejo de LEXA (amplía el requisito por licitación)."""
    _inherit = 'stn.licitacion.requisito'

    origen = fields.Selection(selection_add=[('lexa', 'LEXA')], ondelete={'lexa': 'set default'})
    casilla_id = fields.Many2one('stn.lexa.casilla', 'Casilla ComprasMX', ondelete='set null',
                                 domain="[('lead_id', '=', lead_id)]")
    subindice = fields.Integer('Subíndice', help='1.1, 1.2… cuando varios requisitos caen en la misma casilla.')
    anexo_formato = fields.Char('Anexo o formato', help='El anexo es el continente, no el requisito.')
    soportes = fields.Text('Soportes que manda acompañar', help='Nunca vacío: si no aplica, «ninguno».')
    causal_literal = fields.Text('Causal de desechamiento (literal)')
    huella = fields.Char('Huella', help='Frase única que debe aparecer en el PDF entregado.')
    fundamento = fields.Char('Fundamento (LAASSP / RLAASSP)')
    clase_formato = fields.Selection(CLASE_FORMATO, 'Clase de formato')
    quien_lo_hace = fields.Selection(QUIEN, 'Quién lo hace')
    pendiente = fields.Text('Información pendiente')
    lexa_semaforo = fields.Selection(SEMAFORO_LEXA, 'Semáforo LEXA')
    explicacion = fields.Char('Explicación en corto', help='En palabras llanas: «TE PREGUNTO:» o «YA DECIDISTE:».')
    firma_requerida = fields.Selection(FIRMA, 'Firma')
    evidencia = fields.Char('Evidencia (archivo y página)')
    junta_cambio = fields.Boolean('Cambiado por junta')
    junta_cambio_detalle = fields.Char('Qué cambió la junta')
    lexa_dictamen = fields.Selection(DICTAMEN, 'Revisión LEXA', default='sin_revisar', required=True)
    lexa_observacion = fields.Text('Observación de LEXA')
    lexa_fecha = fields.Datetime('Revisado por LEXA el', readonly=True)
    lexa_encargo_id = fields.Many2one('stn.lexa.encargo', 'Encargo de LEXA', readonly=True, ondelete='set null')

    @api.onchange('casilla_id', 'subindice')
    def _onchange_casilla(self):
        if self.casilla_id:
            self.pestana = self.casilla_id.pestana
            self.orden_casilla = '%s.%s' % (self.casilla_id.orden, self.subindice) if self.subindice \
                else str(self.casilla_id.orden)
