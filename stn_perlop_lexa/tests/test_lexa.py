import base64
import copy
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

NUMERO = 'LA-50-GYR-050GYR012-N-134-2026'

MATRIZ = {
    'esquema': 'lexa.encargo/1.0',
    'llave': {'numero_procedimiento': NUMERO, 'empresa': 'PERLOP', 'parte': 'tecnica', 'version_matriz': 1},
    'tipo': 'matriz',
    'resumen': 'Matriz técnica: 3 renglones, 1 bloquea.',
    'fechas': {'apertura': '2026-12-15 09:30'},
    'casillas': [
        {'pestana': 'tecnico', 'orden': 1, 'nombre_exacto': '3.1.2 INCISO A)', 'obligatoria': True,
         'estado': 'pendiente'},
        {'pestana': 'tecnico', 'orden': 2, 'nombre_exacto': '3.1.2 INCISO B)', 'obligatoria': True,
         'estado': 'subido'},
    ],
    'requisitos': [
        {'orden_casilla': '1.1', 'numeral': 'T&C › INCISO D) › NUMERAL 4)',
         'documento_solicitado': 'Estudios clínicos del personal que entrega', 'tipo': 'tecnico',
         'texto_integro': 'Estudios clínicos (6 pruebas) del personal…', 'clase_formato': 'solo_portada',
         'quien_lo_hace': 'lexa_portada_empresa_anexa', 'situacion': 'VERIFICAR', 'semaforo': 'confirmar',
         'huella': 'ESTUDIOS CLINICOS', 'explicacion_en_corto': 'TE PREGUNTO: ¿son del 13-jul o posteriores?'},
        {'orden_casilla': '1.4', 'numeral': 'T&C › INCISO D) › NUMERAL 2)',
         'documento_solicitado': 'Contrato de fumigación con facturas y certificados', 'tipo': 'tecnico',
         'causal_desechamiento_literal': 'Será causa de desechamiento…', 'semaforo': 'bloquea',
         'situacion': 'CONSEGUIR', 'firma_requerida': 'no_aplica'},
        {'orden_casilla': '2', 'numeral': '3.1.2 INCISO B)', 'documento_solicitado': 'Carta de entrega diaria',
         'tipo': 'tecnico', 'clase_formato': 'libre', 'quien_lo_hace': 'lexa'},
    ],
    'faltantes': [
        {'documento': 'Certificados de fumigación ago-sep 2026', 'requisito': '1.4',
         'dato_faltante': 'certificados y facturas de agosto y septiembre',
         'donde_se_busco': ['OneDrive/fumigación/2026-08', 'vault de LEXA'], 'desecha': True, 'estado': 'abierto'},
    ],
    'aprobaciones': {'matriz_aprobada_por': 'LEXA', 'matriz_aprobada_fecha': '2026-10-08'},
    'verificaciones': [{'compuerta': 'guardia_matriz', 'resultado': 'ok'}],
    'matriz': {'nombre': '01_MATRIZ_DE_COTEJO_TECNICA.xlsx', 'contenido_base64': base64.b64encode(b'xlsx').decode()},
}


