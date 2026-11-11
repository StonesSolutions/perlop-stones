import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.stn_perlop_licitaciones.controllers.main import StnLiciaController

_logger = logging.getLogger(__name__)

P = 'stn_lexa.'


class StnLexaController(StnLiciaController):
    """Entrada y salida de LEXA. Mismo esquema que LICIA (Bearer token), con token propio.

    - GET  /stn/lexa/ping
    - GET  /stn/lexa/pendientes            encargos que el equipo pidió con los botones
    - GET  /stn/lexa/expediente?numero=…   o ?encargo_id=… (lo marca «LEXA trabajando»)
    - GET  /stn/lexa/archivo/<id>          convocatoria, nuestros archivos, archivos de subida, matriz
    - POST /stn/lexa/encargo               matriz, revisión, casillas y faltantes (JSON lexa.encargo/1.0)
    """

    def _lexa_auth(self):
        return self._stn_auth(prefijo=P, agente='LEXA')

    def _lexa_lead(self, env, numero):
        return env['crm.lead'].sudo().with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', numero or ''), ('team_id.stn_es_licitacion', '=', True),
             ('stn_tipo_registro', '=', 'licitacion')], limit=1)

    @http.route('/stn/lexa/ping', type='http', auth='none', methods=['GET'], csrf=False, save_session=False)
    def lexa_ping(self, **kw):
        env, err = self._lexa_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        return self._json({'ok': True, 'agente': 'LEXA', 'base': env['ir.config_parameter'].sudo().get_param('web.base.url'),
                           'usuario': env.user.name, 'esquema': 'lexa.encargo/1.0'})

    @http.route('/stn/lexa/pendientes', type='http', auth='none', methods=['GET'], csrf=False, save_session=False)
    def lexa_pendientes(self, **kw):
        env, err = self._lexa_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        base = env['stn.lexa.service']._base_url()
        encargos = env['stn.lexa.encargo'].sudo().search([('estado', 'in', ['solicitado', 'requiere_regenerar'])],
                                                         order='id')
        return self._json({'ok': True, 'pendientes': [{
            'encargo_id': e.id, 'numero_procedimiento': e.lead_id.stn_no_procedimiento, 'nombre': e.lead_id.name,
            'tipo': e.tipo, 'parte': e.parte, 'version_matriz': e.version_matriz, 'estado': e.estado,
            'indicaciones': e.nota or '', 'solicitado_por': e.solicitado_por.name,
            'fecha_solicitud': str(e.fecha_solicitud or ''),
            'expediente': '%s/stn/lexa/expediente?encargo_id=%s' % (base, e.id),
        } for e in encargos]})

    @http.route('/stn/lexa/expediente', type='http', auth='none', methods=['GET'], csrf=False, save_session=False,
                readonly=False)
    def lexa_expediente(self, numero=None, encargo_id=None, **kw):
        env, err = self._lexa_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        encargo = env['stn.lexa.encargo'].sudo().browse(int(encargo_id)).exists() if encargo_id else None
        lead = encargo.lead_id if encargo else self._lexa_lead(env, numero)
        if not lead:
            return self._json({'ok': False, 'error': 'No existe la licitación o el encargo.'}, status=404)
        return self._json(env['stn.lexa.service'].stn_expediente(lead, encargo))

    def _lexa_archivo_permitido(self, env, att):
        Lead = env['crm.lead'].sudo().with_context(active_test=False)
        if Lead.search_count([('stn_documento_ids', 'in', att.ids), ('team_id.stn_es_licitacion', '=', True)]):
            return True
        if env['stn.licitacion.requisito'].sudo().search_count([('archivo_ids', 'in', att.ids)]):
            return True
        if env['stn.lexa.casilla'].sudo().search_count([('attachment_id', '=', att.id)]):
            return True
        if env['stn.requisito'].sudo()._stn_buscar_por_archivo(att):
            return True  # documento legal de una empresa del grupo (solo lectura)
        return bool(env['stn.lexa.encargo'].sudo().search_count([('matriz_attachment_id', '=', att.id)]))

    @http.route('/stn/lexa/archivo/<int:attachment_id>', type='http', auth='none', methods=['GET'], csrf=False,
                save_session=False)
    def lexa_archivo(self, attachment_id, **kw):
        env, err = self._lexa_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        att = env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not att or not self._lexa_archivo_permitido(env, att):
            return self._json({'ok': False, 'error': 'Archivo no encontrado.'}, status=404)
        nombre = (att.name or 'archivo').replace('"', '')
        return request.make_response(att.raw or b'', headers=[
            ('Content-Type', att.mimetype or 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="%s"' % nombre),
        ])

    @http.route('/stn/lexa/encargo', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def lexa_encargo(self, **kw):
        env, err = self._lexa_auth()
        if err:
            return self._json({'ok': False, 'error': err[1]}, status=err[0])
        Log = env['stn.licia.log'].sudo()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError as e:
            return self._json({'ok': False, 'error': 'JSON inválido: %s' % e}, status=400)
        llave = payload.get('llave') if isinstance(payload, dict) and isinstance(payload.get('llave'), dict) else {}
        registro = dict(payload, numero_procedimiento=llave.get('numero_procedimiento')) \
            if isinstance(payload, dict) else payload
        try:
            with env.cr.savepoint():
                res = env['stn.lexa.service'].stn_upsert_encargo(payload)
            Log._stn_registrar('lexa', registro, {'accion': 'encargo %s' % res.get('estado'),
                                                  'lead_id': res.get('lead_id'),
                                                  'advertencias': res.get('advertencias')})
            return self._json(res)
        except Exception as e:  # noqa: BLE001
            _logger.warning('LEXA: encargo rechazado: %s', e)
            Log._stn_registrar('lexa', registro, error=str(e))
            return self._json({'ok': False, 'error': str(e)}, status=422)
