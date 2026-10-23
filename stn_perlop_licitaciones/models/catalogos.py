from odoo import api, fields, models

from .licia_parser import norm


class StnCatalogoMixin(models.AbstractModel):
    """Catálogo simple: nombre, código, secuencia, activo.

    `_stn_buscar_o_crear` resuelve los textos que manda LICIA comparando
    sin acentos/mayúsculas contra nombre, código y sinónimos.
    """
    _name = 'stn.catalogo.mixin'
    _description = 'Catálogo base STONES'
    _order = 'sequence, id'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', help='Clave técnica usada por la integración y las reglas del módulo.')
    sinonimos = fields.Char('Sinónimos', help='Textos alternos (separados por coma) con los que LICIA puede enviar este valor.')
    sequence = fields.Integer('Secuencia', default=10)
    active = fields.Boolean('Activo', default=True)

    @api.model
    def _stn_buscar_o_crear(self, valor, crear=True):
        if not valor:
            return self.browse()
        buscado = norm(valor)
        registros = self.with_context(active_test=False).search([])
        for rec in registros:
            candidatos = [rec.name, rec.code] + (rec.sinonimos or '').split(',')
            if any(norm(c) == buscado for c in candidatos if c):
                return rec
        for rec in registros:
            if norm(rec.name) and (buscado.startswith(norm(rec.name)) or norm(rec.name) in buscado):
                return rec
        if not crear:
            return self.browse()
        return self.create({'name': str(valor).strip().capitalize() if str(valor).isupper() else str(valor).strip()})


class StnLicitacionCriterio(models.Model):
    _name = 'stn.licitacion.criterio'
    _inherit = 'stn.catalogo.mixin'
    _description = 'Criterio de evaluación'


class StnLicitacionEstatus(models.Model):
    _name = 'stn.licitacion.estatus'
    _inherit = 'stn.catalogo.mixin'
    _description = 'Estatus del procedimiento (plataforma)'

    color = fields.Integer('Color')


class StnLicitacionTipoProcedimiento(models.Model):
    _name = 'stn.licitacion.tipo.procedimiento'
    _inherit = 'stn.catalogo.mixin'
    _description = 'Tipo de procedimiento'


class StnTipoServicio(models.Model):
    _name = 'stn.tipo.servicio'
    _inherit = 'stn.catalogo.mixin'
    _description = 'Tipo de servicio / segmento'


class StnRequisitoCategoria(models.Model):
    _name = 'stn.requisito.categoria'
    _inherit = 'stn.catalogo.mixin'
    _description = 'Categoría de requisitos'


class StnRequisitoEtapa(models.Model):
    _name = 'stn.requisito.etapa'
    _description = 'Etapa de requisito (semáforo)'
    _order = 'sequence, id'

    name = fields.Char('Nombre de la etapa', required=True)
    code = fields.Selection([
        ('en_tramite', 'En trámite'),
        ('vigente', 'Vigente'),
        ('proximo', 'Próximo a vencer'),
        ('vencido', 'Vencido'),
        ('sin_vencimiento', 'Sin vencimiento'),
    ], string='Código', required=True)
    sequence = fields.Integer('Secuencia', default=10)
    fold = fields.Boolean('Plegada en kanban')
