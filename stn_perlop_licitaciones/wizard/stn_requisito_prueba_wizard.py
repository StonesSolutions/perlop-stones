import io
import random

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# (xmlid de categoría, documento, días desde la emisión, vigencia en meses, días de trámite)
# Las fechas se calculan desde hoy para que el semáforo muestre todos los casos.
DOCUMENTOS_PRUEBA = [
    ('cat_constitucion', 'Acta constitutiva y reformas', 3650, 0, 0),
    ('cat_constitucion', 'Poder notarial del representante legal', 900, 0, 0),
    ('cat_constitucion', 'Identificación oficial del representante legal', 700, 120, 30),
    ('cat_legal', 'Constancia de situación fiscal', 12, 1, 3),
    ('cat_legal', 'Opinión de cumplimiento SAT (32-D)', 24, 1, 5),
    ('cat_legal', 'Opinión de cumplimiento IMSS', 40, 1, 5),
    ('cat_legal', 'Opinión de cumplimiento INFONAVIT', 8, 1, 5),
    ('cat_legal', 'Registro en el RUPC', 200, 12, 30),
    ('cat_sanitario', 'Aviso de funcionamiento COFEPRIS', 1500, 0, 0),
    ('cat_sanitario', 'Contrato de fumigación', 300, 12, 30),
    ('cat_sanitario', 'Certificado de fumigación del último mes', 50, 1, 5),
    ('cat_laboratorios', 'Análisis microbiológico de alimentos (EMA)', 60, 3, 15),
    ('cat_laboratorios', 'Estudios clínicos del personal (laboratorio EMA)', 100, 3, 15),
    ('cat_licencia_municipal', 'Licencia de funcionamiento municipal', 250, 12, 30),
    ('cat_licencia_municipal', 'Dictamen de protección civil', 340, 12, 45),
    ('cat_certificaciones', 'Certificado NMX-R-025 igualdad laboral', 400, 48, 60),
    ('cat_certificaciones', 'Distintivo H', 500, 24, 60),
    ('cat_seguros', 'Póliza de responsabilidad civil', 330, 12, 30),
    ('cat_vehiculos', 'Tarjetas de circulación de unidades refrigeradas', 180, 12, 30),
    ('cat_experiencia', 'Contrato IMSS Tamaulipas 2025 (experiencia)', 400, 0, 0),
    ('cat_experiencia', 'Carta de satisfacción IMSS Colima', 200, 0, 0),
    ('cat_personal', 'Constancias DC-3 de manejo higiénico de alimentos', 150, 12, 30),
]


class StnRequisitoPruebaWizard(models.TransientModel):
    """Carga documentos de prueba (PDF marcados «SIN VALIDEZ») para simular el contenido legal de una
    empresa: llenan el catálogo de vigencias y, con el módulo de Documentos, sus carpetas."""
    _name = 'stn.requisito.prueba.wizard'
    _description = 'Documentos de prueba de la empresa'

    empresa_id = fields.Many2one('res.partner', 'Empresa del grupo', required=True,
                                 default=lambda s: s.env.company.stn_empresa_grupo_ids[:1])
    cantidad = fields.Integer('Documentos', compute='_compute_cantidad')

    @api.depends('empresa_id')
    def _compute_cantidad(self):
        for w in self:
            w.cantidad = self.env['stn.requisito'].with_context(active_test=False).search_count(
                [('empresa_id', '=', w.empresa_id.id), ('es_prueba', '=', True)]) if w.empresa_id else 0

    @api.model
    def _pdf(self, empresa, nombre, emision, vencimiento, folio):
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        ancho, alto = letter
        c.saveState()
        c.setFillGray(0.88)
        c.setFont('Helvetica-Bold', 54)
        c.translate(ancho / 2, alto / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, 'DOCUMENTO DE PRUEBA')
        c.setFont('Helvetica-Bold', 30)
        c.drawCentredString(0, -50, 'SIN VALIDEZ OFICIAL')
        c.restoreState()
        c.setFont('Helvetica-Bold', 16)
        c.drawString(72, alto - 90, nombre)
        c.setFont('Helvetica', 11)
        filas = [
            ('Empresa', empresa.name),
            ('RFC', empresa.vat or 'XAXX010101000 (genérico de prueba)'),
            ('Folio', folio),
            ('Fecha de emisión', emision.strftime('%d/%m/%Y')),
            ('Vigente hasta', vencimiento.strftime('%d/%m/%Y') if vencimiento else 'Sin vencimiento'),
        ]
        y = alto - 130
        for etiqueta, valor in filas:
            c.drawString(72, y, '%s:' % etiqueta)
            c.drawString(200, y, str(valor))
            y -= 20
        c.setFont('Helvetica-Oblique', 9)
        c.drawString(72, 60, 'Generado por STONES para pruebas del CRM de Licitaciones. No usar en una proposición.')
        c.showPage()
        c.save()
        return buf.getvalue()

    def action_cargar(self):
        self.ensure_one()
        Req = self.env['stn.requisito']
        hoy = fields.Date.context_today(self)
        existentes = Req.with_context(active_test=False).search(
            [('empresa_id', '=', self.empresa_id.id), ('es_prueba', '=', True)]).mapped('name')
        creados = Req.browse()
        azar = random.Random(self.empresa_id.id)
        for xmlid, nombre, dias, meses, tramite in DOCUMENTOS_PRUEBA:
            if nombre in existentes:
                continue
            categoria = self.env.ref('stn_perlop_licitaciones.%s' % xmlid, raise_if_not_found=False)
            emision = hoy - relativedelta(days=dias)
            vence = emision + relativedelta(months=meses) if meses else False
            rec = Req.create({
                'name': nombre, 'empresa_id': self.empresa_id.id, 'categoria_id': categoria.id if categoria else False,
                'fecha_emision': emision, 'vigencia_meses': meses, 'dias_tramite': tramite, 'es_prueba': True,
            })
            folio = 'PRUEBA-%s-%04d' % (hoy.year, azar.randint(1, 9999))
            rec._stn_guardar_archivo('%s.pdf' % nombre, self._pdf(self.empresa_id, nombre, emision, vence, folio))
            creados |= rec
        creados.action_stn_actualizar_semaforo()
        return self._notificar(_('Se cargaron %(n)s documentos de prueba de %(e)s.', n=len(creados),
                                 e=self.empresa_id.name))

    def action_quitar(self):
        self.ensure_one()
        recs = self.env['stn.requisito'].with_context(active_test=False).search(
            [('empresa_id', '=', self.empresa_id.id), ('es_prueba', '=', True)])
        if recs.linea_ids:
            recs.linea_ids.write({'requisito_id': False})
        n = len(recs)
        recs._stn_quitar_archivos_prueba()
        recs.unlink()
        return self._notificar(_('Se quitaron %(n)s documentos de prueba de %(e)s.', n=n, e=self.empresa_id.name))

    def _notificar(self, mensaje):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Documentos de prueba'), 'message': mensaje, 'type': 'success',
                           'next': {'type': 'ir.actions.act_window_close'}}}