@tagged('post_install', '-at_install')
class TestLexa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env['crm.lead']
        cls.Lead.with_context(active_test=False).search([('stn_no_procedimiento', '=', NUMERO)]).unlink()
        cls.env['ir.config_parameter'].sudo().set_param('stn_lexa.activo', 'True')
        cls.env['ir.config_parameter'].sudo().set_param('stn_lexa.modo', 'cola')
        cls.perlop = cls.env['res.partner'].create({'name': 'PERLOP Operadora de Alimentos', 'is_company': True})
        cls.lider = cls.env['res.users'].create({
            'name': 'Líder LEXA', 'login': 'lider_lexa_test',
            'group_ids': [(6, 0, [cls.env.ref('stn_perlop_licitaciones.group_licitaciones_user').id])]})
        res = cls.Lead.stn_upsert_ficha({
            'numero_procedimiento': NUMERO, 'nombre_oportunidad': 'Colima N-134', 'nivel_licia': 4,
            'fecha_apertura': '2026-12-15 09:30',
            'requisitos': [{'referencia': '3.1.1 I', 'requisito': 'Acreditamiento de personalidad', 'tipo': 'Legal',
                            'situacion': 'TENEMOS'}]})
        cls.lead = cls.Lead.browse(res['lead_id'])
        cls.lead.write({'stn_empresa_licitante_id': cls.perlop.id, 'stn_lider_id': cls.lider.id})
        cls.Service = cls.env['stn.lexa.service']

    def test_01_matriz_casillas_faltantes_y_aprobacion_humana(self):
        res = self.Service.stn_upsert_encargo(copy.deepcopy(MATRIZ))
        encargo = self.env['stn.lexa.encargo'].browse(res['encargo_id'])
        self.assertEqual(encargo.estado, 'matriz_lista')
        self.assertFalse(encargo.matriz_aprobada_por, 'LEXA nunca escribe aprobaciones')
        self.assertTrue(any('lo marca una persona' in a for a in res['advertencias']))
        self.assertTrue(any('verificaciones' in a for a in res['advertencias']))
        casillas = self.lead.stn_lexa_casilla_ids
        self.assertEqual(len(casillas), 2)
        self.assertNotEqual(casillas.filtered(lambda c: c.orden == 2).estado, 'subido', '«Subido» lo marca una persona')
        tecnicos = self.lead._stn_requisitos_por_pestana('tecnica')
        self.assertEqual(tecnicos.mapped('orden_casilla'), ['1.1', '1.4', '2'])
        r14 = tecnicos.filtered(lambda r: r.orden_casilla == '1.4')
        self.assertEqual(r14.casilla_id.orden, 1)
        self.assertEqual(r14.subindice, 4)
        self.assertEqual(r14.lexa_semaforo, 'bloquea')
        self.assertTrue(r14.desecha)
        falt = self.lead.stn_lexa_faltante_ids
        self.assertEqual(len(falt), 1)
        self.assertEqual(falt.requisito_id, r14)
        self.assertIn('vault', falt.donde_se_busco)
        self.assertTrue(encargo.matriz_attachment_id)
        self.assertTrue(self.lead.activity_ids.filtered(lambda a: a.summary.startswith('Aprobar matriz')))
        with self.assertRaises(UserError):
            encargo.write({'matriz_aprobada_por': self.env.user.id})
        otro = self.env['res.users'].create({
            'name': 'Auxiliar', 'login': 'aux_lexa_test',
            'group_ids': [(6, 0, [self.env.ref('stn_perlop_licitaciones.group_licitaciones_user').id])]})
        with self.assertRaises(UserError):
            encargo.with_user(otro).action_aprobar_matriz()
        encargo.with_user(self.lider).action_aprobar_matriz()
        self.assertEqual(encargo.estado, 'aprobada')
        self.assertEqual(encargo.matriz_aprobada_por, self.lider)
        # versión 2 sin el renglón 2: se reemplaza, no se acumula; el faltante que ya no viene queda resuelto
        v2 = copy.deepcopy(MATRIZ)
        v2['llave']['version_matriz'] = 2
        v2['requisitos'] = v2['requisitos'][:2]
        v2['casillas'] = v2['casillas'][:1]
        v2['faltantes'] = []
        res2 = self.Service.stn_upsert_encargo(v2)
        self.assertNotEqual(res2['encargo_id'], encargo.id, 'Una versión nueva de una matriz aprobada es otro encargo')
        self.assertEqual(self.lead._stn_requisitos_por_pestana('tecnica').mapped('orden_casilla'), ['1.1', '1.4'])
        self.assertEqual(len(self.lead.stn_lexa_casilla_ids), 1)
        self.assertEqual(falt.estado, 'resuelto')

    def test_02_revision_cumple_no_cumple_actualiza_avance(self):
        self.Service.stn_upsert_encargo(copy.deepcopy(MATRIZ))
        tecnicos = self.lead._stn_requisitos_por_pestana('tecnica')
        with self.assertRaises(UserError):  # sin archivos no hay nada que revisar
            self.env['stn.lexa.solicitud.wizard'].create({'lead_id': self.lead.id, 'tipo': 'revision',
                                                          'parte': 'tecnica'}).action_confirmar()
        archivo = self.env['ir.attachment'].create({'name': 'estudios.pdf', 'raw': b'%PDF-1.4'})
        tecnicos[0].archivo_ids = [(4, archivo.id)]
        self.assertEqual(archivo.res_id, self.lead.id)
        self.env['stn.lexa.solicitud.wizard'].create({'lead_id': self.lead.id, 'tipo': 'revision',
                                                      'parte': 'ambas'}).action_confirmar()
        encargo = self.lead.stn_lexa_encargo_ids.filtered(lambda e: e.tipo == 'revision')
        self.assertEqual(len(encargo), 1, 'Solo la parte con archivos')
        self.assertEqual(encargo.estado, 'solicitado')
        exp = self.Service.stn_expediente(self.lead, encargo)
        self.assertEqual(encargo.estado, 'en_proceso')
        req_exp = [r for r in exp['requisitos'] if r['id'] == tecnicos[0].id][0]
        self.assertEqual(req_exp['nuestros_archivos'][0]['nombre'], 'estudios.pdf')
        res = self.Service.stn_upsert_encargo({
            'encargo_id': encargo.id, 'resumen': 'Revisión técnica',
            'revision': [
                {'requisito_id': tecnicos[0].id, 'dictamen': 'CUMPLE', 'evidencia': '1.pdf, p. 3'},
                {'orden_casilla': '1.4', 'dictamen': 'NO CUMPLE', 'observacion': 'Faltan certificados de septiembre.'},
                {'orden_casilla': '2', 'dictamen': 'Cumple parcialmente', 'observacion': 'Sin firma.'},
            ]})
        self.assertEqual(res['revisados'], 3)
        self.assertEqual(encargo.estado, 'revisado')
        self.assertEqual((encargo.cumplen, encargo.no_cumplen, encargo.parciales), (1, 1, 1))
        self.assertEqual(tecnicos.mapped('avance'), ['completo', 'incompleto', 'incompleto'])
        self.assertEqual(tecnicos.mapped('lexa_dictamen'), ['cumple', 'no_cumple', 'parcial'])
        self.assertAlmostEqual(self.lead.stn_avance_tecnica, 33.3, 1)
        self.assertEqual(self.lead.stn_lexa_no_cumplen, 2)

    def test_03_empresa_numero_y_apertura(self):
        malo = copy.deepcopy(MATRIZ)
        malo['llave']['empresa'] = 'JADE'
        with self.assertRaises(ValidationError):
            self.Service.stn_upsert_encargo(malo)
        malo = copy.deepcopy(MATRIZ)
        malo['llave']['numero_procedimiento'] = 'LA-00-XXX-000XXX000-N-1-2026'
        with self.assertRaises(ValidationError):
            self.Service.stn_upsert_encargo(malo)
        res = self.Service.stn_upsert_encargo(copy.deepcopy(MATRIZ))
        encargo = self.env['stn.lexa.encargo'].browse(res['encargo_id'])
        encargo.with_user(self.lider).action_aprobar_matriz()
        self.lead.stn_fecha_apertura = self.lead.stn_fecha_apertura + timedelta(days=2)
        self.assertEqual(encargo.estado, 'requiere_regenerar')
        # fechas distintas: se avisa pero no se cambian (las fechas las manda LICIA)
        otra = copy.deepcopy(MATRIZ)
        otra['fechas'] = {'apertura': '2027-01-10 10:00'}
        apertura = self.lead.stn_fecha_apertura
        res = self.Service.stn_upsert_encargo(otra)
        self.assertEqual(self.lead.stn_fecha_apertura, apertura)
        self.assertTrue(any('fechas distintas' in a for a in res['advertencias']))


    def test_05_renglones_con_mismo_numeral_y_reenvio(self):
        payload = copy.deepcopy(MATRIZ)
        payload['requisitos'] = [
            {'orden_casilla': '9.1', 'numeral': '4.1.13 a 4.1.15', 'documento_solicitado': 'Opinión SAT', 'tipo': 'legal'},
            {'orden_casilla': '9.2', 'numeral': '4.1.13 a 4.1.15', 'documento_solicitado': 'Opinión IMSS', 'tipo': 'legal'},
            {'orden_casilla': '9.3', 'numeral': '4.1.13 a 4.1.15', 'documento_solicitado': 'Opinión INFONAVIT', 'tipo': 'legal'},
        ]
        payload['llave']['parte'] = 'legal'
        payload['casillas'] = [{'pestana': 'legal', 'orden': 9, 'nombre_exacto': 'OPINIONES'}]
        self.Service.stn_upsert_encargo(copy.deepcopy(payload))
        legales = self.lead._stn_requisitos_por_pestana('legal').filtered(lambda r: r.origen == 'lexa')
        self.assertEqual(len(legales), 3, 'Tres renglones con el mismo numeral no se fusionan')
        # reenvío: el requisito del faltante cambia, el faltante no se duplica
        payload['faltantes'] = [{'documento': 'Opiniones de cumplimiento', 'requisito': '9.1',
                                 'donde_se_busco': ['Odoo'], 'desecha': False}]
        self.Service.stn_upsert_encargo(copy.deepcopy(payload))
        payload['faltantes'][0]['requisito'] = '9.2'
        self.Service.stn_upsert_encargo(copy.deepcopy(payload))
        self.assertEqual(len(self.lead._stn_requisitos_por_pestana('legal').filtered(lambda r: r.origen == 'lexa')), 3)
        self.assertEqual(len(self.lead.stn_lexa_faltante_ids.filtered(
            lambda f: f.name == 'Opiniones de cumplimiento')), 1)

    def test_04_soportes_desde_odoo(self):
        self.perlop.vat = 'POA0101019Z1'
        jade = self.env['res.partner'].create({'name': 'JADE prueba LEXA', 'is_company': True})
        for empresa in (self.perlop, jade):
            self.env['stn.requisito.prueba.wizard'].create({'empresa_id': empresa.id}).action_cargar()
        exp = self.Service.stn_expediente(self.lead)
        self.assertEqual(exp['empresa']['rfc'], 'POA0101019Z1')
        soportes = exp['soportes_empresa']
        self.assertEqual(len(soportes), 22, 'Solo los de la empresa que licita, nunca los de JADE')
        self.assertTrue(all(s['archivos'] for s in soportes))
        estudios = self.env['stn.requisito'].search([('empresa_id', '=', self.perlop.id),
                                                     ('name', 'like', 'Estudios clínicos')])
        acta = self.env['stn.requisito'].search([('empresa_id', '=', self.perlop.id), ('name', 'like', 'Acta')])
        acta_jade = self.env['stn.requisito'].search([('empresa_id', '=', jade.id), ('name', 'like', 'Acta')])
        payload = copy.deepcopy(MATRIZ)
        payload['requisitos'][0]['documento_maestro'] = estudios.id
        payload['requisitos'][1]['documento_maestro'] = acta_jade.id  # de otra empresa: no se liga
        payload['soportes'] = [
            {'documento_maestro': estudios.id, 'requisito': '1.1', 'rfc_en_documento': 'POA0101019Z1',
             'fecha_emision_interna': str(estudios.fecha_emision), 'legibilidad': 'dudosa',
             'observacion': 'Sello del laboratorio borroso en la foja 3'},
            {'archivo': 'Acta constitutiva y reformas.pdf', 'rfc_en_documento': 'XYZ990101AAA',
             'requisito': '1.4'},
        ]
        res = self.Service.stn_upsert_encargo(payload)
        tecnicos = self.lead._stn_requisitos_por_pestana('tecnica')
        r11 = tecnicos.filtered(lambda r: r.orden_casilla == '1.1')
        r14 = tecnicos.filtered(lambda r: r.orden_casilla == '1.4')
        self.assertEqual(r11.requisito_id, estudios, 'El documento maestro que usó LEXA alimenta el semáforo')
        self.assertFalse(r14.requisito_id, 'Ni documento de otra empresa ni RFC ajeno')
        self.assertEqual(estudios.lexa_legibilidad, 'dudosa')
        self.assertTrue(estudios.lexa_alerta)
        self.assertTrue(acta.lexa_alerta)
        self.assertEqual(acta.lexa_rfc_leido, 'XYZ990101AAA')
        self.assertTrue(any('RFC' in a for a in res['advertencias']))
        self.assertFalse(any('«soportes»' in a for a in res['advertencias']), 'Los soportes ya se procesan')


