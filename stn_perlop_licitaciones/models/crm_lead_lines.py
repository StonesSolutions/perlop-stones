import re
from datetime import timedelta

from odoo import _, api, fields, models

from .licia_parser import clave_partida, lista_claves

TIPO_EVENTO = [
    ('publicacion', 'Publicación'),
    ('limite_preguntas', 'Límite para preguntas'),
    ('junta', 'Junta de aclaraciones'),
    ('cierre_junta', 'Cierre de junta'),
    ('visita', 'Visita a instalaciones'),
    ('muestras', 'Entrega de muestras'),
    ('apertura', 'Presentación y apertura'),
    ('fallo', 'Fallo'),
    ('firma', 'Firma de contrato'),
    ('inicio_contrato', 'Inicio del contrato'),
    ('otro', 'Otro'),
]

TIPO_REQUISITO = [
    ('legal', 'Legal'),
    ('tecnico', 'Técnico'),
    ('economico', 'Económico'),
    ('puntos', 'Puntos'),
    ('operativo', 'Operativo'),
    ('forma', 'Forma'),
]

# Eventos que exigen que alguien haga algo antes de la fecha oficial (límite interno, aviso y escalamiento).
# Publicación, cierre de junta, fallo e inicio de contrato son informativos: solo van al calendario.
EVENTOS_ACCION = {'limite_preguntas', 'junta', 'visita', 'muestras', 'apertura', 'firma', 'otro'}
# Plazos de preparación de la propuesta: se activan cuando la licitación se aprueba (etapa Preparación en adelante).
EVENTOS_PREPARACION = {'muestras', 'apertura'}
ETAPAS_APROBADAS = {'preparacion', 'revision_ia', 'revision', 'presentada', 'evaluacion', 'ganado'}

# Pestañas de «Mi proposición» en ComprasMX (los 3 tipos de requisitos para el avance)
PESTANA = [('legal', 'Legal-administrativa'), ('tecnica', 'Técnica'), ('economica', 'Económica')]
PESTANA_POR_TIPO = {'legal': 'legal', 'forma': 'legal', 'tecnico': 'tecnica', 'operativo': 'tecnica',
                    'puntos': 'tecnica', 'economico': 'economica'}
AVANCE = [('falta', 'Falta'), ('incompleto', 'Incompleto'), ('completo', 'Completo'), ('no_aplica', 'No aplica')]


def clave_orden_casilla(valor):
    """«1.4» → 1004, «11» → 11000; sin casilla → al final de su pestaña."""
    m = re.match(r'^\s*(\d+)(?:\s*[.\-]\s*(\d+))?', str(valor or ''))
    if not m:
        return 999999
    return int(m.group(1)) * 1000 + int(m.group(2) or 0)


SITUACION = [
    ('tenemos', 'Tenemos'),
    ('se_genera', 'Se genera'),
    ('verificar', 'Verificar'),
    ('conseguir', 'Conseguir'),
    ('no_aplica', 'No aplica'),
]


