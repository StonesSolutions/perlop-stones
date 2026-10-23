import json
import logging
import secrets

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ICP_PREFIX = 'stn_licitaciones.'


class StnLiciaService(models.AbstractModel):
    """Conexión con LICIA (agente en Claude).

    - Entrada: endpoint HTTP con token y alias de correo.
    - Salida: disparo de la rutina de Claude por API (POST /fire con token
      de la rutina), mandando los parámetros de búsqueda definidos en Odoo.
    """
    _name = 'stn.licia.service'
    _description = 'Servicio de integración LICIA / Claude'

    @api.model
    def _icp(self, clave, defecto=False):
        return self.env['ir.config_parameter'].sudo().get_param(ICP_PREFIX + clave, defecto)

    @api.model
    def _generar_token(self):
        token = secrets.token_urlsafe(32)
        self.env['ir.config_parameter'].sudo().set_param(ICP_PREFIX + 'token', token)
        return token

    @api.model
    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')

    @api.model
    def stn_parametros(self):
        """Lo que LICIA debe leer de Odoo antes de buscar (GET /stn/licitaciones/parametros)."""
        company = self.env.company
        Lead = self.env['crm.lead']
        seguimiento = Lead.search([
            ('stn_no_procedimiento', '!=', False), ('active', '=', True),
            ('stn_resultado', '=', 'pendiente'), ('team_id.stn_es_licitacion', '=', True)])
        return {
            'version_contrato': '1.0',
            'empresa': company.name,
            'palabras_clave': [p.strip() for p in (self._icp('palabras_clave') or '').split(',') if p.strip()],
            'estados_donde_operamos': company.stn_licia_estado_ids.mapped('name'),
            'segmentos': company.stn_licia_tipo_servicio_ids.mapped('name'),
            'nivel_minimo_para_enviar': int(self._icp('nivel_minimo', 4) or 4),
            'horas_limite_interna': float(self._icp('horas_limite_interna', 72) or 72),
            'instrucciones_adicionales': self._icp('instrucciones') or '',
            'endpoint_ficha': self._base_url() + '/stn/licitaciones/ficha',
            'procedimientos_en_seguimiento': [{
                'numero_procedimiento': l.stn_no_procedimiento,
                'estatus': l.stn_estatus_id.name or '',
                'etapa': l.stage_id.name or '',
                'fecha_apertura': fields.Datetime.context_timestamp(
                    l.with_context(tz=l._stn_tz()), l.stn_fecha_apertura).strftime('%Y-%m-%d %H:%M')
                if l.stn_fecha_apertura else '',
            } for l in seguimiento],
        }

    @api.model
    def stn_disparar_rutina(self, manual=True):
        url = self._icp('claude_routine_url')
        token = self._icp('claude_routine_token')
        if not url or not token:
            raise UserError(_('Configura la URL y el token de la rutina de Claude en Ajustes › CRM › LICIA.'))
        params = self.stn_parametros()
        texto = 'PARAMETROS_ODOO ' + json.dumps(params, ensure_ascii=False)
        headers = {
            'Authorization': 'Bearer %s' % token,
            'anthropic-beta': self._icp('claude_beta') or 'experimental-cc-routine-2026-04-01',
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json',
        }
        Log = self.env['stn.licia.log'].sudo()
        try:
            resp = requests.post(url, headers=headers, json={'text': texto}, timeout=30)
            cuerpo = resp.text[:4000]
            if resp.status_code >= 300:
                Log._stn_registrar('claude', {'url': url, 'status': resp.status_code}, error=cuerpo)
                if manual:
                    raise UserError(_('Claude respondió %(code)s: %(body)s', code=resp.status_code, body=cuerpo))
                return False
            datos = resp.json() if 'json' in resp.headers.get('Content-Type', '') else {}
            Log._stn_registrar('claude', {'url': url, 'respuesta': datos or cuerpo},
                               {'accion': 'rutina disparada',
                                'advertencias': [datos.get('claude_code_session_url', '')] if datos else []})
            self.env['ir.config_parameter'].sudo().set_param(ICP_PREFIX + 'claude_ultima_sesion',
                                                             datos.get('claude_code_session_url', '') if datos else '')
            return datos or True
        except requests.RequestException as e:
            Log._stn_registrar('claude', {'url': url}, error=str(e))
            if manual:
                raise UserError(_('No se pudo contactar a Claude: %s', e)) from e
            return False

    @api.model
    def _cron_disparar_rutina(self):
        if self._icp('claude_modo') == 'rutina_api':
            self.stn_disparar_rutina(manual=False)
