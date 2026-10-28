from odoo import _, api, fields, models

P = 'stn_licitaciones.'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ---------------- Flujo de licitaciones ----------------
    stn_team_id = fields.Many2one('crm.team', 'Equipo de licitaciones', config_parameter=P + 'team_id',
                                  domain=[('stn_es_licitacion', '=', True)])
    stn_user_id = fields.Many2one('res.users', 'Responsable por defecto', config_parameter=P + 'user_id')
    stn_nivel_analisis = fields.Integer('Nivel para pasar a análisis', default=4,
                                        config_parameter=P + 'nivel_analisis')
    stn_horas_limite_interna = fields.Float('Horas de anticipación (límite interno)', default=72,
                                            config_parameter=P + 'horas_limite_interna')
    stn_tz = fields.Char('Zona horaria de la ficha', default='America/Mexico_City', config_parameter=P + 'tz')
    stn_usuarios_nueva_ids = fields.Many2many(related='company_id.stn_usuarios_nueva_ids', readonly=False)
    stn_usuarios_analisis_ids = fields.Many2many(related='company_id.stn_usuarios_analisis_ids', readonly=False)
    stn_usuarios_gerencia_ids = fields.Many2many(related='company_id.stn_usuarios_gerencia_ids', readonly=False)
    stn_dias_aviso = fields.Integer('Días de aviso previo', default=2, config_parameter=P + 'dias_aviso')

    # ---------------- Parámetros de búsqueda para LICIA ----------------
    stn_licia_activo = fields.Boolean('Integración LICIA activa', config_parameter=P + 'activo')
    stn_palabras_clave = fields.Char('Palabras clave', config_parameter=P + 'palabras_clave',
                                     help='Separadas por coma. LICIA busca con y sin acento.')
    stn_nivel_minimo = fields.Integer('Nivel mínimo para enviar a Odoo', default=4,
                                      config_parameter=P + 'nivel_minimo')
    stn_instrucciones = fields.Char('Instrucciones adicionales para LICIA', config_parameter=P + 'instrucciones')
    stn_licia_estado_ids = fields.Many2many(related='company_id.stn_licia_estado_ids', readonly=False)
    stn_licia_tipo_servicio_ids = fields.Many2many(related='company_id.stn_licia_tipo_servicio_ids', readonly=False)
    stn_token = fields.Char('Token de entrada', config_parameter=P + 'token', groups='base.group_system')
    stn_endpoint_ficha = fields.Char('Endpoint de la ficha', compute='_compute_stn_endpoints')
    stn_endpoint_parametros = fields.Char('Endpoint de parámetros', compute='_compute_stn_endpoints')
    stn_alias_correo = fields.Char('Alias de correo', compute='_compute_stn_endpoints')

    # ---------------- Cuenta de Claude / agente ----------------
    stn_claude_modo = fields.Selection([
        ('recepcion', 'La búsqueda diaria la programa Claude (tarea programada)'),
        ('rutina_api', 'La búsqueda diaria la dispara Odoo (acción planificada)'),
    ], 'Búsqueda diaria', default='recepcion', config_parameter=P + 'claude_modo')
    stn_claude_agente = fields.Char('Nombre del agente', default='LICIA', config_parameter=P + 'claude_agente')
    stn_claude_cuenta = fields.Char('Cuenta de Claude', config_parameter=P + 'claude_cuenta',
                                    help='Correo de la cuenta claude.ai dueña de la rutina (referencia).')
    stn_claude_routine_url = fields.Char('URL del activador API', config_parameter=P + 'claude_routine_url',
                                         help='https://api.anthropic.com/v1/claude_code/routines/<id>/fire')
    stn_claude_routine_token = fields.Char('Token del activador API', config_parameter=P + 'claude_routine_token',
                                           groups='base.group_system')
    stn_claude_beta = fields.Char('Encabezado beta', default='experimental-cc-routine-2026-04-01',
                                  config_parameter=P + 'claude_beta')
    stn_claude_ultima_sesion = fields.Char('Última sesión disparada', config_parameter=P + 'claude_ultima_sesion',
                                           readonly=True)

    @api.depends('company_id')
    def _compute_stn_endpoints(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        team_id = int(self.env['ir.config_parameter'].sudo().get_param(P + 'team_id', 0) or 0)
        team = self.env['crm.team'].browse(team_id).exists()
        for rec in self:
            rec.stn_endpoint_ficha = base + '/stn/licitaciones/ficha'
            rec.stn_endpoint_parametros = base + '/stn/licitaciones/parametros'
            rec.stn_alias_correo = team.alias_email if team and 'alias_email' in team._fields else False

    def action_stn_generar_token(self):
        self.env['stn.licia.service']._generar_token()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_stn_disparar_rutina(self):
        self.execute()
        res = self.env['stn.licia.service'].stn_disparar_rutina(manual=True)
        url = res.get('claude_code_session_url') if isinstance(res, dict) else ''
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('LICIA'), 'type': 'success', 'sticky': bool(url),
                       'message': _('Rutina disparada. %s', url or '')},
        }

    def action_stn_ver_bitacora(self):
        return self.env['ir.actions.act_window']._for_xml_id('stn_perlop_licitaciones.action_stn_licia_log')