class StnLicitacionEvento(models.Model):
    _name = 'stn.licitacion.evento'
    _description = 'Evento del procedimiento licitatorio'
    _order = 'fecha_oficial, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    tipo = fields.Selection(TIPO_EVENTO, 'Evento', required=True)
    name = fields.Char('Descripción')
    aplica = fields.Boolean('Aplica', default=True)
    fecha_oficial = fields.Datetime('Fecha oficial')
    anticipacion_horas = fields.Float('Anticipación (h)', help='Horas antes de la fecha oficial para el límite interno.')
    fecha_limite_interna = fields.Datetime(
        'Fecha límite interna', compute='_compute_limite', store=True, readonly=False)
    fuente = fields.Char('Fuente')
    nota = fields.Char('Nota')
    calendar_event_id = fields.Many2one('calendar.event', 'Evento de calendario', readonly=True)
    activity_id = fields.Many2one('mail.activity', 'Actividad', readonly=True)
    hecho = fields.Boolean('Hecho', help='Se marca al completar la actividad del límite interno.')
    aviso_enviado = fields.Boolean('Aviso previo enviado', readonly=True, copy=False)
    escalado = fields.Boolean('Escalado a Gerencia', readonly=True, copy=False)
    dias_restantes = fields.Integer('Días restantes', compute='_compute_dias_restantes')
    cae_fin_semana = fields.Boolean('Límite en fin de semana', compute='_compute_cae_fin_semana', store=True)
    origen = fields.Selection([('licia', 'LICIA'), ('manual', 'Manual')], default='manual', readonly=True)

    @api.depends('fecha_oficial', 'anticipacion_horas', 'tipo')
    def _compute_limite(self):
        for ev in self:
            if ev.tipo not in EVENTOS_ACCION:
                ev.fecha_limite_interna = False  # evento informativo: sin límite interno
            elif ev.fecha_oficial and ev.anticipacion_horas:
                ev.fecha_limite_interna = ev.fecha_oficial - timedelta(hours=ev.anticipacion_horas)
            elif not ev.fecha_limite_interna:
                ev.fecha_limite_interna = ev.fecha_oficial

    @api.depends('fecha_limite_interna')
    def _compute_cae_fin_semana(self):
        for ev in self:
            if ev.fecha_limite_interna:
                local = fields.Datetime.context_timestamp(
                    ev.with_context(tz=ev.lead_id._stn_tz() if ev.lead_id else 'America/Mexico_City'),
                    ev.fecha_limite_interna)
                ev.cae_fin_semana = local.weekday() >= 5
            else:
                ev.cae_fin_semana = False

    @api.depends('fecha_oficial')
    def _compute_dias_restantes(self):
        hoy = fields.Date.context_today(self)
        for ev in self:
            ev.dias_restantes = (fields.Date.to_date(ev.fecha_oficial) - hoy).days if ev.fecha_oficial else 0

    def write(self, vals):
        cambio_fecha = {'fecha_oficial', 'fecha_limite_interna', 'anticipacion_horas'} & set(vals)
        if not cambio_fecha:
            return super().write(vals)
        # Solo cuenta como cambio si el valor realmente es otro: LICIA reenvía las mismas fechas cada día.
        nuevos = {}
        for k in cambio_fecha:
            v = vals[k]
            nuevos[k] = fields.Datetime.to_datetime(v) if k != 'anticipacion_horas' else float(v or 0.0)
        cambiados = self.filtered(lambda ev: any(
            (abs((ev[k] or 0.0) - nuevos[k]) > 0.001) if k == 'anticipacion_horas' else (ev[k] != (nuevos[k] or False))
            for k in cambio_fecha))
        if not self.env.context.get('stn_sin_historial') and 'fecha_oficial' in vals:
            for ev in cambiados:
                if ev.fecha_oficial and nuevos['fecha_oficial'] and nuevos['fecha_oficial'] != ev.fecha_oficial:
                    self.env['stn.licitacion.cambio'].create({
                        'lead_id': ev.lead_id.id, 'fecha': fields.Date.context_today(ev),
                        'campo': dict(TIPO_EVENTO).get(ev.tipo),
                        'antes': ev._stn_local(ev.fecha_oficial),
                        'despues': ev._stn_local(nuevos['fecha_oficial']),
                        'fuente': self.env.context.get('stn_fuente_cambio') or _('Captura manual')})
        res = super().write(vals)
        if cambiados:
            # Fecha nueva → el aviso y el escalamiento vuelven a correr (una vez) para esa fecha.
            super(StnLicitacionEvento, cambiados).write({'aviso_enviado': False, 'escalado': False})
            cambiados._stn_sincronizar_agenda()
        return res

    def _stn_requiere_limite(self):
        """¿Este evento lleva límite interno, actividad, aviso y escalamiento?"""
        self.ensure_one()
        if self.tipo not in EVENTOS_ACCION:
            return False
        if self.tipo in EVENTOS_PREPARACION and self.lead_id.stage_id.stn_codigo not in ETAPAS_APROBADAS:
            return False
        return True

    def _stn_local(self, dt):
        if not dt:
            return ''
        tz = self.lead_id._stn_tz() if self.lead_id else 'America/Mexico_City'
        return fields.Datetime.context_timestamp(self.with_context(tz=tz), dt).strftime('%Y-%m-%d %H:%M')

    def _stn_sincronizar_agenda(self):
        """Evento de calendario (fecha oficial) + actividad con responsable (fecha límite interna).

        El evento de calendario se liga a la oportunidad solo por `opportunity_id`, para que
        no genere una actividad propia: la actividad que cuenta es la del límite interno,
        que es la que se avisa antes y se escala a Gerencia si vence sin hacerse.
        """
        Calendar = self.env['calendar.event'].sudo()
        ahora = fields.Datetime.now()
        for ev in self:
            requiere = ev._stn_requiere_limite()
            if not requiere and ev.activity_id:
                ev.activity_id.with_context(stn_sin_hecho=True).unlink()  # informativo o aún sin aprobar
            if (not ev.aplica or not ev.fecha_oficial or ev.tipo == 'publicacion' or ev.hecho
                    or ev.lead_id.won_status == 'lost' or not ev.lead_id.active):
                continue
            limite = ev.fecha_limite_interna or ev.fecha_oficial
            if ev.fecha_oficial < ahora and limite < ahora:
                continue  # evento pasado: no se agenda ni se genera recordatorio
            evento = dict(TIPO_EVENTO).get(ev.tipo)
            nombre = '%s · %s' % (evento, ev.lead_id.stn_no_procedimiento or ev.lead_id.name)
            responsable = ev.lead_id.user_id
            if ev.fecha_oficial >= ahora:
                vals_cal = {
                    'name': nombre, 'start': ev.fecha_oficial, 'stop': ev.fecha_oficial + timedelta(hours=1),
                    'opportunity_id': ev.lead_id.id, 'description': ev.nota or '',
                }
                if responsable:
                    vals_cal.update(user_id=responsable.id, partner_ids=[(4, responsable.partner_id.id)])
                if ev.calendar_event_id:
                    ev.calendar_event_id.write({k: v for k, v in vals_cal.items() if k in ('name', 'start', 'stop')})
                else:
                    ev.calendar_event_id = Calendar.with_context(
                        no_mail_to_attendees=True, default_res_model=False, default_res_model_id=False,
                        default_opportunity_id=False).create(vals_cal)
            if not requiere:
                continue
            if responsable and limite >= ahora:
                resumen = _('Límite interno: %s', evento)
                if ev.cae_fin_semana:
                    resumen += _(' (cae en fin de semana)')
                nota = _('Fecha oficial: %(oficial)s · Límite interno: %(limite)s',
                         oficial=ev._stn_local(ev.fecha_oficial), limite=ev._stn_local(limite))
                if ev.activity_id.exists():
                    ev.activity_id.write({'date_deadline': fields.Date.to_date(limite), 'summary': resumen,
                                          'note': nota, 'user_id': responsable.id})
                else:
                    ev.activity_id = ev.lead_id.activity_schedule(
                        'mail.mail_activity_data_todo', date_deadline=fields.Date.to_date(limite),
                        summary=resumen, user_id=responsable.id, note=nota)

    @api.model
    def _cron_stn_avisos(self):
        """Aviso previo al responsable y escalamiento a Gerencia (Contexto y glosario v2, §4).

        Cada fecha se avisa una sola vez y se escala una sola vez. Solo cuentan los eventos que
        exigen acción (ver EVENTOS_ACCION); los de preparación, hasta que la licitación se aprueba.
        Si la fecha oficial ya pasó, ya no se escala: el evento quedó atrás.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        dias = int(ICP.get_param('stn_licitaciones.dias_aviso', 2) or 2)
        ahora = fields.Datetime.now()
        eventos = self.search([('aplica', '=', True), ('hecho', '=', False), ('fecha_limite_interna', '!=', False),
                               ('tipo', 'in', list(EVENTOS_ACCION)),
                               '|', ('aviso_enviado', '=', False), ('escalado', '=', False),
                               ('lead_id.active', '=', True), ('lead_id.won_status', '!=', 'lost')])
        silencio = self.with_context(stn_sin_historial=True)
        for ev in eventos:
            if not ev._stn_requiere_limite():
                continue
            lead = ev.lead_id
            evento = dict(TIPO_EVENTO).get(ev.tipo)
            if not ev.aviso_enviado and ahora <= ev.fecha_limite_interna <= ahora + timedelta(days=dias):
                lead.message_post(
                    body=_('Aviso: el límite interno de «%(ev)s» es %(lim)s (fecha oficial %(of)s).',
                           ev=evento, lim=ev._stn_local(ev.fecha_limite_interna), of=ev._stn_local(ev.fecha_oficial)),
                    partner_ids=lead.user_id.partner_id.ids, message_type='comment',
                    subtype_xmlid='mail.mt_comment')
                silencio.browse(ev.id).write({'aviso_enviado': True})
            if not ev.escalado and ev.fecha_limite_interna < ahora:
                if not ev.fecha_oficial or ev.fecha_oficial >= ahora:
                    resumen = _('VENCIDO sin atender: %s', evento)
                    abiertas = lead.activity_ids.filtered(lambda a: a.summary == resumen)
                    for user in lead.company_id.stn_usuarios_gerencia_ids - abiertas.user_id:
                        lead.activity_schedule(
                            'mail.mail_activity_data_todo', date_deadline=fields.Date.context_today(ev),
                            summary=resumen, user_id=user.id,
                            note=_('El límite interno %(lim)s pasó y la actividad del responsable (%(resp)s) '
                                   'sigue abierta. Fecha oficial: %(of)s.',
                                   lim=ev._stn_local(ev.fecha_limite_interna), resp=lead.user_id.name or '-',
                                   of=ev._stn_local(ev.fecha_oficial)))
                silencio.browse(ev.id).write({'escalado': True})


class StnLicitacionCambio(models.Model):
    _name = 'stn.licitacion.cambio'
    _description = 'Historial de cambios de fecha y estatus'
    _order = 'fecha desc, id desc'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    fecha = fields.Date('Detectado')
    campo = fields.Char('Qué cambió')
    antes = fields.Char('Antes')
    despues = fields.Char('Después')
    fuente = fields.Char('Fuente')


class StnLicitacionPregunta(models.Model):
    _name = 'stn.licitacion.pregunta'
    _description = 'Pregunta de junta de aclaraciones'
    _order = 'numero, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    numero = fields.Integer('#')
    pregunta = fields.Text('Pregunta', required=True)
    numeral = fields.Char('Numeral / referencia')
    estado = fields.Selection([
        ('sugerida', 'Sugerida'), ('enviada', 'Enviada'), ('respondida', 'Respondida'), ('descartada', 'Descartada')],
        default='sugerida')
    estado_detalle = fields.Char('Detalle del estado')
    respuesta = fields.Text('Respuesta')


class StnLicitacionPartida(models.Model):
    _name = 'stn.licitacion.partida'
    _description = 'Partida (unidad / lote) de la licitación'
    _order = 'numero, clave, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    company_currency = fields.Many2one(related='lead_id.company_currency')
    numero = fields.Integer('Orden', help='Para ordenar; la clave visible es «Partida».')
    clave = fields.Char('Partida', help='Clave de la partida o grupo como aparece en la convocatoria (1, G3, G7A…).')
    unidad = fields.Char('Unidad')
    municipio = fields.Char('Municipio')
    domicilio = fields.Char('Domicilio (anexo)')
    domicilio_alterno = fields.Char('Domicilio (apéndice)')
    domicilio_inconsistente = fields.Boolean('Domicilios no cuadran')
    partner_entrega_id = fields.Many2one('res.partner', 'Dirección de entrega',
                                         help='Se liga al ganar, para órdenes de suministro y proyecto.')
    corredor = fields.Char('Corredor / zona')
    vehiculos = fields.Char('Vehículos exigidos')
    cedis = fields.Char('CEDIS más cercano · km')
    minimo = fields.Monetary('Mínimo', currency_field='company_currency')
    maximo = fields.Monetary('Máximo', currency_field='company_currency')
    maximo_estimado = fields.Boolean('Máximo estimado', help='El máximo es estimación de LICIA, no dato oficial.')
    maximo_anterior = fields.Monetary('Máximo licitación anterior', currency_field='company_currency')
    ganador_anterior_id = fields.Many2one('res.partner', 'Ganador anterior')
    suma_precios_ganador = fields.Monetary('Suma de precios del ganador', currency_field='company_currency')
    nuestra_suma_precios = fields.Monetary('Nuestra suma de precios', currency_field='company_currency')
    diferencia_pct = fields.Float('Nosotros vs. ganador (%)', compute='_compute_diferencia_pct', store=True,
                                  aggregator='avg')
    lugar_precios = fields.Char('Lugar en precios')
    participamos = fields.Selection([('por_decidir', 'Por decidir'), ('si', 'Sí'), ('no', 'No')],
                                    '¿Participamos?', default='por_decidir')
    ganada = fields.Selection([('na', 'N/A'), ('si', 'Sí'), ('no', 'No')], '¿Ganada?', default='na')
    monto_ofertado = fields.Monetary('Monto ofertado', currency_field='company_currency')
    monto_adjudicado = fields.Monetary('Monto adjudicado', currency_field='company_currency')
    nota = fields.Char('Nota')
    renglon_ids = fields.One2many('stn.licitacion.renglon', 'partida_id', 'Renglones')
    renglon_count = fields.Integer(compute='_compute_renglon_count', string='# Renglones')
    sede_ids = fields.Many2many('stn.licitacion.sede', string='Sedes', compute='_compute_sede_ids',
                                help='Sedes que atienden esta partida (la logística vive en la sede).')

    def _compute_sede_ids(self):
        for p in self:
            clave = clave_partida(p.clave or p.numero)
            p.sede_ids = p.lead_id.stn_sede_ids.filtered(lambda s: clave in lista_claves(s.partidas))

    def _stn_tiene_decision_equipo(self):
        """Resultados que captura el equipo y que una ficha nueva no debe borrar."""
        self.ensure_one()
        return self.ganada in ('si', 'no') or bool(self.monto_adjudicado) or bool(self.nuestra_suma_precios) \
            or bool(self.monto_ofertado) or bool(self.partner_entrega_id)

    @api.depends('suma_precios_ganador', 'nuestra_suma_precios')
    def _compute_diferencia_pct(self):
        for p in self:
            p.diferencia_pct = ((p.nuestra_suma_precios / p.suma_precios_ganador - 1) * 100
                                if p.suma_precios_ganador and p.nuestra_suma_precios else 0.0)

    def _compute_renglon_count(self):
        for p in self:
            p.renglon_count = len(p.renglon_ids)

    @api.depends('numero', 'unidad')
    def _compute_display_name(self):
        for p in self:
            p.display_name = '%s %s' % (p.clave or 'P%s' % p.numero, p.unidad or '')

    def action_ver_renglones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Renglones %s', self.display_name),
            'res_model': 'stn.licitacion.renglon',
            'view_mode': 'list,form',
            'domain': [('partida_id', '=', self.id)],
            'context': {'default_partida_id': self.id},
        }


class StnLicitacionSede(models.Model):
    """Sede / unidad de entrega con su logística (una línea por unidad)."""
    _name = 'stn.licitacion.sede'
    _description = 'Sede y logística de la licitación'
    _order = 'id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    unidad = fields.Char('Unidad', required=True)
    partidas = fields.Char('Partidas que atiende')
    municipio = fields.Char('Municipio')
    domicilio = fields.Char('Domicilio (anexo)')
    domicilio_alterno = fields.Char('Domicilio (apéndice)')
    domicilio_inconsistente = fields.Boolean('Domicilios no cuadran')
    corredor = fields.Char('Corredor / zona')
    vehiculos = fields.Char('Vehículos exigidos')
    cedis = fields.Char('CEDIS más cercano · km')
    horario = fields.Char('Horario de entrega')
    partner_entrega_id = fields.Many2one('res.partner', 'Dirección de entrega',
                                         help='Se liga al ganar, para órdenes de suministro.')
    nota = fields.Char('Nota')
    origen = fields.Selection([('licia', 'LICIA'), ('manual', 'Manual')], default='manual', readonly=True)


class StnLicitacionRenglon(models.Model):
    """Producto dentro de una partida: base para nombre contractual y precio fijo."""
    _name = 'stn.licitacion.renglon'
    _description = 'Renglón (producto) de partida'
    _order = 'partida_id, numero, id'

    partida_id = fields.Many2one('stn.licitacion.partida', required=True, ondelete='cascade', index=True)
    lead_id = fields.Many2one(related='partida_id.lead_id', store=True, index=True)
    company_currency = fields.Many2one(related='partida_id.company_currency')
    numero = fields.Integer('Renglón')
    product_id = fields.Many2one('product.product', 'Producto base')
    nombre_contractual = fields.Char('Nombre contractual', required=True)
    clave = fields.Char('Clave / CUCoP')
    unidad_medida = fields.Char('Unidad de medida')
    cantidad_minima = fields.Float('Cantidad mínima')
    cantidad_maxima = fields.Float('Cantidad máxima')
    precio_unitario = fields.Monetary('Precio unitario', currency_field='company_currency')
    adjudicado = fields.Boolean('Adjudicado')


class StnLicitacionRequisito(models.Model):
    """Requisito de una licitación (antes x_crm_lead_line_265ca en Studio).

    Se liga opcionalmente al documento maestro (`stn.requisito`) para
    traer su vigencia y semáforo.
    """
    _name = 'stn.licitacion.requisito'
    _description = 'Requisito por licitación'
    _order = 'sequence, id'

    lead_id = fields.Many2one('crm.lead', 'Licitación', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('Secuencia', default=10)
    name = fields.Char('Descripción del requisito', required=True)
    referencia = fields.Char('Referencia / numeral')
    tipo = fields.Selection(TIPO_REQUISITO, 'Tipo')
    tipo_detalle = fields.Char('Tipo (texto LICIA)')
    situacion = fields.Selection(SITUACION, 'Situación')
    situacion_detalle = fields.Char('Situación (detalle)')
    efecto = fields.Char('Efecto si falta', help='Ej. DESECHA, Cumplimiento, sin puntos, condición.')
    nota = fields.Char('Nota de LICIA', help='Detalle de la situación, p. ej. «acuse 29-jul: ¿socios vigentes?».')
    desecha = fields.Boolean('Desecha', compute='_compute_desecha', store=True)
    vigencia_maxima = fields.Char('Vigencia máxima exigida')
    partner_id = fields.Many2one('res.partner', 'Cliente', related='lead_id.partner_id', store=True)
    state_id = fields.Many2one('res.country.state', 'Estado', related='lead_id.state_id', store=True)
    tipo_servicio_id = fields.Many2one('stn.tipo.servicio', 'Tipo de servicio')
    categoria_id = fields.Many2one('stn.requisito.categoria', 'Categoría')
    requisito_id = fields.Many2one('stn.requisito', 'Documento maestro')
    responsable_id = fields.Many2one(related='requisito_id.user_id', string='Responsable')
    proveedor_id = fields.Many2one(related='requisito_id.proveedor_id', string='Proveedor')
    etapa_id = fields.Many2one(related='requisito_id.stage_id', string='Estatus')
    estado_kanban = fields.Selection(related='requisito_id.kanban_state', string='Estado del documento')
    fecha_emision = fields.Date(related='requisito_id.fecha_emision')
    fecha_vencimiento = fields.Date(related='requisito_id.fecha_vencimiento')
    fecha_recomendada_renovacion = fields.Date(related='requisito_id.fecha_recomendada_renovacion')
    notas = fields.Html(related='requisito_id.notes', string='Notas')
    extracto_literal = fields.Text('Extracto literal', help='Texto del requisito tal como aparece en la convocatoria.')
    captura = fields.Image('Captura del requisito', max_width=1600, max_height=1600)
    antiguedad_max_dias = fields.Integer(
        'Antigüedad máxima (días)', help='Antigüedad máxima que exige esta convocatoria; 0 = solo vigente.')
    fecha_referencia = fields.Date(
        'Medir contra', compute='_compute_fecha_referencia', store=True, readonly=False,
        help='Fecha contra la que se mide la vigencia (normalmente la apertura). Si la apertura se difiere, se recalcula.')
    semaforo = fields.Selection([
        ('verde', 'Verde · sirve'), ('amarillo', 'Amarillo · margen corto'),
        ('naranja', 'Naranja · iniciar trámite'), ('rojo', 'Rojo · riesgo de incumplir'),
        ('na', 'Sin documento ligado')], 'Semáforo', compute='_compute_semaforo', store=True)
    semaforo_detalle = fields.Char('Detalle del semáforo', compute='_compute_semaforo', store=True)
    origen = fields.Selection([('licia', 'LICIA'), ('manual', 'Manual')], default='manual', readonly=True)
    # Avance de la propuesta (pestaña de ComprasMX y orden de casilla)
    pestana = fields.Selection(PESTANA, 'Pestaña', help='Pestaña de «Mi proposición» en ComprasMX donde se sube.')
    orden_casilla = fields.Char('Casilla', help='Orden de la casilla en ComprasMX: 1, 2… o con subíndice 1.1, 1.2.')
    orden_clave = fields.Integer('Orden', compute='_compute_orden_clave', store=True)
    avance = fields.Selection(AVANCE, 'Avance', default='falta', required=True,
                              help='Avance de la propuesta en este requisito (lo marca el equipo o la revisión de LEXA).')
    archivo_ids = fields.Many2many('ir.attachment', 'stn_requisito_archivo_rel', 'requisito_id', 'attachment_id',
                                   string='Nuestros archivos', help='Documento(s) que preparó el equipo para este requisito.')

    @api.depends('orden_casilla', 'pestana')
    def _compute_orden_clave(self):
        """Orden de lectura: pestaña (legal, técnica, económica) y luego casilla de ComprasMX."""
        rango = {codigo: i for i, (codigo, _n) in enumerate(PESTANA, 1)}
        for r in self:
            r.orden_clave = rango.get(r.pestana, 9) * 1000000 + clave_orden_casilla(r.orden_casilla)

    @api.onchange('tipo')
    def _onchange_tipo_pestana(self):
        if self.tipo and not self.pestana:
            self.pestana = PESTANA_POR_TIPO.get(self.tipo)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('pestana') and vals.get('tipo'):
                vals['pestana'] = PESTANA_POR_TIPO.get(vals['tipo'])
            if vals.get('situacion') == 'no_aplica' and 'avance' not in vals:
                vals['avance'] = 'no_aplica'
        recs = super().create(vals_list)
        recs._stn_ligar_archivos()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if 'archivo_ids' in vals:
            self._stn_ligar_archivos()
        return res

    def _stn_ligar_archivos(self):
        for r in self:
            r.archivo_ids.filtered(lambda a: not a.res_id).sudo().write({'res_model': 'crm.lead', 'res_id': r.lead_id.id})

    @api.depends('lead_id.stn_fecha_apertura')
    def _compute_fecha_referencia(self):
        for r in self:
            r.fecha_referencia = fields.Date.to_date(r.lead_id.stn_fecha_apertura) if r.lead_id.stn_fecha_apertura \
                else r.fecha_referencia

    @api.depends('requisito_id.fecha_emision', 'requisito_id.fecha_vencimiento', 'requisito_id.dias_tramite',
                 'antiguedad_max_dias', 'fecha_referencia')
    def _compute_semaforo(self):
        """Semáforo por licitación (glosario §4): un documento vigente en el catálogo puede
        no servir para esta apertura por la antigüedad máxima que exige la convocatoria."""
        hoy = fields.Date.context_today(self)
        for r in self:
            doc = r.requisito_id
            ref = r.fecha_referencia
            if not doc or not ref:
                r.semaforo, r.semaforo_detalle = 'na', (_('Sin documento ligado') if not doc else _('Sin fecha de referencia'))
                continue
            sirve = bool(doc.fecha_emision) and (not doc.fecha_vencimiento or doc.fecha_vencimiento >= ref)
            if sirve and r.antiguedad_max_dias:
                sirve = (ref - doc.fecha_emision).days <= r.antiguedad_max_dias
            dias_para_ref = (ref - hoy).days
            tramite = doc.dias_tramite or 0
            if sirve:
                margen = (doc.fecha_vencimiento - ref).days if doc.fecha_vencimiento else 999
                if r.antiguedad_max_dias:
                    margen = min(margen, r.antiguedad_max_dias - (ref - doc.fecha_emision).days)
                r.semaforo = 'amarillo' if margen <= 7 else 'verde'
                r.semaforo_detalle = _('Sirve para la fecha %(ref)s · margen %(m)s días', ref=ref, m=margen)
            elif dias_para_ref >= tramite:
                r.semaforo = 'naranja'
                r.semaforo_detalle = _('No sirve para %(ref)s: iniciar trámite (quedan %(d)s días, trámite %(t)s)',
                                       ref=ref, d=dias_para_ref, t=tramite)
            else:
                r.semaforo = 'rojo'
                r.semaforo_detalle = _('No sirve para %(ref)s y no alcanza el tiempo de trámite (%(d)s de %(t)s días)',
                                       ref=ref, d=dias_para_ref, t=tramite)

    @api.model
    def _cron_stn_semaforo(self):
        self.search([('lead_id.active', '=', True)])._compute_semaforo()

    @api.depends('efecto')
    def _compute_desecha(self):
        for r in self:
            r.desecha = bool(r.efecto and 'desecha' in r.efecto.lower() and 'no desecha' not in r.efecto.lower())

    @api.onchange('requisito_id')
    def _onchange_requisito_id(self):
        if self.requisito_id and not self.categoria_id:
            self.categoria_id = self.requisito_id.categoria_id


class StnLicitacionPunto(models.Model):
    _name = 'stn.licitacion.punto'
    _description = 'Rubro de evaluación por puntos'
    _order = 'sequence, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    rubro = fields.Char('Rubro · subrubro', required=True)
    puntos = fields.Float('Puntos máximos')
    puntos_esperados = fields.Float('Puntos esperados')
    entregable = fields.Char('Qué se entrega')
    situacion = fields.Selection(SITUACION, 'Situación')
    situacion_detalle = fields.Char('Situación (detalle)')


class StnLicitacionAntecedente(models.Model):
    _name = 'stn.licitacion.antecedente'
    _description = 'Licitación anterior / antecedente'
    _order = 'id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    company_currency = fields.Many2one(related='lead_id.company_currency')
    procedimiento = fields.Char('Procedimiento', required=True)
    lead_anterior_id = fields.Many2one('crm.lead', 'Oportunidad anterior en Odoo')
    participamos = fields.Boolean('¿Participó el grupo?')
    criterio = fields.Char('Criterio usado')
    participantes = fields.Text('Participantes y puntajes')
    razon_mismo = fields.Text('Por qué es el mismo')
    ganador_id = fields.Many2one('res.partner', 'Ganador')
    puntos_ganador = fields.Float('Puntos técnicos del ganador')
    contrato = fields.Char('Contrato')
    como_gano = fields.Text('Cómo ganó')
    precio_a_vencer = fields.Char('Precio a vencer')
    monto_maximo = fields.Monetary('Monto máximo', currency_field='company_currency')
    vigencia = fields.Char('Vigencia')
    desiertas = fields.Char('Procedimientos desiertos')
    hipotesis = fields.Text('Hipótesis')


class StnLicitacionCompetidor(models.Model):
    _name = 'stn.licitacion.competidor'
    _description = 'Competidor en la unidad compradora'
    _order = 'id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', 'Competidor', required=True)
    historia = fields.Text('Historia en esta unidad compradora')
    lectura = fields.Text('Lectura de LICIA')
    rol = fields.Selection([('incumbente', 'Incumbente'), ('entrante', 'Entrante'), ('ocasional', 'Ocasional'),
                            ('otro', 'Otro')], 'Rol')


class StnLicitacionPendiente(models.Model):
    """Pendientes que se activan al ganar (firma, garantía, constancias)."""
    _name = 'stn.licitacion.pendiente'
    _description = 'Pendiente posterior al fallo'
    _order = 'fecha, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    name = fields.Char('Pendiente', required=True)
    plazo = fields.Char('Plazo')
    fecha = fields.Date('Fecha calculada')
    fecha_detalle = fields.Char('Fecha (texto)')
    fuente = fields.Char('Fuente')
    estado = fields.Selection([('espera', 'Se activa al ganar'), ('activo', 'Activo'), ('hecho', 'Hecho'),
                               ('cancelado', 'Cancelado')], default='espera')
    activity_id = fields.Many2one('mail.activity', readonly=True)

    def _stn_activar(self):
        for p in self.filtered(lambda x: x.estado == 'espera'):
            user = p.lead_id.user_id or self.env.user
            p.activity_id = p.lead_id.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=p.fecha or fields.Date.context_today(p),
                summary=p.name, user_id=user.id,
                note=' · '.join(filter(None, [p.plazo, p.fuente])))
            p.estado = 'activo'


class StnLicitacionSeguimiento(models.Model):
    _name = 'stn.licitacion.seguimiento'
    _description = 'Seguimiento diario de LICIA'
    _order = 'fecha desc, id desc'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    fecha = fields.Char('Fecha')
    texto = fields.Text('Seguimiento', required=True)
    message_id = fields.Many2one('mail.message', readonly=True)


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def _stn_marcar_eventos_hechos(self):
        if self and not self.env.context.get('stn_sin_hecho'):
            eventos = self.env['stn.licitacion.evento'].sudo().search([('activity_id', 'in', self.ids)])
            eventos.with_context(stn_sin_historial=True).write({'hecho': True})

    def _action_done(self, *args, **kwargs):
        """Al marcar hecha la actividad del límite interno, el evento queda atendido y ya no se recrea."""
        self._stn_marcar_eventos_hechos()
        return super()._action_done(*args, **kwargs)

    def unlink(self):
        self._stn_marcar_eventos_hechos()
        return super().unlink()
