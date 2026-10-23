import json
import logging

from odoo import http
from odoo.http import request
from odoo.tools import consteq

_logger = logging.getLogger(__name__)

P = 'stn_licitaciones.'


class StnLiciaController(http.Controller):
    """Entrada de LICIA a Odoo.

    Autenticación: encabezado `Authorization: Bearer <token>` (o `X-STN-Token`)
    con el token generado en Ajustes › CRM › LICIA. Las operaciones se
    ejecutan con el usuario técnico configurado como responsable por defecto
    (o el superusuario si no hay uno), nunca con el usuario público.
    """

    def _stn_auth(self):
        ICP = request.env['ir.config_parameter'].sudo()
        token = ICP.get_param(P + 'token') or ''
        if not token or not ICP.get_param(P + 'activo'):
            return None, (503, 'Integración LICIA inactiva o sin token.')
        recibido = request.httprequest.headers.get('Authorization', '')
        if recibido.lower().startswith('bearer '):
            recibido = recibido[7:].strip()
        recibido = recibido or request.httprequest.headers.get('X-STN-Token', '')
        if not recibido or not consteq(recibido, token):
            return None, (401, 'Token inválido.')
        uid = int(ICP.get_param(P + 'user_id', 0) or 0)
        user = request.env['res.users'].sudo().browse(uid).exists() if uid else None
        env = request.env(user=user.id) if user else request.env(su=True)
        return env, None

    def _json(self, data, status=200):
        return request.make_json_response(data, status=status)

    @http.route('/stn/licitaciones/ping', type='http', auth='none', methods=['GET'], csrf=False, save_session=False)
    def ping(self, **kw):
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        return self._json({'ok': True, 'base': env.cr.dbname, 'empresa': env.company.name})

    @http.route('/stn/licitaciones/parametros', type='http', auth='none', methods=['GET'], csrf=False,
                save_session=False)
    def parametros(self, **kw):
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        return self._json({'ok': True, **env['stn.licia.service'].stn_parametros()})

    @http.route('/stn/licitaciones/ficha', type='http', auth='none', methods=['POST'], csrf=False,
                save_session=False, readonly=False)
    def ficha(self, **kw):
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        Log = env['stn.licia.log'].sudo()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError as e:
            Log._stn_registrar('http', request.httprequest.get_data(as_text=True)[:5000], error='JSON inválido: %s' % e)
            return self._json({'ok': False, 'error': 'JSON inválido: %s' % e}, status=400)
        fichas = payload if isinstance(payload, list) else [payload]
        resultados = []
        for ficha in fichas:
            try:
                with env.cr.savepoint():
                    res = env['crm.lead'].stn_upsert_ficha(ficha, origen='http')
                Log._stn_registrar('http', ficha, res)
                base = env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
                res['url'] = '%s/odoo/crm/%s' % (base, res['lead_id'])
                resultados.append({'ok': True, **res})
            except Exception as e:  # noqa: BLE001
                _logger.exception('LICIA: error al procesar ficha')
                Log._stn_registrar('http', ficha, error=str(e))
                resultados.append({'ok': False, 'numero_procedimiento': (ficha or {}).get('numero_procedimiento')
                                   if isinstance(ficha, dict) else None, 'error': str(e)})
        status = 200 if all(r['ok'] for r in resultados) else (207 if any(r['ok'] for r in resultados) else 422)
        return self._json(resultados if isinstance(payload, list) else resultados[0], status=status)

    @http.route('/stn/licitaciones/reporte', type='http', auth='none', methods=['POST'], csrf=False,
                save_session=False, readonly=False)
    def reporte(self, **kw):
        """Reporte diario de LICIA (revisados, nuevos, nivel y recomendación)."""
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
            rep = env['stn.licia.reporte'].sudo().stn_registrar(payload)
            env['stn.licia.log'].sudo()._stn_registrar('http', payload, {'accion': 'reporte diario'})
            return self._json({'ok': True, 'reporte_id': rep.id, 'fecha': str(rep.fecha)})
        except Exception as e:  # noqa: BLE001
            _logger.exception('LICIA: error en reporte diario')
            env['stn.licia.log'].sudo()._stn_registrar('http', {}, error=str(e))
            return self._json({'ok': False, 'error': str(e)}, status=422)
