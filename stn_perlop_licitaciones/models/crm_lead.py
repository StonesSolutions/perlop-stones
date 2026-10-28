import base64
import json
import logging

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import licia_parser as P
from .crm_stage import SELLO_ETAPA

_logger = logging.getLogger(__name__)

GROUP_DIRECTORES = 'stn_perlop_licitaciones.group_licitaciones_director'

VIABILIDAD = [
    ('0', 'Nivel 0 · No viable'),
    ('1', 'Nivel 1 · Poco viable'),
    ('2', 'Nivel 2 · Medianamente viable'),
    ('3', 'Nivel 3 · Viable'),
    ('4', 'Nivel 4 · Muy viable'),
    ('5', 'Nivel 5 · Completamente viable'),
]

ACCION = [
    ('perseguir', 'Perseguir'),
    ('perseguir_condicion', 'Perseguir con condición'),
    ('analizar', 'Analizar'),
    ('en_espera', 'En espera'),
    ('descartar', 'No participar por ahora'),
]

RESULTADO = [
    ('pendiente', 'Pendiente'),
    ('ganada', 'Ganada'),
    ('parcial', 'Ganada parcialmente'),
    ('perdida', 'Perdida'),
    ('desierta', 'Desierta'),
    ('cancelada', 'Cancelada'),
    ('no_participada', 'No participada'),
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    stn_es_licitacion = fields.Boolean(related='team_id.stn_es_licitacion', string='Es licitación')
    stn_can_move_stage = fields.Boolean('Puede mover etapa', compute='_compute_stn_can_move_stage')
    stn_stage_codigo = fields.Selection(related='stage_id.stn_codigo', string='Código de etapa')

    # ------------------------------------------------------------------
    # Identificación (Studio: no. procedimiento, objeto, criterio, estatus)
    # ------------------------------------------------------------------
    stn_no_procedimiento = fields.Char('No. de procedimiento', index=True, tracking=True, copy=False)
    stn_plataforma = fields.Selection([('comprasmx', 'ComprasMX'), ('cfe', 'Plataforma CFE'),
                                       ('compranet', 'CompraNet (histórico)'),
                                       ('estatal', 'Portal estatal'), ('otra', 'Otra')],
                                      'Plataforma', default='comprasmx')
    stn_folio_plataforma = fields.Char(
        'Folio de la plataforma', help='Folio del expediente en ComprasMX (2026-A-L-NAC-…). No es el número '
                                      'de procedimiento ni el de contrato.')
    stn_plaza = fields.Char('Plaza', help='Ciudad o sede donde se presta el servicio.')
    stn_url_ficha = fields.Char('URL de la ficha')
    stn_objeto = fields.Text('Objeto')
    stn_tipo_procedimiento_id = fields.Many2one('stn.licitacion.tipo.procedimiento', 'Tipo de procedimiento',
                                                tracking=True)
    stn_tipo_procedimiento_detalle = fields.Char('Tipo (fundamento)')
    stn_modalidad = fields.Selection([('electronica', 'Electrónica'), ('presencial', 'Presencial'),
                                      ('mixta', 'Mixta')], 'Modalidad')
    stn_empresa_licitante_id = fields.Many2one(
        'res.partner', 'Empresa del grupo que licita', domain=[('is_company', '=', True)],
        default=lambda s: s.env.company.partner_id,
        help='PERLOP, JADE o JD. Permite filtrar el embudo por empresa mientras se define la multiempresa.')
    stn_modo_participacion = fields.Selection([('individual', 'Individual'), ('conjunta', 'Conjunta'),
                                               ('consorcio', 'Consorcio')], 'Modo de participación',
                                              help='Se decide al aprobar la participación.')
    stn_caracter = fields.Selection([('nacional', 'Nacional'), ('internacional_abierta', 'Internacional abierta'),
                                     ('internacional_tratados', 'Internacional bajo tratados')], 'Carácter')
    stn_criterio_id = fields.Many2one('stn.licitacion.criterio', 'Criterio de evaluación', tracking=True)
    stn_criterio_detalle = fields.Char('Criterio (detalle)')
    stn_minimo_tecnico = fields.Float('Mínimo técnico (puntos)')
    stn_estatus_id = fields.Many2one('stn.licitacion.estatus', 'Estatus del procedimiento', tracking=True)
    stn_tipo_servicio_id = fields.Many2one('stn.tipo.servicio', 'Tipo de servicio', tracking=True)
    stn_cucop = fields.Char('CUCoP')
    stn_cliente_nuevo = fields.Boolean('Cliente nuevo')

    # Convocante / unidad compradora (partner_id = unidad compradora)
    stn_dependencia_id = fields.Many2one('res.partner', 'Dependencia / entidad', tracking=True,
                                         help='Cliente (IMSS, IMSS-Bienestar, ISSSTE, ASA, CFE…).')
    stn_convocante_id = fields.Many2one('res.partner', 'Convocante (OOAD / área)', tracking=True)
    stn_unidad_compradora_clave = fields.Char('Clave unidad compradora')
    stn_area_requirente = fields.Char('Área requirente')
    stn_operamos_estado = fields.Boolean('Operamos en el estado')

    # ------------------------------------------------------------------
    # Montos y contrato
    # ------------------------------------------------------------------
    stn_monto_minimo = fields.Monetary('Monto mínimo (sin IVA)', currency_field='company_currency', tracking=True)
    stn_monto_maximo = fields.Monetary('Monto máximo (sin IVA)', currency_field='company_currency', tracking=True)
    stn_monto_minimo_estimado = fields.Monetary('Mínimo estimado', currency_field='company_currency',
                                                help='Estimación de LICIA cuando la convocatoria no publica montos (hipótesis).')
    stn_monto_maximo_estimado = fields.Monetary('Máximo estimado', currency_field='company_currency',
                                                help='Estimación de LICIA cuando la convocatoria no publica montos (hipótesis).')
    stn_condiciones_entrega = fields.Text('Condiciones de entrega')
    stn_nota_montos = fields.Text('Nota de montos')
    stn_vigencia_inicio = fields.Date('Vigencia del contrato desde')
    stn_vigencia_fin = fields.Date('Vigencia del contrato hasta')
    stn_garantia_pct = fields.Float('Garantía de cumplimiento (%)')
    stn_conjunta_permitida = fields.Boolean('Propuesta conjunta permitida')

    # ------------------------------------------------------------------
    # Lectura de LICIA
    # ------------------------------------------------------------------
    stn_viabilidad = fields.Selection(VIABILIDAD, 'Viabilidad (nivel LICIA)', tracking=True)
    stn_accion = fields.Selection(ACCION, 'Acción recomendada', tracking=True)
    stn_accion_detalle = fields.Char('Acción (detalle)')
    stn_lectura = fields.Text('Lectura de una línea')
    stn_razon_nivel = fields.Text('Por qué este nivel')
    stn_junta_aplica = fields.Boolean('Hay junta de aclaraciones')
    stn_aclaraciones = fields.Char('Medio y plazo de aclaraciones')
    stn_acta_aclaraciones = fields.Text('Acta de aclaraciones')
    stn_logistica_nota = fields.Text('Logística (resumen)')
    stn_carpeta = fields.Char('Carpeta de documentos')
    stn_licia_version = fields.Char('Versión de ficha', readonly=True)
    stn_licia_corte = fields.Char('Corte de la ficha', readonly=True)
    stn_licia_ultima_sync = fields.Datetime('Última actualización LICIA', readonly=True)
    stn_fechas_verificadas = fields.Datetime('Fechas verificadas en la ficha', readonly=True,
                                             help='Última vez que LICIA verificó las fechas en la ficha del procedimiento.')
    stn_proximo_evento = fields.Char('Cuenta regresiva', compute='_compute_stn_proximo_evento')
    stn_licia_payload = fields.Text('Último JSON recibido', readonly=True)

    # Archivo de requisitos (Studio)
    stn_requisitos_file = fields.Binary('Requisitos (archivo)', attachment=True)
    stn_requisitos_filename = fields.Char('Nombre del archivo de requisitos')
    stn_documento_ids = fields.Many2many(
        'ir.attachment', 'stn_lead_documento_rel', 'lead_id', 'attachment_id',
        string='Documentos de la convocatoria',
        help='Convocatoria, anexos, términos de referencia y actas. LICIA los descarga desde Odoo para analizarlos.')
    stn_documentos_count = fields.Integer('# Documentos', compute='_compute_stn_documentos_count')
    stn_analisis_estado = fields.Selection([
        ('sin_solicitar', 'Sin solicitar'),
        ('solicitado', 'Enviado a LICIA'),
        ('completado', 'Analizado por LICIA'),
        ('error', 'Error en el análisis'),
    ], 'Análisis de documentos', default='sin_solicitar', tracking=True, copy=False)
    stn_analisis_fecha = fields.Datetime('Último análisis solicitado', readonly=True, copy=False)
    stn_analisis_sesion = fields.Char('Sesión de Claude', readonly=True, copy=False)
    stn_analisis_mensaje = fields.Text('Mensaje del análisis', readonly=True, copy=False)
    stn_acta_fallo = fields.Binary('Acta de fallo', attachment=True)
    stn_acta_fallo_filename = fields.Char('Nombre del acta de fallo')
    stn_propuesta_economica = fields.Binary('Propuesta económica', attachment=True)
    stn_propuesta_economica_filename = fields.Char('Nombre de la propuesta económica')
    stn_requiere_rc = fields.Boolean('Exige póliza de responsabilidad civil')

    # ------------------------------------------------------------------
    # Fechas del procedimiento
    # ------------------------------------------------------------------
    stn_fecha_deteccion = fields.Datetime('Detectada')
    stn_fecha_publicacion = fields.Datetime('Publicación')
    stn_fecha_limite_preguntas = fields.Datetime('Límite de aclaraciones', tracking=True)
    stn_fecha_junta = fields.Datetime('Junta de aclaraciones', tracking=True)
    stn_fecha_apertura = fields.Datetime('Apertura de proposiciones', tracking=True)
    stn_fecha_limite_interna = fields.Datetime('Límite interno (propuesta lista)', tracking=True)
    stn_fecha_fallo = fields.Datetime('Fallo', tracking=True)
    stn_fecha_inicio_contrato = fields.Datetime('Inicio del contrato')
    # Sellos de seguimiento interno (al entrar a cada etapa)
    stn_fecha_analisis = fields.Datetime('Entró a análisis', readonly=True, copy=False)
    stn_fecha_aprobacion = fields.Datetime('Aprobación interna', copy=False)
    stn_fecha_propuesta_terminada = fields.Datetime('Propuesta terminada', copy=False)
    stn_fecha_revision = fields.Datetime('Revisión de propuesta', copy=False)
    stn_fecha_presentacion = fields.Datetime('Presentada en plataforma', copy=False)
    stn_fecha_evaluacion = fields.Datetime('Entró a evaluación', readonly=True, copy=False)
    stn_dias_reaccion = fields.Float('Días detección → aprobación', compute='_compute_stn_tiempos', store=True,
                                     aggregator='avg')
    stn_dias_disponibles = fields.Float('Días aprobación → límite interno', compute='_compute_stn_tiempos',
                                        store=True, aggregator='avg')
    stn_dias_preparacion = fields.Float('Días aprobación → presentación', compute='_compute_stn_tiempos',
                                        store=True, aggregator='avg')

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------
    stn_resultado = fields.Selection(RESULTADO, 'Resultado', default='pendiente', tracking=True)
    stn_apertura_celebrada = fields.Boolean('Apertura celebrada')
    stn_lugar_precios = fields.Char('Lugar en precios')
    stn_fallo_texto = fields.Char('Fallo (texto)')
    stn_causa_literal = fields.Text('Causa literal (acta)')
    stn_monto_adjudicado = fields.Monetary('Monto adjudicado', currency_field='company_currency',
                                           compute='_compute_stn_montos', store=True)
    stn_partidas_count = fields.Integer('# Partidas', compute='_compute_stn_montos', store=True)
    stn_partidas_ganadas = fields.Integer('Partidas ganadas', compute='_compute_stn_montos', store=True)

    # ------------------------------------------------------------------
    # Tablas
    # ------------------------------------------------------------------
    stn_evento_ids = fields.One2many('stn.licitacion.evento', 'lead_id', 'Eventos')
    stn_cambio_ids = fields.One2many('stn.licitacion.cambio', 'lead_id', 'Historial de cambios')
    stn_pregunta_ids = fields.One2many('stn.licitacion.pregunta', 'lead_id', 'Preguntas de aclaración')
    stn_partida_ids = fields.One2many('stn.licitacion.partida', 'lead_id', 'Partidas')
    stn_sede_ids = fields.One2many('stn.licitacion.sede', 'lead_id', 'Sedes y logística')
    stn_renglon_ids = fields.One2many('stn.licitacion.renglon', 'lead_id', 'Renglones')
    stn_requisito_ids = fields.One2many('stn.licitacion.requisito', 'lead_id', 'Requerimientos de la licitación')
    stn_punto_ids = fields.One2many('stn.licitacion.punto', 'lead_id', 'Puntos')
    stn_antecedente_ids = fields.One2many('stn.licitacion.antecedente', 'lead_id', 'Antecedentes')
    stn_competidor_ids = fields.One2many('stn.licitacion.competidor', 'lead_id', 'Competidores')
    stn_pendiente_ids = fields.One2many('stn.licitacion.pendiente', 'lead_id', 'Pendientes post-fallo')
    stn_seguimiento_ids = fields.One2many('stn.licitacion.seguimiento', 'lead_id', 'Seguimiento diario')
    stn_log_ids = fields.One2many('stn.licia.log', 'lead_id', 'Bitácora de integración')

    stn_requisitos_faltantes = fields.Integer('Requisitos por conseguir', compute='_compute_stn_requisitos',
                                              store=True)
    stn_requisitos_desechan = fields.Integer('Faltantes que desechan', compute='_compute_stn_requisitos',
                                             store=True)
    stn_puntos_maximos = fields.Float('Puntos técnicos posibles', compute='_compute_stn_puntos', store=True)

    _stn_no_procedimiento_uniq = models.Constraint(
        'UNIQUE(stn_no_procedimiento, company_id)',
        'Ya existe una licitación con ese número de procedimiento.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends_context('uid')
    def _compute_stn_can_move_stage(self):
        allowed = self._stn_user_can_move_stage()
        for lead in self:
            lead.stn_can_move_stage = allowed

    @api.depends('stn_fecha_deteccion', 'stn_fecha_aprobacion', 'stn_fecha_limite_interna', 'stn_fecha_presentacion')
    def _compute_stn_tiempos(self):
        def dias(a, b):
            return round((b - a).total_seconds() / 86400.0, 2) if a and b else 0.0
        for lead in self:
            lead.stn_dias_reaccion = dias(lead.stn_fecha_deteccion, lead.stn_fecha_aprobacion)
            lead.stn_dias_disponibles = dias(lead.stn_fecha_aprobacion, lead.stn_fecha_limite_interna)
            lead.stn_dias_preparacion = dias(lead.stn_fecha_aprobacion, lead.stn_fecha_presentacion)

    @api.depends('stn_documento_ids')
    def _compute_stn_documentos_count(self):
        for lead in self:
            lead.stn_documentos_count = len(lead.stn_documento_ids)

    def action_stn_analizar_licia(self):
        """Pide a LICIA analizar los documentos subidos y completar la ficha."""
        for lead in self:
            if not lead.stn_no_procedimiento:
                raise UserError(_('Captura el número de procedimiento antes de pedir el análisis.'))
            if not lead.stn_documento_ids:
                raise UserError(_('Sube primero la convocatoria y los anexos en la pestaña «Documentos».'))
            base = self.env['stn.licia.service']._base_url()
            texto = '\n'.join([
                'ANALIZAR_PROCEDIMIENTO %s' % lead.stn_no_procedimiento,
                'DOCUMENTOS %s/stn/licitaciones/documentos?numero=%s' % (base, lead.stn_no_procedimiento),
                'SOLICITADO_POR %s' % self.env.user.name,
            ])
            res = self.env['stn.licia.service'].stn_disparar_rutina(manual=True, texto=texto)
            sesion = res.get('claude_code_session_url') if isinstance(res, dict) else ''
            lead.write({'stn_analisis_estado': 'solicitado', 'stn_analisis_fecha': fields.Datetime.now(),
                        'stn_analisis_sesion': sesion or False, 'stn_analisis_mensaje': False})
            lead.message_post(body=_('Se pidió a LICIA analizar %(n)s documento(s). %(s)s',
                                     n=len(lead.stn_documento_ids), s=sesion or ''),
                              message_type='comment', subtype_xmlid='mail.mt_note')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('LICIA'), 'type': 'success',
                       'message': _('Análisis solicitado. La ficha se actualizará sola en unos minutos.')},
        }

    def action_stn_marcar_analisis_pendiente(self):
        """Sin activador API: deja la solicitud para la siguiente corrida diaria de LICIA."""
        for lead in self:
            if not lead.stn_documento_ids:
                raise UserError(_('Sube primero la convocatoria y los anexos en la pestaña «Documentos».'))
            lead.write({'stn_analisis_estado': 'solicitado', 'stn_analisis_fecha': fields.Datetime.now()})
        return True

    @api.depends('stn_evento_ids.fecha_oficial', 'stn_evento_ids.aplica', 'stn_fechas_verificadas')
    def _compute_stn_proximo_evento(self):
        ahora = fields.Datetime.now()
        hoy = fields.Date.context_today(self)
        etiquetas = dict(self.env['stn.licitacion.evento']._fields['tipo'].selection)
        for lead in self:
            prox = lead.stn_evento_ids.filtered(lambda e: e.aplica and e.fecha_oficial and e.fecha_oficial >= ahora
                                                and e.tipo != 'publicacion').sorted('fecha_oficial')[:1]
            if not prox:
                lead.stn_proximo_evento = False
                continue
            dias = (fields.Date.to_date(prox.fecha_oficial) - hoy).days
            texto = _('%(ev)s en %(d)s días', ev=etiquetas.get(prox.tipo), d=dias) if dias else \
                _('%(ev)s HOY', ev=etiquetas.get(prox.tipo))
            if lead.stn_fechas_verificadas:
                texto += _(' · fechas verificadas %s', fields.Date.to_date(lead.stn_fechas_verificadas))
            lead.stn_proximo_evento = texto

    @api.onchange('stn_no_procedimiento')
    def _onchange_stn_no_procedimiento(self):
        for lead in self:
            lead.update(lead._stn_vals_desde_numero(lead.stn_no_procedimiento, lead))

    @api.model
    def _stn_vals_desde_numero(self, numero, lead=None):
        """Completa tipo, carácter y clave de UC leyendo el número de procedimiento."""
        datos = P.leer_numero_procedimiento(numero)
        vals = {}
        if not datos:
            return vals
        if datos.get('tipo_codigo') and not (lead and lead.stn_tipo_procedimiento_id):
            tipo = self.env['stn.licitacion.tipo.procedimiento'].search([('code', '=', datos['tipo_codigo'])], limit=1)
            if tipo:
                vals['stn_tipo_procedimiento_id'] = tipo.id
        if datos.get('caracter') and not (lead and lead.stn_caracter):
            vals['stn_caracter'] = datos['caracter']
        if datos.get('uc') and not (lead and lead.stn_unidad_compradora_clave):
            vals['stn_unidad_compradora_clave'] = datos['uc']
        return vals

    @api.depends('stn_partida_ids.ganada', 'stn_partida_ids.monto_adjudicado', 'stn_partida_ids.maximo')
    def _compute_stn_montos(self):
        for lead in self:
            ganadas = lead.stn_partida_ids.filtered(lambda p: p.ganada == 'si')
            lead.stn_partidas_count = len(lead.stn_partida_ids)
            lead.stn_partidas_ganadas = len(ganadas)
            lead.stn_monto_adjudicado = sum(p.monto_adjudicado or p.maximo for p in ganadas)

    @api.depends('stn_requisito_ids.situacion', 'stn_requisito_ids.desecha')
    def _compute_stn_requisitos(self):
        for lead in self:
            faltan = lead.stn_requisito_ids.filtered(lambda r: r.situacion == 'conseguir')
            lead.stn_requisitos_faltantes = len(faltan)
            lead.stn_requisitos_desechan = len(faltan.filtered('desecha'))

    @api.depends('stn_punto_ids.puntos')
    def _compute_stn_puntos(self):
        for lead in self:
            lead.stn_puntos_maximos = sum(lead.stn_punto_ids.mapped('puntos'))

    # ------------------------------------------------------------------
    # Regla de Directores (antes módulo stn_crm_stage_directores)
    # ------------------------------------------------------------------
    @api.model
    def _stn_user_can_move_stage(self):
        return self.env.su or self.env.user.has_group(GROUP_DIRECTORES)

    def _stn_stage_restringida(self):
        """Solo aplica la regla a oportunidades de equipos de licitación."""
        return self.filtered(lambda l: l.type == 'opportunity' and l.team_id.stn_es_licitacion)

    def write(self, vals):
        if (
            'stage_id' in vals
            and not self.env.context.get('stn_skip_stage_check')
            and not self._stn_user_can_move_stage()
        ):
            new_stage_id = vals.get('stage_id') or False
            blocked = self._stn_stage_restringida().filtered(
                lambda l: l.stage_id and l.stage_id.id != new_stage_id)
            if blocked:
                raise UserError(_(
                    "Solo los usuarios del grupo «Licitaciones / Directores» pueden mover libremente la etapa "
                    "de una licitación. Usa los botones de flujo del formulario.\n\nLicitación(es): %s",
                    ', '.join(blocked.mapped('name')[:5])))
        if vals.get('stage_id') and not self.env.context.get('stn_skip_ganado_check'):
            etapa = self.env['crm.stage'].browse(vals['stage_id'])
            if etapa.stn_codigo == 'ganado':
                self._stn_validar_ganado()
        etapa_anterior = {l.id: l.stage_id for l in self} if 'stage_id' in vals else {}
        res = super().write(vals)
        if 'stage_id' in vals:
            self._stn_al_cambiar_etapa(etapa_anterior)
        if 'stn_resultado' in vals and vals['stn_resultado'] in ('ganada', 'parcial'):
            self.stn_pendiente_ids._stn_activar()
        if 'stn_documento_ids' in vals:
            # Los documentos quedan ligados a la licitación (también visibles en su chatter)
            for lead in self:
                lead.stn_documento_ids.filtered(lambda a: not a.res_id).sudo().write(
                    {'res_model': 'crm.lead', 'res_id': lead.id})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('stn_no_procedimiento'):
                for k, v in self._stn_vals_desde_numero(vals['stn_no_procedimiento']).items():
                    vals.setdefault(k, v)
        leads = super().create(vals_list)
        for lead in leads.filtered('stn_es_licitacion'):
            lead._stn_notificar(lead.company_id.stn_usuarios_nueva_ids, _('Revisar nueva licitación'))
            lead._stn_aplicar_viabilidad()
            if lead.stage_id.stn_codigo in SELLO_ETAPA:
                lead._stn_al_cambiar_etapa({lead.id: self.env['crm.stage']})
        return leads

    def _merge_opportunity(self, *args, **kwargs):
        return super(CrmLead, self.with_context(stn_skip_stage_check=True))._merge_opportunity(*args, **kwargs)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == 'kanban' and not self._stn_user_can_move_stage() and self.env.context.get('stn_licitaciones'):
            res = dict(res)
            arch = etree.fromstring(res['arch'])
            if arch.tag == 'kanban':
                arch.set('records_draggable', '0')
                res['arch'] = etree.tostring(arch, encoding='unicode')
        return res

    # ------------------------------------------------------------------
    # Flujo de etapas
    # ------------------------------------------------------------------
    def _stn_etapa(self, codigo):
        self.ensure_one()
        dominio = [('stn_codigo', '=', codigo)]
        etapa = self.env['crm.stage'].search(dominio + [('team_ids', 'in', self.team_id.ids)], limit=1)
        return etapa or self.env['crm.stage'].search(dominio, limit=1)

    def _stn_mover(self, codigo):
        for lead in self:
            etapa = lead._stn_etapa(codigo)
            if not etapa:
                raise UserError(_('No hay una etapa configurada con el código «%s».', codigo))
            if lead.stage_id != etapa:
                lead.with_context(stn_skip_stage_check=True,
                                  stn_skip_ganado_check=self.env.context.get('stn_skip_ganado_check')).write(
                    {'stage_id': etapa.id})
        return True

    def _stn_al_cambiar_etapa(self, etapa_anterior):
        ahora = fields.Datetime.now()
        for lead in self.filtered('stn_es_licitacion'):
            codigo = lead.stage_id.stn_codigo
            if etapa_anterior.get(lead.id) == lead.stage_id:
                continue
            campo = SELLO_ETAPA.get(codigo)
            if campo and not lead[campo]:
                super(CrmLead, lead).write({campo: ahora})
            if codigo == 'analisis':
                lead._stn_notificar(lead.company_id.stn_usuarios_analisis_ids, _('Revisar y analizar licitación'))
            if codigo == 'ganado':
                lead._stn_al_ganar()

    def _stn_notificar(self, usuarios, resumen):
        self.ensure_one()
        for user in usuarios:
            self.activity_schedule('mail.mail_activity_data_todo', summary=resumen, user_id=user.id,
                                   date_deadline=fields.Date.context_today(self))

    def _stn_aplicar_viabilidad(self):
        """Antes: automatización Studio 'Viabilidad de IA para mover licitación a análisis'."""
        minimo = int(self.env['ir.config_parameter'].sudo().get_param('stn_licitaciones.nivel_analisis', 4) or 4)
        for lead in self:
            if (lead.stn_es_licitacion and lead.stage_id.stn_codigo == 'nueva'
                    and lead.stn_viabilidad and int(lead.stn_viabilidad) >= minimo):
                lead._stn_mover('analisis')

    def action_stn_pasar_analisis(self):
        return self._stn_mover('analisis')

    def action_stn_pasar_preparacion(self):
        return self._stn_mover('preparacion')

    def action_stn_pasar_revision_ia(self):
        return self._stn_mover('revision_ia')

    def action_stn_pasar_revision(self):
        return self._stn_mover('revision')

    def action_stn_pasar_alta(self):
        return self._stn_mover('presentada')

    def action_set_won_rainbowman(self):
        self._stn_check_director(_('marcar como ganada'))
        self.filtered('stn_es_licitacion')._stn_validar_ganado()
        return super(CrmLead, self.with_context(stn_skip_ganado_check=True)).action_set_won_rainbowman()

    def action_stn_pasar_evaluacion(self):
        return self._stn_mover('evaluacion')

    def action_stn_pasar_ganado(self):
        self._stn_check_director(_('marcar como ganada'))
        return self._stn_mover('ganado')

    def _stn_validar_ganado(self):
        """Glosario §4: el fallo y las partidas adjudicadas deben estar cargados antes de marcar ganada."""
        faltan = []
        for lead in self.filtered('stn_es_licitacion'):
            motivos = []
            if not lead.stn_acta_fallo:
                motivos.append(_('subir el acta de fallo'))
            if lead.stn_partida_ids and not lead.stn_partida_ids.filtered(lambda p: p.ganada == 'si'):
                motivos.append(_('marcar las partidas ganadas'))
            if motivos:
                faltan.append('%s: %s' % (lead.stn_no_procedimiento or lead.name, ', '.join(motivos)))
        if faltan:
            raise UserError(_('Antes de marcar como ganada falta:\n%s', '\n'.join(faltan)))

    def _stn_al_ganar(self):
        for lead in self:
            participadas = lead.stn_partida_ids.filtered(lambda p: p.participamos != 'no')
            ganadas = participadas.filtered(lambda p: p.ganada == 'si')
            if lead.stn_resultado in ('pendiente', False):
                resultado = 'parcial' if participadas and len(ganadas) < len(participadas) else 'ganada'
                super(CrmLead, lead).write({'stn_resultado': resultado})
            # Firma, fianza y póliza RC salen del tablero: se controlan como actividades (glosario §4)
            base = [_('Firma del contrato'), _('Fianza de cumplimiento')]
            if lead.stn_requiere_rc:
                base.append(_('Póliza de responsabilidad civil'))
            existentes = [P.norm(n) for n in lead.stn_pendiente_ids.mapped('name')]
            for nombre in base:
                if not any(P.norm(nombre) in e for e in existentes):
                    self.env['stn.licitacion.pendiente'].create({'lead_id': lead.id, 'name': nombre,
                                                                 'fuente': _('Regla Perlop')})
            lead.stn_pendiente_ids._stn_activar()

    @api.model
    def _cron_stn_evaluacion(self):
        """Presentada → En evaluación cuando ya pasó la apertura."""
        ahora = fields.Datetime.now()
        for lead in self.search([('stage_id.stn_codigo', '=', 'presentada'), ('stn_fecha_apertura', '<', ahora),
                                 ('active', '=', True)]):
            lead._stn_mover('evaluacion')

    def _stn_check_director(self, accion):
        if self._stn_stage_restringida() and not self._stn_user_can_move_stage():
            raise UserError(_('Solo Directores pueden %s una licitación.', accion))

    def action_stn_sincronizar_agenda(self):
        self.stn_evento_ids._stn_sincronizar_agenda()
        return True

    # ==================================================================
    # Ingesta de la ficha LICIA
    # ==================================================================
    def _stn_tz(self):
        return self.env['ir.config_parameter'].sudo().get_param('stn_licitaciones.tz') or 'America/Mexico_City'

    @api.model
    def stn_upsert_ficha(self, payload, origen='http'):
        """Crea o actualiza una licitación a partir de la ficha LICIA (contrato JSON v1).

        Devuelve dict con: accion (creada/actualizada), lead_id, advertencias.
        """
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValidationError(_('La ficha debe ser un objeto JSON.'))
        numero = P.texto(payload.get('numero_procedimiento'))
        if not numero:
            raise ValidationError(_('Falta numero_procedimiento en la ficha.'))
        advertencias = []
        ctx = dict(self.env.context, stn_skip_stage_check=True, mail_create_nosubscribe=True,
                   tracking_disable=False)
        Lead = self.with_context(ctx)
        lead = Lead.with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', numero), ('company_id', 'in', [self.env.company.id, False])], limit=1)
        vals = Lead._stn_vals_encabezado(payload, advertencias, nuevo=not lead)
        if lead:
            accion = 'actualizada'
            lead.write(vals)
        else:
            accion = 'creada'
            ICP = self.env['ir.config_parameter'].sudo()
            team = self.env['crm.team'].browse(int(ICP.get_param('stn_licitaciones.team_id', 0) or 0)).exists() \
                or self.env['crm.team'].search([('stn_es_licitacion', '=', True)], limit=1)
            vals.update({
                'type': 'opportunity',
                'team_id': team.id,
                'name': P.texto(payload.get('nombre_oportunidad')) or numero,
            })
            user_id = int(ICP.get_param('stn_licitaciones.user_id', 0) or 0)
            if user_id:
                vals['user_id'] = user_id
            etapa = self.env['crm.stage'].search([('stn_codigo', '=', 'nueva')] +
                                                 ([('team_ids', 'in', team.ids)] if team else []), limit=1)
            if etapa:
                vals['stage_id'] = etapa.id
            lead = Lead.create(vals)
        lead = lead.with_context(ctx)
        lead._stn_sync_eventos(payload, advertencias)
        lead._stn_sync_simple('stn_cambio_ids', payload.get('historial'), ('fecha', 'campo', 'antes', 'despues'),
                              lead._stn_vals_cambio)
        lead._stn_sync_simple('stn_pregunta_ids', payload.get('preguntas'), ('numero',), lead._stn_vals_pregunta)
        lead._stn_sync_partidas(payload.get('partidas'), advertencias)
        lead._stn_sync_sedes(payload.get('sedes'))
        lead._stn_sync_requisitos(payload.get('requisitos'), advertencias)
        lead._stn_sync_simple('stn_punto_ids', payload.get('puntos'), ('rubro',), lead._stn_vals_punto)
        lead._stn_sync_simple('stn_antecedente_ids', payload.get('antecedentes'), ('procedimiento',),
                              lead._stn_vals_antecedente)
        lead._stn_sync_competidores(payload.get('competidores'))
        lead._stn_sync_resultado(payload.get('resultado') or {}, advertencias)
        lead._stn_sync_simple('stn_pendiente_ids', payload.get('pendientes_fallo'), ('name',),
                              lead._stn_vals_pendiente, proteger=('estado', 'activity_id'))
        lead._stn_sync_seguimiento(payload.get('seguimiento'))
        lead._stn_sync_adjuntos(payload.get('adjuntos'), advertencias)
        if accion == 'creada':
            lead._stn_aplicar_viabilidad()
        lead.stn_evento_ids._stn_sincronizar_agenda()
        if accion == 'actualizada':
            lead.message_post(body=_('Ficha LICIA actualizada (corte %s).', payload.get('corte') or '-'),
                              message_type='comment', subtype_xmlid='mail.mt_note')
        return {'accion': accion, 'lead_id': lead.id, 'name': lead.name, 'advertencias': advertencias}

    # ---------------- encabezado ----------------
    def _stn_vals_encabezado(self, d, advertencias, nuevo):
        tz = self._stn_tz()
        g = d.get
        vals = {
            'stn_no_procedimiento': P.texto(g('numero_procedimiento')),
            'stn_licia_version': P.texto(g('version')) or P.FICHA_VERSION,
            'stn_licia_corte': P.texto(g('corte')),
            'stn_licia_ultima_sync': fields.Datetime.now(),
            'stn_licia_payload': json.dumps(d, ensure_ascii=False, indent=1, default=str)[:200000],
        }

        def put(campo, valor):
            if valor is not None and valor is not False and valor != '':
                vals[campo] = valor

        def put_bool(campo, valor):
            b = P.booleano(valor)
            if b is not None:
                vals[campo] = b

        nivel = P.entero(g('nivel_licia'))
        if nivel is not None:
            vals['stn_viabilidad'] = str(max(0, min(5, nivel)))
        accion = P.mapear(g('accion'), P.ACCION)
        put('stn_accion', accion)
        put('stn_accion_detalle', P.texto(g('accion')))
        put('stn_lectura', P.texto(g('lectura')))
        put('stn_razon_nivel', P.texto(g('razon_nivel')))
        plataforma = P.mapear(g('plataforma'), [('comprasmx', 'comprasmx'), ('cfe', 'cfe'), ('compranet', 'compranet'),
                                                 ('estat', 'estatal')], 'otra' if P.texto(g('plataforma')) else False)
        put('stn_plataforma', plataforma)
        put('stn_url_ficha', P.texto(g('url_ficha')))
        put('stn_folio_plataforma', P.texto(g('folio_plataforma')))
        put('stn_plaza', P.texto(g('plaza')))
        if 'fechas_verificadas' in d:
            put('stn_fechas_verificadas', P.fecha_hora(g('fechas_verificadas'), tz))
        put_bool('stn_requiere_rc', g('requiere_poliza_rc'))
        if P.texto(g('analisis_error')):
            vals['stn_analisis_estado'] = 'error'
            vals['stn_analisis_mensaje'] = P.texto(g('analisis_error'))
        elif P.booleano(g('analisis_documentos')):
            vals['stn_analisis_estado'] = 'completado'
            vals['stn_analisis_mensaje'] = P.texto(g('analisis_resumen')) or False
        for k, v in self._stn_vals_desde_numero(g('numero_procedimiento')).items():
            vals.setdefault(k, v)
        put('stn_objeto', P.texto(g('objeto')))
        put('stn_cucop', P.texto(g('cucop')))
        put('stn_caracter', P.mapear(g('caracter'), P.CARACTER))
        put('stn_area_requirente', P.texto(g('area_requirente')))
        put_bool('stn_operamos_estado', g('operamos_en_estado'))
        put_bool('stn_conjunta_permitida', g('conjunta_permitida'))
        put_bool('stn_cliente_nuevo', g('cliente_nuevo'))
        put('stn_minimo_tecnico', P.numero(g('minimo_tecnico')))
        put('stn_garantia_pct', P.numero(g('garantia_pct')))
        put('stn_monto_minimo', P.numero(g('monto_minimo')))
        maximo = P.numero(g('monto_maximo'))
        if maximo is not None:
            vals['stn_monto_maximo'] = maximo
            vals['expected_revenue'] = maximo
        put('stn_monto_minimo_estimado', P.numero(g('monto_minimo_estimado')))
        max_est = P.numero(g('monto_maximo_estimado'))
        if max_est is not None:
            vals['stn_monto_maximo_estimado'] = max_est
            if maximo is None:
                vals['expected_revenue'] = max_est  # sin monto oficial: ingreso esperado = estimado
        put('stn_condiciones_entrega', P.texto(g('condiciones_entrega')))
        put('stn_modalidad', P.mapear(g('modalidad') or g('tipo_procedimiento'),
                                      [('electron', 'electronica'), ('presencial', 'presencial'), ('mixt', 'mixta')]))
        if P.texto(g('empresa_licitante')):
            vals['stn_empresa_licitante_id'] = self._stn_partner(g('empresa_licitante')).id
        put('stn_nota_montos', P.texto(g('nota_montos')))
        put('stn_vigencia_inicio', P.fecha(g('vigencia_inicio')))
        put('stn_vigencia_fin', P.fecha(g('vigencia_fin')))
        put('stn_logistica_nota', P.texto(g('logistica_nota')))
        documentos = g('documentos') or {}
        if isinstance(documentos, dict):
            put('stn_carpeta', P.texto(documentos.get('carpeta')))
        junta = g('junta') or {}
        if isinstance(junta, dict):
            put_bool('stn_junta_aplica', junta.get('aplica'))
            put('stn_aclaraciones', P.texto(junta.get('aclaraciones')))
            put('stn_acta_aclaraciones', P.texto(junta.get('acta')))

        # catálogos
        if P.texto(g('tipo_procedimiento')):
            tipo = self.env['stn.licitacion.tipo.procedimiento']._stn_buscar_o_crear(g('tipo_procedimiento'))
            vals['stn_tipo_procedimiento_id'] = tipo.id
            vals['stn_tipo_procedimiento_detalle'] = P.texto(g('tipo_procedimiento'))
        if P.texto(g('criterio')):
            vals['stn_criterio_id'] = self.env['stn.licitacion.criterio']._stn_buscar_o_crear(g('criterio')).id
            vals['stn_criterio_detalle'] = P.texto(g('criterio'))
        if P.texto(g('estatus_procedimiento')):
            vals['stn_estatus_id'] = self.env['stn.licitacion.estatus']._stn_buscar_o_crear(
                g('estatus_procedimiento')).id
        if P.texto(g('tipo_servicio')):
            vals['stn_tipo_servicio_id'] = self.env['stn.tipo.servicio']._stn_buscar_o_crear(g('tipo_servicio')).id

        # fechas
        for clave, campo in [('fecha_deteccion', 'stn_fecha_deteccion'),
                             ('fecha_publicacion', 'stn_fecha_publicacion'),
                             ('fecha_limite_preguntas', 'stn_fecha_limite_preguntas'),
                             ('fecha_junta', 'stn_fecha_junta'),
                             ('fecha_apertura', 'stn_fecha_apertura'),
                             ('fecha_limite_interna', 'stn_fecha_limite_interna'),
                             ('fecha_fallo', 'stn_fecha_fallo'),
                             ('fecha_inicio_contrato', 'stn_fecha_inicio_contrato')]:
            if clave in d:
                valor = P.fecha_hora(g(clave), tz)
                vals[campo] = valor or False
        # Cierre esperado = fecha de fallo (si no hay, el límite interno)
        if vals.get('stn_fecha_fallo'):
            vals['date_deadline'] = fields.Date.to_date(vals['stn_fecha_fallo'])
        elif vals.get('stn_fecha_limite_interna'):
            vals['date_deadline'] = fields.Date.to_date(vals['stn_fecha_limite_interna'])

        # dependencia > convocante (OOAD) > unidad compradora / estado
        dependencia = self._stn_partner(g('dependencia'))
        if dependencia:
            vals['stn_dependencia_id'] = dependencia.id
        convocante = self._stn_partner(g('convocante'), parent=dependencia)
        if convocante:
            vals['stn_convocante_id'] = convocante.id
        clave_uc, nombre_uc = P.separar_unidad_compradora(g('unidad_compradora'))
        if nombre_uc:
            uc = self._stn_partner(nombre_uc, ref=clave_uc, parent=convocante)
            vals['partner_id'] = uc.id
            vals['stn_unidad_compradora_clave'] = clave_uc or False
        elif convocante:
            vals['partner_id'] = convocante.id
        if P.texto(g('estado')):
            estado = self.env['res.country.state'].search(
                [('country_id.code', '=', 'MX'), ('name', '=ilike', P.texto(g('estado')))], limit=1)
            if estado:
                vals['state_id'] = estado.id
                vals['country_id'] = estado.country_id.id
            else:
                advertencias.append(_('Estado no encontrado: %s', g('estado')))
        return vals

    @api.model
    def _stn_partner(self, nombre, ref=False, parent=False, competidor=False):
        nombre = P.texto(nombre)
        if not nombre and not ref:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        partner = Partner.browse()
        if ref:
            partner = Partner.search([('ref', '=', ref)], limit=1)
        if not partner and nombre:
            partner = Partner.search([('name', '=ilike', nombre)], limit=1)
        if not partner:
            vals = {'name': nombre or ref, 'is_company': True, 'ref': ref or False}
            if competidor:
                vals['stn_es_competidor'] = True
            else:
                vals['stn_es_convocante'] = True
            if parent:
                vals['parent_id'] = parent.id
            partner = Partner.create(vals)
        elif competidor and not partner.stn_es_competidor:
            partner.stn_es_competidor = True
        return partner

    # ---------------- tablas ----------------
    def _stn_sync_simple(self, campo_o2m, filas, llave, preparar, proteger=()):
        """Sincroniza filas por llave natural; no borra lo capturado a mano."""
        if not filas or not isinstance(filas, list):
            return
        existentes = self[campo_o2m]
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            vals = preparar(fila)
            if not vals:
                continue
            clave = tuple(str(vals.get(k) or '').strip().lower() for k in llave)
            actual = existentes.filtered(
                lambda r: tuple(str(r[k] or '').strip().lower() for k in llave) == clave)[:1]
            if actual:
                actual.write({k: v for k, v in vals.items() if k not in proteger})
            else:
                vals['lead_id'] = self.id
                self.env[existentes._name].create(vals)

    def _stn_vals_cambio(self, f):
        return {'fecha': P.fecha(f.get('fecha')), 'campo': P.texto(f.get('campo')),
                'antes': P.texto(f.get('antes')), 'despues': P.texto(f.get('despues')),
                'fuente': P.texto(f.get('fuente'))}

    def _stn_vals_pregunta(self, f):
        if not P.texto(f.get('pregunta')):
            return {}
        return {'numero': P.entero(f.get('numero')) or 0, 'pregunta': P.texto(f.get('pregunta')),
                'numeral': P.texto(f.get('numeral')),
                'estado': P.mapear(f.get('estado'), P.PREGUNTA_ESTADO, 'sugerida'),
                'estado_detalle': P.texto(f.get('estado')), 'respuesta': P.texto(f.get('respuesta'))}

    def _stn_vals_punto(self, f):
        if not P.texto(f.get('rubro')):
            return {}
        return {'rubro': P.texto(f.get('rubro')), 'puntos': P.numero(f.get('puntos')) or 0.0,
                'entregable': P.texto(f.get('entregable')),
                'situacion': P.mapear(f.get('situacion'), P.SITUACION),
                'situacion_detalle': P.texto(f.get('situacion'))}

    def _stn_vals_antecedente(self, f):
        if not P.texto(f.get('procedimiento')):
            return {}
        ganador = self._stn_partner(f.get('ganador'), competidor=True) if P.texto(f.get('ganador')) else False
        anterior = self.with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', P.texto(f.get('procedimiento')))], limit=1)
        desiertas = f.get('desiertas')
        if isinstance(desiertas, list):
            desiertas = ' · '.join(map(str, desiertas))
        return {'procedimiento': P.texto(f.get('procedimiento')),
                'lead_anterior_id': anterior.id or False,
                'participamos': bool(P.booleano(f.get('participamos'))),
                'razon_mismo': P.texto(f.get('razon_mismo')), 'ganador_id': ganador.id if ganador else False,
                'puntos_ganador': P.numero(f.get('puntos_ganador')) or 0.0,
                'contrato': P.texto(f.get('contrato')), 'como_gano': P.texto(f.get('como_gano')),
                'precio_a_vencer': P.texto(f.get('precio_a_vencer')),
                'monto_maximo': P.numero(f.get('monto_maximo')) or 0.0, 'vigencia': P.texto(f.get('vigencia')),
                'desiertas': P.texto(desiertas), 'hipotesis': P.texto(f.get('hipotesis'))}

    def _stn_vals_pendiente(self, f):
        nombre = P.texto(f.get('pendiente') or f.get('name'))
        if not nombre:
            return {}
        return {'name': nombre, 'plazo': P.texto(f.get('plazo')), 'fecha': P.fecha(f.get('fecha')),
                'fecha_detalle': P.texto(f.get('fecha')), 'fuente': P.texto(f.get('fuente'))}

    def _stn_sync_eventos(self, d, advertencias):
        tz = self._stn_tz()
        horas_default = float(self.env['ir.config_parameter'].sudo().get_param(
            'stn_licitaciones.horas_limite_interna', 72) or 72)
        filas = d.get('eventos') if isinstance(d.get('eventos'), list) else []
        # si no vienen eventos, se arman desde las fechas planas
        if not filas:
            for clave, tipo in P.FECHAS_EVENTO:
                if clave in d:
                    filas.append({'tipo': tipo, 'fecha_oficial': d.get(clave), 'fuente': 'Ficha'})
        for fila in filas:
            tipo = fila.get('tipo')
            tipo = tipo if tipo in dict(self.env['stn.licitacion.evento']._fields['tipo'].selection) \
                else P.mapear(tipo, P.EVENTO, 'otro')
            oficial = P.fecha_hora(fila.get('fecha_oficial'), tz)
            limite = P.fecha_hora(fila.get('fecha_limite_interna'), tz)
            vals = {
                'tipo': tipo,
                'name': P.texto(fila.get('evento') or fila.get('nombre')),
                'aplica': bool(oficial) and P.booleano(fila.get('aplica')) is not False,
                'fecha_oficial': oficial or False,
                'fuente': P.texto(fila.get('fuente')),
                'nota': P.texto(fila.get('nota')),
                'origen': 'licia',
            }
            if limite:
                vals['fecha_limite_interna'] = limite
            elif tipo == 'apertura' and oficial:
                vals['anticipacion_horas'] = horas_default
            actual = self.stn_evento_ids.filtered(lambda e: e.tipo == tipo and (tipo != 'otro' or e.name == vals['name']))[:1]
            if actual:
                actual.with_context(stn_fuente_cambio='LICIA').write(vals)
            else:
                vals['lead_id'] = self.id
                self.env['stn.licitacion.evento'].create(vals)

    def _stn_sync_partidas(self, filas, advertencias):
        if not filas or not isinstance(filas, list):
            return
        Partida = self.env['stn.licitacion.partida']
        for f in filas:
            clave = P.texto(f.get('clave') or f.get('partida')) or (
                P.texto(f.get('numero')) if not isinstance(f.get('numero'), (int, float)) else False)
            num = P.entero(f.get('numero')) if isinstance(f.get('numero'), (int, float)) else P.entero(clave)
            if num is None and not clave:
                continue
            clave = clave or str(num)
            ganador_ant = self._stn_partner(f.get('ganador_anterior'), competidor=True) \
                if P.texto(f.get('ganador_anterior')) else False
            vals = {
                'numero': num or 0,
                'clave': clave,
                'ganador_anterior_id': ganador_ant.id if ganador_ant else False,
                'suma_precios_ganador': P.numero(f.get('suma_precios_ganador')) or 0.0,
                'nuestra_suma_precios': P.numero(f.get('nuestra_suma_precios')) or 0.0,
                'maximo_estimado': bool(P.booleano(f.get('maximo_estimado'))),
                'lugar_precios': P.texto(f.get('lugar_precios')),
                'unidad': P.texto(f.get('unidad')),
                'municipio': P.texto(f.get('municipio')),
                'domicilio': P.texto(f.get('domicilio')),
                'domicilio_alterno': P.texto(f.get('domicilio_alterno')),
                'domicilio_inconsistente': bool(P.booleano(f.get('domicilio_inconsistente'))),
                'corredor': P.texto(f.get('corredor')),
                'vehiculos': P.texto(f.get('vehiculos')),
                'cedis': P.texto(f.get('cedis')),
                'minimo': P.numero(f.get('minimo')) or 0.0,
                'maximo': P.numero(f.get('maximo')) or 0.0,
                'maximo_anterior': P.numero(f.get('maximo_anterior')) or 0.0,
                'nota': P.texto(f.get('nota')),
            }
            participamos = P.mapear(f.get('participamos'), P.PARTICIPAMOS)
            ganada = P.mapear(f.get('ganada'), P.GANADA)
            actual = self.stn_partida_ids.filtered(lambda p: (p.clave or str(p.numero)) == clave)[:1]
            # Las decisiones del equipo no se pisan: solo se llenan si siguen "por decidir"/"N/A"
            if participamos and (not actual or actual.participamos == 'por_decidir'):
                vals['participamos'] = participamos
            if ganada in ('si', 'no') and (not actual or actual.ganada == 'na'):
                vals['ganada'] = ganada
            if actual:
                actual.write(vals)
            else:
                vals['lead_id'] = self.id
                actual = Partida.create(vals)
            renglones = f.get('renglones')
            if isinstance(renglones, list):
                for r in renglones:
                    nombre = P.texto(r.get('nombre_contractual') or r.get('descripcion'))
                    if not nombre:
                        continue
                    rvals = {
                        'numero': P.entero(r.get('numero')) or 0,
                        'nombre_contractual': nombre,
                        'clave': P.texto(r.get('clave')),
                        'unidad_medida': P.texto(r.get('unidad_medida')),
                        'cantidad_minima': P.numero(r.get('cantidad_minima')) or 0.0,
                        'cantidad_maxima': P.numero(r.get('cantidad_maxima')) or 0.0,
                        'precio_unitario': P.numero(r.get('precio_unitario')) or 0.0,
                    }
                    existe = actual.renglon_ids.filtered(
                        lambda x: (rvals['numero'] and x.numero == rvals['numero']) or x.nombre_contractual == nombre)[:1]
                    if existe:
                        existe.write(rvals)
                    else:
                        rvals['partida_id'] = actual.id
                        self.env['stn.licitacion.renglon'].create(rvals)

    def _stn_sync_sedes(self, filas):
        """Sedes y logística: una línea por unidad (puede atender varias partidas)."""
        if not filas or not isinstance(filas, list):
            return
        Sede = self.env['stn.licitacion.sede']
        for f in filas:
            unidad = P.texto(f.get('unidad'))
            if not unidad:
                continue
            partidas = f.get('partidas')
            if isinstance(partidas, list):
                partidas = ', '.join(map(str, partidas))
            vals = {
                'unidad': unidad,
                'partidas': P.texto(partidas),
                'municipio': P.texto(f.get('municipio')),
                'domicilio': P.texto(f.get('domicilio')),
                'domicilio_alterno': P.texto(f.get('domicilio_alterno')),
                'domicilio_inconsistente': bool(P.booleano(f.get('domicilio_inconsistente'))),
                'corredor': P.texto(f.get('corredor')),
                'vehiculos': P.texto(f.get('vehiculos')),
                'cedis': P.texto(f.get('cedis')),
                'horario': P.texto(f.get('horario')),
                'nota': P.texto(f.get('nota')),
            }
            actual = self.stn_sede_ids.filtered(lambda s: P.norm(s.unidad) == P.norm(unidad))[:1]
            if actual:
                actual.write(vals)
            else:
                vals['lead_id'] = self.id
                Sede.create(vals)

    def _stn_sync_requisitos(self, filas, advertencias):
        if not filas or not isinstance(filas, list):
            return
        Req = self.env['stn.licitacion.requisito']
        Maestro = self.env['stn.requisito']
        seq = max(self.stn_requisito_ids.mapped('sequence') or [0])
        for f in filas:
            nombre = P.texto(f.get('requisito') or f.get('name'))
            if not nombre:
                continue
            ref = P.texto(f.get('referencia'))
            vals = {
                'name': nombre,
                'referencia': ref,
                'tipo': P.mapear(f.get('tipo'), P.TIPO_REQUISITO),
                'tipo_detalle': P.texto(f.get('tipo')),
                'situacion': P.mapear(f.get('situacion'), P.SITUACION),
                'situacion_detalle': P.texto(f.get('situacion')),
                'efecto': P.texto(f.get('efecto')),
                'vigencia_maxima': P.texto(f.get('vigencia_maxima')),
                'antiguedad_max_dias': P.entero(f.get('antiguedad_max_dias')) or P.antiguedad_dias(f.get('vigencia_maxima')),
                'nota': P.texto(f.get('nota') or f.get('nota_licia')),
                'origen': 'licia',
            }
            if P.texto(f.get('extracto_literal')):
                vals['extracto_literal'] = P.texto(f.get('extracto_literal'))
            if f.get('captura_base64'):
                vals['captura'] = f.get('captura_base64')
            if P.texto(f.get('categoria')):
                vals['categoria_id'] = self.env['stn.requisito.categoria']._stn_buscar_o_crear(f.get('categoria')).id
            if self.stn_tipo_servicio_id:
                vals['tipo_servicio_id'] = self.stn_tipo_servicio_id.id
            actual = self.stn_requisito_ids.filtered(
                lambda r: (r.referencia or '') == (ref or '') and P.norm(r.name) == P.norm(nombre))[:1]
            if not actual.requisito_id and not (actual and actual.requisito_id):
                maestro = Maestro.search([('name', '=ilike', nombre)], limit=1)
                if maestro:
                    vals['requisito_id'] = maestro.id
            if actual:
                actual.write(vals)
            else:
                seq += 1
                vals.update({'lead_id': self.id, 'sequence': seq})
                Req.create(vals)

    def _stn_sync_competidores(self, filas):
        if not filas or not isinstance(filas, list):
            return
        for f in filas:
            partner = self._stn_partner(f.get('nombre'), competidor=True)
            if not partner:
                continue
            rol = P.mapear(f.get('lectura'), [('incumbente', 'incumbente'), ('entrante', 'entrante'),
                                              ('ocasional', 'ocasional')], 'otro')
            vals = {'partner_id': partner.id, 'historia': P.texto(f.get('historia')),
                    'lectura': P.texto(f.get('lectura')), 'rol': rol}
            actual = self.stn_competidor_ids.filtered(lambda c: c.partner_id == partner)[:1]
            if actual:
                actual.write(vals)
            else:
                vals['lead_id'] = self.id
                self.env['stn.licitacion.competidor'].create(vals)

    def _stn_sync_resultado(self, r, advertencias):
        if not isinstance(r, dict) or not r:
            return
        vals = {}
        celebrada = P.booleano(r.get('apertura_celebrada'))
        if celebrada is not None:
            vals['stn_apertura_celebrada'] = celebrada
        if P.texto(r.get('lugar_precios')):
            vals['stn_lugar_precios'] = P.texto(r.get('lugar_precios'))
        if P.texto(r.get('fallo')):
            vals['stn_fallo_texto'] = P.texto(r.get('fallo'))
            resultado = P.mapear(r.get('fallo'), P.RESULTADO)
            if resultado and self.stn_resultado == 'pendiente':
                vals['stn_resultado'] = resultado
        if P.texto(r.get('causa_literal')):
            vals['stn_causa_literal'] = P.texto(r.get('causa_literal'))
        if P.texto(r.get('motivo_perdida')):
            motivo = self.env['crm.lost.reason'].search([('name', '=ilike', P.texto(r.get('motivo_perdida')))], limit=1)
            if motivo:
                vals['lost_reason_id'] = motivo.id
            else:
                advertencias.append(_('Motivo de pérdida no encontrado: %s', r.get('motivo_perdida')))
        if vals:
            self.write(vals)

    def _stn_sync_seguimiento(self, filas):
        if not filas or not isinstance(filas, list):
            return
        Seg = self.env['stn.licitacion.seguimiento']
        for f in filas:
            texto = P.texto(f.get('texto'))
            if not texto:
                continue
            fecha = P.texto(f.get('fecha')) or ''
            if self.stn_seguimiento_ids.filtered(lambda s: (s.fecha or '') == fecha and s.texto == texto):
                continue
            msg = self.message_post(body=_('LICIA · %(fecha)s — %(texto)s', fecha=fecha, texto=texto),
                                    message_type='comment', subtype_xmlid='mail.mt_note')
            Seg.create({'lead_id': self.id, 'fecha': fecha, 'texto': texto, 'message_id': msg.id})

    def _stn_sync_adjuntos(self, filas, advertencias):
        if not filas or not isinstance(filas, list):
            return
        Att = self.env['ir.attachment'].sudo()
        for f in filas:
            nombre = P.texto(f.get('nombre'))
            contenido = f.get('contenido_base64')
            if not nombre or not contenido:
                continue
            try:
                base64.b64decode(contenido, validate=True)
            except Exception:  # noqa: BLE001
                advertencias.append(_('Adjunto inválido (base64): %s', nombre))
                continue
            vals = {'name': nombre, 'datas': contenido, 'res_model': 'crm.lead', 'res_id': self.id,
                    'mimetype': P.texto(f.get('mimetype')) or False}
            existe = Att.search([('res_model', '=', 'crm.lead'), ('res_id', '=', self.id), ('name', '=', nombre)],
                                limit=1)
            if existe:
                existe.write({'datas': contenido})
            else:
                existe = Att.create(vals)
            if existe not in self.stn_documento_ids:
                self.write({'stn_documento_ids': [(4, existe.id)]})
            if 'requisitos' in nombre.lower() and nombre.lower().endswith('.pdf'):
                self.write({'stn_requisitos_file': contenido, 'stn_requisitos_filename': nombre})

    # ==================================================================
    # Correo: alias del equipo de licitaciones
    # ==================================================================
    @api.model
    def _stn_payload_desde_correo(self, msg_dict):
        for att in msg_dict.get('attachments') or []:
            fname = getattr(att, 'fname', None) or (att[0] if isinstance(att, (list, tuple)) else '')
            content = getattr(att, 'content', None) or (att[1] if isinstance(att, (list, tuple)) else b'')
            if fname and fname.lower().endswith('.json'):
                try:
                    if isinstance(content, bytes):
                        content = content.decode('utf-8-sig')
                    datos = json.loads(content)
                    if isinstance(datos, dict) and datos.get('numero_procedimiento'):
                        return datos
                except Exception:  # noqa: BLE001
                    _logger.warning('LICIA: adjunto JSON ilegible %s', fname)
        cuerpo = msg_dict.get('body') or ''
        if cuerpo:
            try:
                from odoo.tools import html2plaintext
                cuerpo = html2plaintext(cuerpo)
            except Exception:  # noqa: BLE001
                pass
        datos = P.parse_clave_valor(cuerpo)
        return datos if datos.get('numero_procedimiento') else None

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        team_id = (custom_values or {}).get('team_id') or self.env.context.get('default_team_id')
        team = self.env['crm.team'].browse(team_id).exists() if team_id else self.env['crm.team']
        if team.stn_es_licitacion:
            payload = self._stn_payload_desde_correo(msg_dict)
            if payload:
                Log = self.env['stn.licia.log'].sudo()
                try:
                    with self.env.cr.savepoint():
                        res = self.stn_upsert_ficha(payload, origen='email')
                    Log._stn_registrar('email', payload, res)
                    return self.browse(res['lead_id'])
                except Exception as e:  # noqa: BLE001
                    _logger.exception('LICIA: error al procesar correo')
                    Log._stn_registrar('email', payload, error=str(e))
        return super().message_new(msg_dict, custom_values=custom_values)

    def message_update(self, msg_dict, update_vals=None):
        if len(self) == 1 and self.stn_es_licitacion:
            payload = self._stn_payload_desde_correo(msg_dict)
            if payload and P.texto(payload.get('numero_procedimiento')) == self.stn_no_procedimiento:
                try:
                    with self.env.cr.savepoint():
                        res = self.stn_upsert_ficha(payload, origen='email')
                    self.env['stn.licia.log'].sudo()._stn_registrar('email', payload, res)
                except Exception as e:  # noqa: BLE001
                    self.env['stn.licia.log'].sudo()._stn_registrar('email', payload, error=str(e))
        return super().message_update(msg_dict, update_vals=update_vals)