@tagged('post_install', '-at_install')
class TestLexaHttp(HttpCase):

    def test_endpoints(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('stn_lexa.activo', 'True')
        ICP.set_param('stn_lexa.token', 'tok-lexa')
        ICP.set_param('stn_licitaciones.token', 'tok-licia')
        Lead = self.env['crm.lead']
        Lead.with_context(active_test=False).search([('stn_no_procedimiento', '=', NUMERO)]).unlink()
        lead = Lead.browse(Lead.stn_upsert_ficha({'numero_procedimiento': NUMERO, 'nombre_oportunidad': 'N-134'})['lead_id'])
        conv = self.env['ir.attachment'].create({'name': 'Convocatoria.pdf', 'raw': b'%PDF'})
        lead.stn_documento_ids = [(4, conv.id)]
        self.env['stn.lexa.service'].stn_solicitar(lead, 'matriz', ['tecnica'])
        h = {'Authorization': 'Bearer tok-lexa'}
        self.assertEqual(self.url_open('/stn/lexa/ping', headers={'Authorization': 'Bearer tok-licia'}).status_code, 401,
                         'LEXA tiene su propio token')
        r = self.url_open('/stn/lexa/pendientes', headers=h)
        self.assertEqual(r.status_code, 200)
        pend = r.json()['pendientes']
        self.assertEqual(pend[0]['numero_procedimiento'], NUMERO)
        r = self.url_open('/stn/lexa/expediente?encargo_id=%s' % pend[0]['encargo_id'], headers=h)
        exp = r.json()
        self.assertEqual(exp['encargo']['estado'], 'en_proceso')
        self.assertEqual(self.url_open('/stn/lexa/archivo/%s' % exp['documentos_convocatoria'][0]['id'],
                                       headers=h).content, b'%PDF')
        empresa = self.env['res.partner'].create({'name': 'PERLOP http', 'is_company': True})
        lead.stn_empresa_licitante_id = empresa
        self.env['stn.requisito.prueba.wizard'].create({'empresa_id': empresa.id}).action_cargar()
        exp = self.url_open('/stn/lexa/expediente?numero=%s' % NUMERO, headers=h).json()
        soporte = exp['soportes_empresa'][0]['archivos'][0]
        self.assertTrue(self.url_open('/stn/lexa/archivo/%s' % soporte['id'], headers=h).content.startswith(b'%PDF'))
        otro = self.env['ir.attachment'].create({'name': 'ajeno.pdf', 'raw': b'x'})
        self.assertEqual(self.url_open('/stn/lexa/archivo/%s' % otro.id, headers=h).status_code, 404)
        cuerpo = copy.deepcopy(MATRIZ)
        cuerpo['llave'].pop('empresa')
        cuerpo['encargo_id'] = pend[0]['encargo_id']
        r = self.url_open('/stn/lexa/encargo', data=json.dumps(cuerpo), headers=dict(h, **{'Content-Type': 'application/json'}))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['estado'], 'matriz_lista')
        self.assertEqual(r.json()['requisitos'], 3)
        malo = dict(cuerpo, encargo_id=None, llave={'numero_procedimiento': 'NO-EXISTE', 'parte': 'legal'})
        r = self.url_open('/stn/lexa/encargo', data=json.dumps(malo), headers=dict(h, **{'Content-Type': 'application/json'}))
        self.assertEqual(r.status_code, 422)
