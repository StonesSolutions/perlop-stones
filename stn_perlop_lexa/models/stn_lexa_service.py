import base64
import json
import logging
import os
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.stn_perlop_licitaciones.models import licia_parser as P
from odoo.addons.stn_perlop_licitaciones.models.crm_lead_lines import PESTANA_POR_TIPO

from .stn_lexa_requisito_maps import (CLASE_MAP, DICTAMEN_MAP, FIRMA_MAP, PARTE_MAP, PESTANA_MAP, QUIEN_MAP,
                                      SEMAFORO_MAP)

_logger = logging.getLogger(__name__)

ICP = 'stn_lexa.'
ESQUEMA = 'lexa.encargo/1.0'
# Bloques del JSON de LEXA que quedan para una fase posterior: se guardan en el JSON del encargo
FUERA_DE_ALCANCE = ('documentos_convocatoria', 'entregables', 'verificaciones', 'firmas')
AVANCE_POR_DICTAMEN = {'cumple': 'completo', 'parcial': 'incompleto', 'no_cumple': 'incompleto'}
FECHAS_LEAD = [('publicacion', 'stn_fecha_publicacion'), ('limite_preguntas', 'stn_fecha_limite_preguntas'),
               ('junta', 'stn_fecha_junta'), ('apertura', 'stn_fecha_apertura'),
               ('limite_interno', 'stn_fecha_limite_interna'), ('fallo', 'stn_fecha_fallo')]


