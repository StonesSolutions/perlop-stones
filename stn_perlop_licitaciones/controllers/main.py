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
        return self._stn_env(ICP), None

    def _stn_env(self, ICP):
        """Entorno con un usuario interno real: el responsable por defecto de Ajustes o,
        si no hay, el administrador. Sin usuario, Odoo no tiene empresa ni puede publicar
        mensajes (antes: «Expected singleton: res.users()»)."""
        Users = request.env['res.users'].sudo().with_context(active_test=False)
        uid = int(ICP.get_param(P + 'user_id', 0) or 0)
        user = Users.browse(uid).exists() if uid else Users.browse()
        if not user or not user.active:
            admin = request.env.ref('base.user_admin', raise_if_not_found=False)
            user = Users.browse(admin.id) if admin else Users.browse()
        if not user or not user.active:
            user = Users.search([('share', '=', False), ('active', '=', True),
                                 ('group_ids', 'in', request.env.ref('base.group_system').sudo().id)], limit=1)
        env = request.env(user=user.id, context=dict(request.env.context, allowed_company_ids=user.company_id.ids))
        return env

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

    # ------------------------------------------------------------------
    # Documentos de la convocatoria (subidos por el equipo en Odoo)
    # ------------------------------------------------------------------
    def _stn_lead(self, env, numero):
        return env['crm.lead'].sudo().with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', numero), ('team_id.stn_es_licitacion', '=', True)], limit=1)

    @http.route('/stn/licitaciones/documentos', type='http', auth='none', methods=['GET'], csrf=False,
                save_session=False)
    def documentos(self, numero=None, **kw):
        """Lista los documentos de una licitación para que LICIA los descargue."""
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        lead = self._stn_lead(env, numero or '')
        if not lead:
            return self._json({'ok': False, 'error': 'No existe la licitación %s.' % numero}, status=404)
        base = env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        return self._json({
            'ok': True,
            'numero_procedimiento': lead.stn_no_procedimiento,
            'nombre': lead.name,
            'url_ficha': lead.stn_url_ficha or '',
            'estado_analisis': lead.stn_analisis_estado,
            'documentos': [{
                'id': a.id, 'nombre': a.name, 'mimetype': a.mimetype, 'tamano': a.file_size,
                'url': '%s/stn/licitaciones/documento/%s' % (base, a.id),
            } for a in lead.stn_documento_ids.sudo()],
        })

    @http.route('/stn/licitaciones/documento/<int:attachment_id>', type='http', auth='none', methods=['GET'],
                csrf=False, save_session=False)
    def documento(self, attachment_id, **kw):
        """Descarga un documento, solo si pertenece a una licitación."""
        env, err = self._stn_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        att = env['ir.attachment'].sudo().browse(attachment_id).exists()
        lead = env['crm.lead'].sudo().with_context(active_test=False).search(
            [('stn_documento_ids', 'in', att.ids), ('team_id.stn_es_licitacion', '=', True)], limit=1) if att else None
        if not att or not lead:
            return self._json({'ok': False, 'error': 'Documento no encontrado.'}, status=404)
        nombre = (att.name or 'documento').replace('"', '')
        return request.make_response(att.raw or b'', headers=[
            ('Content-Type', att.mimetype or 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="%s"' % nombre),
        ])
