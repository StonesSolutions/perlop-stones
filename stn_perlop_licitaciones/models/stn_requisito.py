from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class StnRequisito(models.Model):
    """Documento maestro de la empresa (antes x_requisitos en Studio).

    Cada documento tiene emisión, vigencia y tiempo de trámite; un cron
    diario recalcula días restantes y etapa del semáforo y avisa al
    responsable cuando hay que iniciar la renovación.
    """
    _name = 'stn.requisito'
    _description = 'Requisito / documento de la empresa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, sequence, id desc'

    name = fields.Char('Descripción', required=True, tracking=True)
    sequence = fields.Integer('Secuencia', default=10)
    active = fields.Boolean('Activo', default=True)
    color = fields.Integer('Color')
    priority = fields.Boolean('Alta prioridad')
    categoria_id = fields.Many2one('stn.requisito.categoria', 'Categoría', tracking=True)
    tipo_servicio_ids = fields.Many2many('stn.tipo.servicio', string='Aplica a tipos de servicio')
    user_id = fields.Many2one('res.users', 'Responsable', default=lambda s: s.env.user, tracking=True)
    proveedor_id = fields.Many2one('res.partner', 'Proveedor / gestor', tracking=True)
    company_id = fields.Many2one('res.company', 'Compañía', default=lambda s: s.env.company)
    notes = fields.Html('Notas')

    fecha_emision = fields.Date('Fecha de emisión', tracking=True)
    vigencia_meses = fields.Integer('Vigencia (meses)', help='0 = sin vencimiento.', tracking=True)
    fecha_vencimiento = fields.Date(
        'Fecha de vencimiento', compute='_compute_fecha_vencimiento', store=True, readonly=False, tracking=True)
    dias_tramite = fields.Integer(
        'Tiempo mínimo para renovar (días)', default=30,
        help='Días que toma el trámite de renovación; se usa para anticipar la alerta.')
    fecha_recomendada_renovacion = fields.Date(
        'Fecha recomendada de renovación', compute='_compute_fecha_recomendada', store=True, readonly=False)
    dias_restantes = fields.Integer('Días restantes', readonly=True,
                                    help='Se actualiza diariamente.')
    stage_id = fields.Many2one(
        'stn.requisito.etapa', 'Etapa', tracking=True, group_expand='_read_group_stage_ids',
        default=lambda s: s.env['stn.requisito.etapa'].search([('code', '=', 'en_tramite')], limit=1))
    stage_code = fields.Selection(related='stage_id.code', store=True, string='Semáforo')
    kanban_state = fields.Selection([
        ('normal', 'En progreso'), ('done', 'Listo'), ('blocked', 'Bloqueado')],
        'Estado de kanban', default='normal')
    attachment_ids = fields.Many2many('ir.attachment', string='Documento vigente')
    linea_ids = fields.One2many('stn.licitacion.requisito', 'requisito_id', 'Usado en licitaciones')
    linea_count = fields.Integer(compute='_compute_linea_count')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([])

    @api.depends('fecha_emision', 'vigencia_meses')
    def _compute_fecha_vencimiento(self):
        for rec in self:
            if rec.fecha_emision and rec.vigencia_meses:
                rec.fecha_vencimiento = rec.fecha_emision + relativedelta(months=rec.vigencia_meses)
            elif not rec.vigencia_meses:
                rec.fecha_vencimiento = rec.fecha_vencimiento or False

    @api.depends('fecha_vencimiento', 'dias_tramite')
    def _compute_fecha_recomendada(self):
        for rec in self:
            rec.fecha_recomendada_renovacion = (
                rec.fecha_vencimiento - relativedelta(days=rec.dias_tramite or 0)
                if rec.fecha_vencimiento else False)

    def _compute_linea_count(self):
        for rec in self:
            rec.linea_count = len(rec.linea_ids)

    # ------------------------------------------------------------------
    # Semáforo
    # ------------------------------------------------------------------
    def _stn_codigo_semaforo(self, hoy):
        self.ensure_one()
        if self.stage_code == 'en_tramite' and not self.fecha_emision:
            return 'en_tramite'
        if not self.fecha_vencimiento:
            return 'sin_vencimiento' if self.fecha_emision else 'en_tramite'
        if hoy > self.fecha_vencimiento:
            return 'vencido'
        if self.fecha_recomendada_renovacion and hoy >= self.fecha_recomendada_renovacion:
            return 'proximo'
        return 'vigente'

    def action_stn_actualizar_semaforo(self):
        hoy = fields.Date.context_today(self)
        etapas = {e.code: e for e in self.env['stn.requisito.etapa'].search([])}
        for rec in self:
            vals = {'dias_restantes': (rec.fecha_vencimiento - hoy).days if rec.fecha_vencimiento else 0}
            codigo = rec._stn_codigo_semaforo(hoy)
            etapa = etapas.get(codigo)
            if etapa and etapa != rec.stage_id:
                vals['stage_id'] = etapa.id
                if codigo in ('proximo', 'vencido') and rec.user_id:
                    rec.activity_schedule(
                        'mail.mail_activity_data_todo',
                        date_deadline=rec.fecha_vencimiento if codigo == 'proximo' else hoy,
                        summary=_('Renovar: %s', rec.name) if codigo == 'proximo' else _('VENCIDO: %s', rec.name),
                        user_id=rec.user_id.id)
            rec.write(vals)
        return True

    @api.model
    def _cron_stn_semaforo(self):
        self.search([]).action_stn_actualizar_semaforo()

    def action_view_lineas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Licitaciones que usan %s', self.name),
            'res_model': 'stn.licitacion.requisito',
            'view_mode': 'list,form',
            'domain': [('requisito_id', '=', self.id)],
        }