class StnLexaService(models.AbstractModel):
    _name = 'stn.lexa.service'
    _description = 'Conexión con LEXA'

    # ------------------------------------------------------------------
    # Parámetros
    # ------------------------------------------------------------------
    @api.model
    def _icp(self, clave, defecto=False):
        return self.env['ir.config_parameter'].sudo().get_param(ICP + clave, defecto)

    @api.model
    def _generar_token(self):
        token = secrets.token_urlsafe(32)
        self.env['ir.config_parameter'].sudo().set_param(ICP + 'token', token)
        return token

    @api.model
    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')

    # ------------------------------------------------------------------
    # Solicitudes a LEXA
    # ------------------------------------------------------------------
    @api.model
    def stn_solicitar(self, lead, tipo, partes, nota=False):
        Encargo = self.env['stn.lexa.encargo']
        encargos = Encargo.browse()
        for parte in partes:
            previas = lead.stn_lexa_encargo_ids.filtered(lambda e, p=parte: e.parte == p and e.tipo == 'matriz')
            ultima = max(previas.mapped('version_matriz') or [0])
            if tipo == 'matriz':
                version = ultima + 1
            else:
                aprobada = previas.filtered(lambda e: e.estado == 'aprobada')[:1]
                version = aprobada.version_matriz if aprobada else max(ultima, 1)
            # Una solicitud abierta del mismo tipo y parte se reusa (no se duplica el pedido)
            abierta = lead.stn_lexa_encargo_ids.filtered(
                lambda e, p=parte: e.parte == p and e.tipo == tipo and e.estado in ('solicitado', 'en_proceso'))[:1]
            if abierta:
                abierta.write({'nota': nota or abierta.nota, 'estado': 'solicitado'})
                encargos |= abierta
                continue
            encargos |= Encargo.create({'lead_id': lead.id, 'tipo': tipo, 'parte': parte, 'version_matriz': version,
                                        'nota': nota, 'estado': 'solicitado'})
        nombres = ', '.join(encargos.mapped('name'))
        lead.message_post(body=_('Se pidió a LEXA: %s.', nombres), message_type='comment',
                          subtype_xmlid='mail.mt_note')
        if self._icp('modo') == 'rutina_api':
            base = self._base_url()
            for e in encargos:
                texto = '\n'.join([
                    'LEXA_ENCARGO %s' % e.id,
                    'PROCEDIMIENTO %s' % (lead.stn_no_procedimiento or ''),
                    'TIPO %s' % e.tipo.upper(),
                    'PARTE %s' % e.parte.upper(),
                    'EXPEDIENTE %s/stn/lexa/expediente?encargo_id=%s' % (base, e.id),
                    'SOLICITADO_POR %s' % self.env.user.name,
                ] + (['INDICACIONES %s' % nota] if nota else []))
                datos = self.env['stn.licia.service'].stn_disparar_rutina(
                    manual=True, texto=texto, url=self._icp('claude_routine_url'),
                    token=self._icp('claude_routine_token'), beta=self._icp('claude_beta'), agente='LEXA')
                if isinstance(datos, dict) and datos.get('claude_code_session_url'):
                    e.sesion_url = datos['claude_code_session_url']
        return encargos

    # ------------------------------------------------------------------
    # Expediente que lee LEXA
    # ------------------------------------------------------------------
    def _url_archivo(self, att):
        return '%s/stn/lexa/archivo/%s' % (self._base_url(), att.id)

    def _local(self, lead, dt):
        if not dt:
            return None
        return fields.Datetime.context_timestamp(lead.with_context(tz=lead._stn_tz()), dt).strftime('%Y-%m-%d %H:%M')

    @api.model
    def stn_expediente(self, lead, encargo=None):
        lead = lead.sudo()
        if encargo and encargo.estado == 'solicitado':
            encargo.estado = 'en_proceso'
        aprobadas = {}
        for e in lead.stn_lexa_encargo_ids.filtered(lambda x: x.tipo == 'matriz' and x.estado == 'aprobada'):
            if e.parte not in aprobadas or e.version_matriz > aprobadas[e.parte]['version']:
                aprobadas[e.parte] = {'version': e.version_matriz, 'por': e.matriz_aprobada_por.name,
                                      'fecha': self._local(lead, e.matriz_aprobada_fecha)}
        sel = lambda rec, campo: dict(rec._fields[campo].selection).get(rec[campo]) if rec[campo] else None
        return {
            'ok': True,
            'esquema': ESQUEMA,
            'encargo': {
                'id': encargo.id, 'tipo': encargo.tipo, 'parte': encargo.parte,
                'version_matriz': encargo.version_matriz, 'estado': encargo.estado,
                'indicaciones': encargo.nota or '', 'solicitado_por': encargo.solicitado_por.name,
            } if encargo else None,
            'licitacion': {
                'id': lead.id,
                'numero_procedimiento': lead.stn_no_procedimiento,
                'nombre': lead.name,
                'empresa_licitante': lead.stn_empresa_licitante_id.name or None,
                'objeto': lead.stn_objeto or None,
                'dependencia': lead.stn_dependencia_id.name or None,
                'convocante': lead.stn_convocante_id.name or None,
                'unidad_compradora': {'clave': lead.stn_unidad_compradora_clave or None,
                                      'nombre': lead.partner_id.name or None},
                'plaza': lead.stn_plaza or None,
                'estado': lead.state_id.name or None,
                'tipo_procedimiento': lead.stn_tipo_procedimiento_id.name or None,
                'caracter': sel(lead, 'stn_caracter'),
                'modalidad': sel(lead, 'stn_modalidad'),
                'criterio': lead.stn_criterio_id.name or None,
                'estatus': lead.stn_estatus_id.name or None,
                'url_ficha': lead.stn_url_ficha or None,
                'folio_plataforma': lead.stn_folio_plataforma or None,
                'etapa': lead.stage_id.name,
                'lider': lead.stn_lider_id.name or None,
                'responsable': lead.user_id.name or None,
            },
            'fechas': {clave: self._local(lead, lead[campo]) for clave, campo in FECHAS_LEAD},
            'matriz_aprobada': aprobadas,
            'documentos_convocatoria': [{'id': a.id, 'nombre': a.name, 'mimetype': a.mimetype,
                                         'url': self._url_archivo(a)} for a in lead.stn_documento_ids],
            'empresa': {'id': lead.stn_empresa_licitante_id.id, 'nombre': lead.stn_empresa_licitante_id.name,
                        'rfc': lead.stn_empresa_licitante_id.vat or None} if lead.stn_empresa_licitante_id else None,
            'soportes_empresa': self._soportes_empresa(lead),
            'casillas': [{
                'id': c.id, 'pestana': c.pestana, 'orden': c.orden, 'nombre_exacto': c.name,
                'obligatoria': c.obligatoria, 'estado': c.estado,
                'archivo_subida': {'nombre': c.attachment_id.name, 'url': self._url_archivo(c.attachment_id)}
                if c.attachment_id else None,
            } for c in lead.stn_lexa_casilla_ids],
            'requisitos': [{
                'id': r.id, 'pestana': r.pestana, 'orden_casilla': r.orden_casilla or None,
                'numeral': r.referencia or None, 'documento_solicitado': r.name,
                'texto_integro': r.extracto_literal or None, 'tipo': r.tipo, 'situacion': r.situacion,
                'avance': r.avance, 'anexo_o_formato': r.anexo_formato or None,
                'soportes_que_manda_acompanar': r.soportes or None,
                'causal_desechamiento_literal': r.causal_literal or None, 'desecha': r.desecha,
                'huella': r.huella or None, 'clase_formato': r.clase_formato, 'quien_lo_hace': r.quien_lo_hace,
                'vigencia_maxima': r.vigencia_maxima or None,
                'medir_contra': fields.Date.to_string(r.fecha_referencia) if r.fecha_referencia else None,
                'documento_maestro': r.requisito_id.name or None,
                'dictamen': r.lexa_dictamen, 'observacion': r.lexa_observacion or None,
                'nuestros_archivos': [{'id': a.id, 'nombre': a.name, 'mimetype': a.mimetype,
                                       'url': self._url_archivo(a)} for a in r.archivo_ids],
            } for r in lead.stn_requisito_ids.sorted(lambda r: (r.pestana or '', r.orden_clave, r.sequence, r.id))],
            'faltantes': [{
                'id': f.id, 'documento': f.name, 'requisito': f.requisito_id.orden_casilla or f.requisito_id.name or None,
                'dato_faltante': f.dato or None, 'estado': f.estado, 'desecha': f.desecha,
                'solicitado_a': f.solicitado_a_id.name or None,
            } for f in lead.stn_lexa_faltante_ids],
        }

    def _soportes_empresa(self, lead):
        """Documentos legales de la empresa que licita (Odoo es la fuente única). Nunca los de otra empresa."""
        empresa = lead.stn_empresa_licitante_id
        if not empresa:
            return []
        apertura = fields.Date.to_date(lead.stn_fecha_apertura) if lead.stn_fecha_apertura else None
        docs = self.env['stn.requisito'].sudo().search([('empresa_id', '=', empresa.id)], order='categoria_id, name')
        res = []
        for d in docs:
            res.append({
                'id': d.id, 'nombre': d.name, 'categoria': d.categoria_id.name or None,
                'fecha_emision': fields.Date.to_string(d.fecha_emision) if d.fecha_emision else None,
                'vigencia_meses': d.vigencia_meses or 0,
                'fecha_vencimiento': fields.Date.to_string(d.fecha_vencimiento) if d.fecha_vencimiento else None,
                'semaforo': d.stage_code or None,
                'vigente_a_la_apertura': (not d.fecha_vencimiento or d.fecha_vencimiento >= apertura)
                if apertura and d.fecha_emision else None,
                'dias_tramite': d.dias_tramite,
                'es_prueba': d.es_prueba,
                'leido_por_lexa': {'rfc': d.lexa_rfc_leido or None, 'folio': d.lexa_folio or None,
                                   'legibilidad': d.lexa_legibilidad or None, 'alerta': d.lexa_alerta}
                if d.lexa_fecha_revision else None,
                'archivos': [{'id': a.id, 'nombre': a.name, 'mimetype': a.mimetype, 'url': self._url_archivo(a)}
                             for a in d._stn_archivos()],
            })
        return res

    # ------------------------------------------------------------------
    # Entrada de LEXA
    # ------------------------------------------------------------------
    @api.model
    def stn_upsert_encargo(self, payload):
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValidationError(_('El encargo debe ser un objeto JSON.'))
        llave = payload.get('llave') if isinstance(payload.get('llave'), dict) else {}
        g = lambda k: llave.get(k) if llave.get(k) not in (None, '') else payload.get(k)
        advertencias = []
        ctx = dict(self.env.context, stn_lexa_api=True, stn_skip_stage_check=True, mail_create_nosubscribe=True)
        self = self.with_context(ctx)

        encargo = self.env['stn.lexa.encargo']
        if payload.get('encargo_id'):
            encargo = encargo.browse(int(payload['encargo_id'])).exists()
            if not encargo:
                raise ValidationError(_('No existe el encargo %s.', payload['encargo_id']))
        numero = P.texto(g('numero_procedimiento'))
        lead = encargo.lead_id
        if not lead:
            if not numero:
                raise ValidationError(_('Falta llave.numero_procedimiento.'))
            lead = self.env['crm.lead'].with_context(active_test=False).search(
                [('stn_no_procedimiento', '=', numero), ('stn_tipo_registro', '=', 'licitacion')], limit=1)
            if not lead:
                raise ValidationError(_('No existe la licitación %s en Odoo. LEXA no crea licitaciones.', numero))
        elif numero and numero != lead.stn_no_procedimiento:
            raise ValidationError(_('El número %(n)s no coincide con el del encargo (%(e)s). Triple cotejo.',
                                    n=numero, e=lead.stn_no_procedimiento))
        lead = lead.with_context(ctx)

        # Nunca se mezclan empresas
        empresa = P.texto(g('empresa'))
        if empresa and lead.stn_empresa_licitante_id:
            if P.norm(empresa) not in P.norm(lead.stn_empresa_licitante_id.name) \
                    and P.norm(lead.stn_empresa_licitante_id.name) not in P.norm(empresa):
                raise ValidationError(_('La empresa «%(e)s» no coincide con la empresa licitante de Odoo «%(o)s». '
                                        'Nunca se mezclan datos de dos empresas.',
                                        e=empresa, o=lead.stn_empresa_licitante_id.name))
        elif empresa:
            advertencias.append(_('La licitación no tiene empresa licitante en Odoo; la define una persona.'))

        parte = encargo.parte or P.mapear(g('parte'), PARTE_MAP)
        if not parte:
            raise ValidationError(_('Falta llave.parte («legal» o «tecnica»).'))
        tipo = encargo.tipo or P.mapear(payload.get('tipo'), [('revis', 'revision'), ('matriz', 'matriz')],
                                        'revision' if payload.get('revision') else 'matriz')
        version = P.entero(g('version_matriz')) or encargo.version_matriz or 1
        if not encargo:
            encargo = lead.stn_lexa_encargo_ids.filtered(
                lambda e: e.parte == parte and e.tipo == tipo and e.version_matriz == version
                and e.estado != 'cancelado')[:1]
        if tipo == 'matriz' and encargo and encargo.estado == 'aprobada' and version > encargo.version_matriz:
            encargo = self.env['stn.lexa.encargo']  # versión nueva de una matriz ya aprobada → nuevo encargo
        if not encargo:
            encargo = self.env['stn.lexa.encargo'].create({
                'lead_id': lead.id, 'parte': parte, 'tipo': tipo, 'version_matriz': version, 'estado': 'en_proceso',
                'nota': _('Iniciado por LEXA')})
        elif tipo == 'matriz' and version != encargo.version_matriz:
            encargo.version_matriz = version

        for clave in ('aprobaciones', 'matriz_aprobada_por', 'matriz_aprobada_fecha', 'visto_bueno_final'):
            valor = payload.get(clave)
            if isinstance(valor, dict):
                valor = {k: v for k, v in valor.items() if not k.startswith('_') and v not in (None, '')}
            if valor:
                advertencias.append(_('«%s» lo marca una persona en Odoo; LEXA nunca lo escribe. Se ignoró.', clave))
        for clave in FUERA_DE_ALCANCE:
            if payload.get(clave):
                advertencias.append(_('«%s» queda para una fase posterior: se guardó en el JSON del encargo.', clave))

        pestana_parte = 'legal' if parte == 'legal' else 'tecnica'
        casillas = self._sync_casillas(lead, payload.get('casillas'), pestana_parte, advertencias)
        filas = payload.get('requisitos') if isinstance(payload.get('requisitos'), list) else []
        recibidos = self._sync_requisitos(lead, encargo, filas, pestana_parte, tipo, advertencias)
        revision = payload.get('revision') if isinstance(payload.get('revision'), list) else []
        conteo = self._sync_revision(lead, encargo, revision + [f for f in filas if isinstance(f, dict)
                                                                 and f.get('dictamen')], pestana_parte, advertencias)
        self._sync_faltantes(lead, encargo, payload.get('faltantes'), advertencias)
        self._sync_soportes(lead, payload.get('soportes'), pestana_parte, advertencias)
        self._sync_matriz(encargo, payload.get('matriz'), advertencias)
        self._cotejar_fechas(lead, payload.get('fechas'), advertencias)
        self._avisos_comprasmx(lead, payload.get('comprasmx_ultima_revision'))

        # Estado del encargo
        error = P.texto(payload.get('error'))
        estado = P.mapear(payload.get('estado'), [('error', 'error'), ('proceso', 'en_proceso'),
                                                  ('matriz', 'matriz_lista'), ('revisad', 'revisado')])
        if error:
            estado = 'error'
        elif not estado:
            if tipo == 'revision' and conteo['revisados']:
                estado = 'revisado'
            elif tipo == 'matriz' and recibidos:
                estado = 'matriz_lista'
            else:
                estado = encargo.estado if encargo.estado not in ('solicitado',) else 'en_proceso'
        if estado == 'revisado' and tipo == 'matriz':
            estado = 'matriz_lista'
        vals = {
            'estado': estado,
            'empresa': empresa or encargo.empresa,
            'fecha_respuesta': fields.Datetime.now(),
            'resumen': P.texto(payload.get('resumen')) or error or encargo.resumen,
            'advertencias': '\n'.join(advertencias) or False,
            'payload': json.dumps(payload, ensure_ascii=False, indent=1, default=str)[:300000],
        }
        if conteo['revisados']:
            vals.update(conteo)
        encargo.write(vals)
        self._notificar(lead, encargo, conteo)
        return {'ok': True, 'encargo_id': encargo.id, 'estado': encargo.estado, 'lead_id': lead.id,
                'casillas': len(casillas), 'requisitos': len(recibidos), 'revisados': conteo['revisados'],
                'advertencias': advertencias}

    # ---------------- casillas ----------------
    def _sync_casillas(self, lead, filas, pestana_parte, advertencias):
        if not isinstance(filas, list) or not filas:
            return self.env['stn.lexa.casilla']
        Casilla = self.env['stn.lexa.casilla']
        recibidas = Casilla.browse()
        pestanas = set()
        for f in filas:
            if not isinstance(f, dict):
                continue
            orden = P.entero(f.get('orden'))
            nombre = P.texto(f.get('nombre_exacto') or f.get('name'))
            if not orden or not nombre:
                continue
            pestana = P.mapear(f.get('pestana'), PESTANA_MAP, pestana_parte)
            pestanas.add(pestana)
            vals = {'name': nombre, 'obligatoria': P.booleano(f.get('obligatoria')) is not False}
            estado = P.mapear(f.get('estado'), [('pendiente', 'pendiente'), ('generado', 'generado'),
                                               ('verificado', 'verificado'), ('foliado', 'foliado'),
                                               ('subido', 'subido')])
            if estado == 'subido':
                advertencias.append(_('Casilla %s: «subido» solo lo marca una persona.', orden))
            elif estado:
                vals['estado'] = estado
            actual = lead.stn_lexa_casilla_ids.filtered(lambda c: c.pestana == pestana and c.orden == orden)[:1]
            if actual:
                if actual.estado == 'subido':
                    vals.pop('estado', None)
                actual.write(vals)
            else:
                actual = Casilla.create(dict(vals, lead_id=lead.id, pestana=pestana, orden=orden, origen='lexa'))
            recibidas |= actual
        # Reemplazar, no acumular: las casillas de LEXA que ya no vienen se quitan (salvo las ya subidas)
        sobran = lead.stn_lexa_casilla_ids.filtered(
            lambda c: c.pestana in pestanas and c not in recibidas and c.origen == 'lexa')
        for c in sobran:
            if c.estado == 'subido' or c.attachment_id:
                advertencias.append(_('La casilla %s ya no viene en el pantallazo; se conservó porque tiene archivo '
                                      'o ya se subió.', c.display_name))
            else:
                c.unlink()
        return recibidas

    # ---------------- requisitos (renglones de la matriz) ----------------
    def _buscar_requisito(self, lead, f, pestana, excluir=None, filas=None):
        """Busca el requisito en Odoo. `excluir`: los ya tomados en este envío. `filas`: el envío completo;
        si varios renglones comparten numeral o nombre, ese criterio no sirve para distinguirlos."""
        reqs = lead.stn_requisito_ids - (excluir or lead.stn_requisito_ids.browse())

        def unico(clave, valor):
            if not filas:
                return True
            return sum(1 for x in filas if isinstance(x, dict) and P.norm(x.get(clave) or '') == P.norm(valor)) <= 1
        rid = P.entero(f.get('id') or f.get('requisito_id'))
        if rid:
            r = reqs.filtered(lambda x: x.id == rid)
            if r:
                return r
        orden = P.texto(f.get('orden_casilla'))
        if orden:
            r = reqs.filtered(lambda x: x.pestana == pestana and P.norm(x.orden_casilla) == P.norm(orden))
            if len(r) == 1:
                return r
        numeral = P.texto(f.get('numeral') or f.get('referencia'))
        if numeral and unico('numeral', numeral):
            r = reqs.filtered(lambda x: P.norm(x.referencia or '') == P.norm(numeral))
            if len(r) == 1:
                return r
        nombre = P.texto(f.get('documento_solicitado') or f.get('requisito'))
        if nombre and unico('documento_solicitado', nombre):
            r = reqs.filtered(lambda x: P.norm(x.name) == P.norm(nombre))
            if len(r) == 1:
                return r
        return reqs.browse()

    def _vals_requisito(self, lead, f, pestana_parte, casillas_lead):
        orden = P.texto(f.get('orden_casilla'))
        pestana = P.mapear(f.get('pestana'), PESTANA_MAP) or PESTANA_POR_TIPO.get(
            P.mapear(f.get('tipo'), P.TIPO_REQUISITO) or '') or pestana_parte
        vals = {
            'referencia': P.texto(f.get('numeral') or f.get('referencia')),
            'extracto_literal': P.texto(f.get('texto_integro')),
            'anexo_formato': P.texto(f.get('anexo_o_formato')),
            'soportes': P.texto(f.get('soportes_que_manda_acompanar')),
            'causal_literal': P.texto(f.get('causal_desechamiento_literal')),
            'huella': P.texto(f.get('huella')),
            'fundamento': P.texto(f.get('fundamento')),
            'clase_formato': P.mapear(f.get('clase_formato'), CLASE_MAP),
            'quien_lo_hace': P.mapear(f.get('quien_lo_hace'), QUIEN_MAP),
            'pendiente': P.texto(f.get('informacion_pendiente')),
            'lexa_semaforo': P.mapear(f.get('semaforo'), SEMAFORO_MAP),
            'explicacion': P.texto(f.get('explicacion_en_corto')),
            'firma_requerida': P.mapear(f.get('firma_requerida'), FIRMA_MAP),
            'evidencia': P.texto(f.get('evidencia_archivo_pagina')),
            'vigencia_maxima': P.texto(f.get('vigencia_maxima')),
            'situacion': P.mapear(f.get('situacion'), P.SITUACION),
            'situacion_detalle': P.texto(f.get('informacion_localizada')),
            'tipo': P.mapear(f.get('tipo'), P.TIPO_REQUISITO),
        }
        maestro = self._buscar_maestro(lead, f.get('documento_maestro'))
        if maestro:
            vals['requisito_id'] = maestro.id
        cambio = f.get('cambiado_por_junta')
        if isinstance(cambio, dict):
            vals['junta_cambio'] = bool(P.booleano(cambio.get('cambio')) or cambio.get('detalle'))
            vals['junta_cambio_detalle'] = P.texto(cambio.get('detalle'))
        elif cambio not in (None, ''):
            b = P.booleano(cambio)
            vals['junta_cambio'] = bool(b) if b is not None else True
            if b is None:
                vals['junta_cambio_detalle'] = P.texto(cambio)
        if P.texto(f.get('causal_desechamiento_literal')) and not P.texto(f.get('efecto')):
            vals['efecto'] = P.texto(f.get('causal_desechamiento_literal'))[:250]
        vals = {k: v for k, v in vals.items() if v not in (None, False, '')}
        if orden:
            vals['orden_casilla'] = orden
            base, _sep, sub = orden.partition('.')
            casilla = casillas_lead.filtered(lambda c: c.pestana == pestana and str(c.orden) == base.strip())[:1]
            if casilla:
                vals['casilla_id'] = casilla.id
                vals['subindice'] = P.entero(sub) or 0
        vals['pestana'] = pestana
        return vals

    def _sync_requisitos(self, lead, encargo, filas, pestana_parte, tipo, advertencias):
        Req = self.env['stn.licitacion.requisito']
        recibidos = Req.browse()
        casillas_lead = lead.stn_lexa_casilla_ids
        if tipo != 'matriz':
            return recibidos
        for f in filas:
            if not isinstance(f, dict):
                continue
            nombre = P.texto(f.get('documento_solicitado') or f.get('requisito'))
            req = self._buscar_requisito(lead, f, P.mapear(f.get('pestana'), PESTANA_MAP) or pestana_parte,
                                         excluir=recibidos, filas=filas)
            vals = self._vals_requisito(lead, f, pestana_parte, casillas_lead)
            if req:
                if nombre:
                    vals['name'] = nombre
                vals['lexa_encargo_id'] = encargo.id
                req.write(vals)
            elif nombre:
                req = Req.create(dict(vals, lead_id=lead.id, name=nombre, origen='lexa', lexa_encargo_id=encargo.id))
            else:
                advertencias.append(_('Renglón sin «documento_solicitado»: no entra.'))
                continue
            recibidos |= req
        if recibidos:
            # Reemplazar, no acumular: renglones que LEXA puso antes en esta pestaña y ya no vienen
            pestanas = set(recibidos.mapped('pestana'))
            sobran = lead.stn_requisito_ids.filtered(
                lambda r: r.origen == 'lexa' and r.pestana in pestanas and r not in recibidos)
            for r in sobran:
                if r.archivo_ids or r.avance == 'completo':
                    advertencias.append(_('El renglón «%s» ya no viene en la matriz; se conservó porque tiene '
                                          'archivos o avance del equipo.', r.name))
                else:
                    r.unlink()
        return recibidos

    # ---------------- revisión cumple / no cumple ----------------
    def _sync_revision(self, lead, encargo, filas, pestana_parte, advertencias):
        conteo = {'revisados': 0, 'cumplen': 0, 'no_cumplen': 0, 'parciales': 0}
        ahora = fields.Datetime.now()
        for f in filas:
            if not isinstance(f, dict):
                continue
            dictamen = P.mapear(f.get('dictamen') or f.get('resultado'), DICTAMEN_MAP)
            if not dictamen:
                continue
            req = self._buscar_requisito(lead, f, P.mapear(f.get('pestana'), PESTANA_MAP) or pestana_parte)
            if not req:
                advertencias.append(_('Revisión sin requisito en Odoo: %s',
                                      f.get('orden_casilla') or f.get('numeral') or f.get('id')))
                continue
            vals = {'lexa_dictamen': dictamen, 'lexa_observacion': P.texto(f.get('observacion')),
                    'lexa_fecha': ahora, 'lexa_encargo_id': encargo.id}
            if P.texto(f.get('evidencia') or f.get('evidencia_archivo_pagina')):
                vals['evidencia'] = P.texto(f.get('evidencia') or f.get('evidencia_archivo_pagina'))
            if req.avance != 'no_aplica':
                vals['avance'] = AVANCE_POR_DICTAMEN[dictamen]
            req.write(vals)
            conteo['revisados'] += 1
            conteo[{'cumple': 'cumplen', 'no_cumple': 'no_cumplen', 'parcial': 'parciales'}[dictamen]] += 1
        return conteo

    # ---------------- faltantes ----------------
    def _sync_faltantes(self, lead, encargo, filas, advertencias):
        if not isinstance(filas, list):
            return
        Faltante = self.env['stn.lexa.faltante']
        recibidos = Faltante.browse()
        usuarios = self.env['res.users'].sudo()
        for f in filas:
            if not isinstance(f, dict):
                continue
            nombre = P.texto(f.get('documento'))
            if not nombre:
                continue
            req = self._buscar_requisito(lead, {'orden_casilla': f.get('requisito'), 'numeral': f.get('requisito'),
                                                'documento_solicitado': f.get('requisito')}, encargo.parte == 'legal'
                                         and 'legal' or 'tecnica') if P.texto(f.get('requisito')) else False
            donde = f.get('donde_se_busco')
            if isinstance(donde, list):
                donde = '\n'.join(map(str, donde))
            vals = {
                'name': nombre, 'dato': P.texto(f.get('dato_faltante')), 'donde_se_busco': P.texto(donde),
                'lugar': P.texto(f.get('lugar_en_documento')), 'consecuencia': P.texto(f.get('consecuencia')),
                'desecha': bool(P.booleano(f.get('desecha'))), 'encargo_id': encargo.id,
                'requisito_id': req.id if req else False,
            }
            estado = P.mapear(f.get('estado'), [('abiert', 'abierto'), ('tramite', 'en_tramite'),
                                               ('resuelt', 'resuelto'), ('no aplica', 'no_aplica')])
            if estado:
                vals['estado'] = estado
            if P.texto(f.get('solicitado_a')):
                user = usuarios.search([('name', '=ilike', P.texto(f.get('solicitado_a'))), ('share', '=', False)],
                                       limit=1)
                if user:
                    vals['solicitado_a_id'] = user.id
            if not P.texto(donde):
                advertencias.append(_('Faltante «%s» sin «donde_se_busco»: no se puede declarar «falta» sin decir '
                                      'dónde se buscó.', nombre))
            libres = lead.stn_lexa_faltante_ids - recibidos
            actual = libres.filtered(
                lambda x: P.norm(x.name) == P.norm(nombre) and x.requisito_id.id == vals['requisito_id'])[:1]
            if not actual:
                # Mismo faltante aunque el requisito haya cambiado de id entre envíos
                mismo = libres.filtered(lambda x: x.origen == 'lexa' and P.norm(x.name) == P.norm(nombre))
                actual = mismo if len(mismo) == 1 else actual
            if actual:
                if actual.estado in ('resuelto', 'no_aplica') and vals.get('estado') in (None, 'abierto'):
                    vals.pop('estado', None)  # lo cerró una persona
                actual.write(vals)
            else:
                actual = Faltante.create(dict(vals, lead_id=lead.id, origen='lexa'))
            recibidos |= actual
        # Lo que LEXA ya no reporta como faltante en esta parte, quedó resuelto
        lead.stn_lexa_faltante_ids.filtered(
            lambda x: x.origen == 'lexa' and x.encargo_id.parte == encargo.parte and x not in recibidos
            and x.estado in ('abierto', 'en_tramite')).write({'estado': 'resuelto'})

    # ---------------- soportes de la empresa (documentos maestros) ----------------
    def _buscar_maestro(self, lead, ref):
        """Documento maestro por id o por nombre, solo de la empresa que licita."""
        empresa = lead.stn_empresa_licitante_id
        if not ref or not empresa:
            return self.env['stn.requisito']
        Req = self.env['stn.requisito'].sudo()
        rid = P.entero(ref) if isinstance(ref, (int, float)) or str(ref).strip().isdigit() else None
        if rid:
            return Req.search([('id', '=', rid), ('empresa_id', '=', empresa.id)], limit=1)
        nombre = P.norm(os.path.splitext(str(ref))[0])
        return Req.search([('empresa_id', '=', empresa.id)]).filtered(
            lambda d: P.norm(d.name) == nombre or any(P.norm(os.path.splitext(a.name or '')[0]) == nombre
                                                      for a in d._stn_archivos()))[:1]

    def _sync_soportes(self, lead, filas, pestana_parte, advertencias):
        if not isinstance(filas, list) or not filas:
            return
        empresa = lead.stn_empresa_licitante_id
        if not empresa:
            advertencias.append(_('Soportes ignorados: la licitación no tiene empresa licitante.'))
            return
        rfc_empresa = P.norm(empresa.vat or '').replace(' ', '').replace('-', '')
        ahora = fields.Datetime.now()
        for f in filas:
            if not isinstance(f, dict):
                continue
            doc = self._buscar_maestro(lead, f.get('documento_maestro') or f.get('id') or f.get('archivo'))
            if not doc:
                advertencias.append(_('Soporte «%s» no está en los documentos de %s en Odoo.',
                                      f.get('archivo') or f.get('documento_maestro'), empresa.name))
                continue
            alertas = []
            rfc = P.texto(f.get('rfc_en_documento'))
            rfc_norm = P.norm(rfc or '').replace(' ', '').replace('-', '')
            rfc_ajeno = bool(rfc_norm and rfc_empresa and rfc_norm != rfc_empresa)
            if rfc_ajeno:
                alertas.append(_('el RFC del documento (%(r)s) no es el de %(e)s', r=rfc, e=empresa.name))
            leida = P.fecha(f.get('fecha_emision_interna'))
            vals = {'lexa_fecha_revision': ahora, 'lexa_rfc_leido': rfc or doc.lexa_rfc_leido,
                    'lexa_fecha_emision_leida': leida or doc.lexa_fecha_emision_leida,
                    'lexa_fecha_sello': P.fecha(f.get('fecha_sello')) or doc.lexa_fecha_sello,
                    'lexa_folio': P.texto(f.get('folio_o_numero') or f.get('folio')) or doc.lexa_folio,
                    'lexa_observacion': P.texto(f.get('observacion')) or doc.lexa_observacion}
            if leida and not doc.fecha_emision:
                vals['fecha_emision'] = leida
            elif leida and doc.fecha_emision and leida != doc.fecha_emision:
                alertas.append(_('la fecha dentro del documento (%(l)s) no coincide con la del catálogo (%(c)s)',
                                 l=leida, c=doc.fecha_emision))
            legibilidad = P.mapear(f.get('legibilidad'), [('ilegible', 'ilegible'), ('dudos', 'dudosa'),
                                                          ('legible', 'legible')])
            if legibilidad:
                vals['lexa_legibilidad'] = legibilidad
                if legibilidad != 'legible':
                    alertas.append(_('legibilidad %s', legibilidad))
            contradiccion = f.get('contradice_declaracion')
            if isinstance(contradiccion, dict):
                contradiccion = contradiccion.get('detalle') if contradiccion.get('contradice', True) else None
            if contradiccion not in (None, False, '', 'NO', 'no'):
                vals['lexa_contradiccion'] = P.texto(contradiccion) if not isinstance(contradiccion, bool) \
                    else _('Sí (sin detalle)')
                alertas.append(_('contradice lo declarado'))
            vals['lexa_alerta'] = bool(alertas)
            doc.sudo().write(vals)
            if 'fecha_emision' in vals:
                doc.sudo().action_stn_actualizar_semaforo()
            if alertas:
                texto = _('LEXA revisó «%(d)s»: %(a)s.', d=doc.name, a='; '.join(alertas))
                advertencias.append(texto)
                doc.sudo().message_post(body=texto, message_type='comment', subtype_xmlid='mail.mt_note')
            # Ligar el documento maestro al requisito de la licitación (semáforo por licitación)
            if P.texto(f.get('requisito')) and not rfc_ajeno:
                req = self._buscar_requisito(lead, {'orden_casilla': f.get('requisito'), 'numeral': f.get('requisito')},
                                             pestana_parte)
                if req:
                    req.requisito_id = doc

    # ---------------- archivo de la matriz ----------------
    def _sync_matriz(self, encargo, matriz, advertencias):
        if not isinstance(matriz, dict) or not matriz.get('contenido_base64'):
            return
        try:
            datos = base64.b64decode(matriz['contenido_base64'], validate=False)
        except (ValueError, TypeError):
            advertencias.append(_('La matriz no viene en base64 válido.'))
            return
        att = self.env['ir.attachment'].sudo().create({
            'name': P.texto(matriz.get('nombre')) or '01_MATRIZ_DE_COTEJO_v%s.xlsx' % encargo.version_matriz,
            'raw': datos, 'res_model': 'stn.lexa.encargo', 'res_id': encargo.id,
            'mimetype': matriz.get('mimetype') or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        encargo.matriz_attachment_id = att

    # ---------------- cotejo de fechas (LICIA manda las fechas; LEXA solo avisa) ----------------
    def _cotejar_fechas(self, lead, fechas, advertencias):
        if not isinstance(fechas, dict):
            return
        tz = lead._stn_tz()
        diferencias = []
        for clave, campo in FECHAS_LEAD:
            valor = P.fecha_hora(fechas.get(clave), tz)
            if valor and lead[campo] and abs((valor - lead[campo]).total_seconds()) >= 60:
                diferencias.append('%s: LEXA %s · Odoo %s' % (clave, P.texto(fechas.get(clave)),
                                                               self._local(lead, lead[campo])))
        if diferencias:
            texto = _('LEXA ve fechas distintas a las de Odoo (no se cambiaron): %s', '; '.join(diferencias))
            advertencias.append(texto)
            lead.message_post(body=texto, message_type='comment', subtype_xmlid='mail.mt_note')

    def _avisos_comprasmx(self, lead, revision):
        if not isinstance(revision, dict):
            return
        partes = []
        for clave, titulo in [('anexos_nuevos', _('anexos nuevos')), ('anexos_reemplazados', _('anexos reemplazados')),
                              ('actas_junta_nuevas', _('actas de junta nuevas')),
                              ('avisos_cambio_fecha', _('avisos de cambio de fecha'))]:
            valor = revision.get(clave)
            if isinstance(valor, list) and valor:
                partes.append('%s: %s' % (titulo, ', '.join(map(str, valor))))
        if revision.get('casillas_cuadran_con_matriz') is False:
            partes.append(_('las casillas de ComprasMX no cuadran con la matriz'))
        if partes:
            lead.message_post(body=_('LEXA revisó ComprasMX y encontró %s.', '; '.join(partes)),
                              partner_ids=lead.stn_lider_id.partner_id.ids, message_type='comment',
                              subtype_xmlid='mail.mt_comment')

    # ---------------- avisos al equipo ----------------
    def _notificar(self, lead, encargo, conteo):
        responsable = lead.stn_lider_id or lead.user_id
        parte = dict(encargo._fields['parte'].selection)[encargo.parte].lower()
        if encargo.estado == 'matriz_lista':
            resumen = _('Aprobar matriz de LEXA (%s)', parte)
            if responsable and not lead.activity_ids.filtered(lambda a: a.summary == resumen):
                lead.activity_schedule('mail.mail_activity_data_todo', summary=resumen, user_id=responsable.id,
                                       note=_('LEXA entregó la matriz %s. Sin aprobación no elabora documentos.',
                                              encargo.name))
            lead.message_post(body=_('LEXA entregó la matriz %s: falta aprobarla.', encargo.name),
                              message_type='comment', subtype_xmlid='mail.mt_note')
        elif encargo.estado == 'revisado':
            lead.message_post(
                body=_('LEXA revisó %(n)s requisito(s) de la parte %(p)s: %(c)s cumplen, %(nc)s no cumplen y '
                       '%(pa)s cumplen parcialmente.', n=conteo['revisados'], p=parte, c=conteo['cumplen'],
                       nc=conteo['no_cumplen'], pa=conteo['parciales']),
                partner_ids=responsable.partner_id.ids, message_type='comment', subtype_xmlid='mail.mt_comment')
            if (conteo['no_cumplen'] or conteo['parciales']) and responsable:
                lead.activity_schedule('mail.mail_activity_data_todo', user_id=responsable.id,
                                       summary=_('Atender observaciones de LEXA (%s)', parte),
                                       note=_('Revisa la columna «Revisión LEXA» en Requerimientos.'))
        elif encargo.estado == 'error':
            lead.message_post(body=_('LEXA no pudo completar %(e)s: %(m)s', e=encargo.name, m=encargo.resumen or '-'),
                              message_type='comment', subtype_xmlid='mail.mt_note')
