import copy
import json
import os

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

RUTA = os.path.join(os.path.dirname(__file__), 'ficha_ejemplo_v1.json')


def ficha():
    with open(RUTA, encoding='utf-8') as f:
        return json.load(f)


@tagged('post_install', '-at_install')
class TestLiciaIngesta(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env['crm.lead']
        cls.env['ir.config_parameter'].sudo().set_param('stn_licitaciones.user_id', cls.env.user.id)
        cls.Lead.with_context(active_test=False).search(
            [('stn_no_procedimiento', 'in', [ficha()['numero_procedimiento'], 'LA-50-GYR-050GYR041-N-135-2026',
                                             'LA-50-GYR-050GYR017-N-3-2027', 'IA-11-B00-011B00001-N-4968-2026',
                                             'IM-2026-000379', 'LA-50-GYR-050GYR026-N-12-2027',
                                             'LA-50-GYR-050GYR012-N-134-2026', 'LA-50-GYR-050GYR069-N-3-2027'])]).unlink()

    def test_01_crea_y_llena_campos(self):
        res = self.Lead.stn_upsert_ficha(ficha())
        self.assertEqual(res['accion'], 'creada')
        lead = self.Lead.browse(res['lead_id'])
        self.assertTrue(lead.team_id.stn_es_licitacion)
        self.assertEqual(lead.stn_no_procedimiento, 'IA-50-GYR-050GYR018-N-210-2026')
        self.assertEqual(lead.stn_viabilidad, '4')
        self.assertEqual(lead.stn_accion, 'perseguir_condicion')
        self.assertEqual(lead.stn_estatus_id.code, 'suspendido')
        self.assertEqual(lead.stn_criterio_id.code, 'puntos')
        self.assertEqual(lead.stn_tipo_procedimiento_id.code, 'IA')
        self.assertEqual(lead.stn_tipo_servicio_id.code, 'viveres')
        self.assertEqual(lead.stn_caracter, 'nacional')
        self.assertAlmostEqual(lead.stn_monto_maximo, 13168217.17, 2)
        self.assertAlmostEqual(lead.expected_revenue, 13168217.17, 2)
        self.assertEqual(lead.stn_minimo_tecnico, 37.5)
        self.assertTrue(lead.stn_operamos_estado)
        self.assertTrue(lead.stn_conjunta_permitida)
        self.assertEqual(lead.state_id.name, 'Tamaulipas')
        self.assertEqual(lead.stn_unidad_compradora_clave, '050GYR018')
        self.assertEqual(lead.partner_id.parent_id, lead.stn_convocante_id)
        self.assertEqual(lead.stn_dependencia_id.name, 'IMSS')
        self.assertEqual(lead.stn_convocante_id.parent_id, lead.stn_dependencia_id)
        self.assertTrue(lead.stn_fechas_verificadas)
        estudios = lead.stn_requisito_ids.filtered(lambda r: r.name.startswith('Estudios clínicos'))
        self.assertEqual(estudios.antiguedad_max_dias, 90)
        self.assertTrue(estudios.extracto_literal)
        self.assertEqual(str(estudios.fecha_referencia), '2026-10-15')
        # 10:00 hora CDMX (UTC-6) = 16:00 UTC
        self.assertEqual(str(lead.stn_fecha_apertura), '2026-10-15 16:00:00')
        self.assertEqual(str(lead.date_deadline), '2026-10-20')  # cierre esperado = fallo
        self.assertFalse(lead.stn_fecha_junta)
        # tablas
        self.assertEqual(len(lead.stn_partida_ids), 8)
        self.assertEqual(lead.stn_partida_ids.filtered(lambda p: p.numero == 7).domicilio_inconsistente, True)
        self.assertEqual(len(lead.stn_requisito_ids), 17)
        self.assertGreaterEqual(lead.stn_requisitos_desechan, 4)
        self.assertEqual(len(lead.stn_punto_ids), 11)
        self.assertAlmostEqual(lead.stn_puntos_maximos, 50.0, 2)
        self.assertEqual(len(lead.stn_pregunta_ids), 12)
        self.assertEqual(len(lead.stn_cambio_ids), 3)
        self.assertEqual(len(lead.stn_antecedente_ids), 1)
        self.assertEqual(lead.stn_antecedente_ids.ganador_id.name, 'Arturo Garza Hernández («Don Sazón»)')
        self.assertEqual(len(lead.stn_competidor_ids), 4)
        self.assertEqual(len(lead.stn_pendiente_ids), 4)
        self.assertEqual(len(lead.stn_seguimiento_ids), 6)
        apertura = lead.stn_evento_ids.filtered(lambda e: e.tipo == 'apertura')
        self.assertEqual(str(apertura.fecha_limite_interna), '2026-10-12 16:00:00')
        self.assertFalse(lead.stn_evento_ids.filtered(lambda e: e.tipo == 'junta').aplica)
        # nivel 4 → pasa sola a análisis
        self.assertEqual(lead.stage_id.stn_codigo, 'analisis')
        self.assertTrue(lead.stn_fecha_analisis)

    def test_02_actualiza_sin_duplicar_ni_pisar_decisiones(self):
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        p1 = lead.stn_partida_ids.filtered(lambda p: p.numero == 1)
        p1.participamos = 'si'
        datos = ficha()
        datos['estatus_procedimiento'] = 'VIGENTE'
        datos['fecha_apertura'] = '2026-10-22 10:00'
        datos['eventos'][5]['fecha_oficial'] = '2026-10-22 10:00'
        datos['seguimiento'].append({'fecha': '2026-10-16', 'texto': 'Se reanuda el procedimiento.'})
        datos['partidas'][0]['participamos'] = 'NO'
        res2 = self.Lead.stn_upsert_ficha(datos)
        self.assertEqual(res2['accion'], 'actualizada')
        self.assertEqual(res2['lead_id'], lead.id)
        self.assertEqual(self.Lead.search_count([('stn_no_procedimiento', '=', datos['numero_procedimiento'])]), 1)
        self.assertEqual(lead.stn_estatus_id.code, 'vigente')
        self.assertEqual(len(lead.stn_partida_ids), 8)
        self.assertEqual(p1.participamos, 'si', 'No debe pisar la decisión del equipo')
        self.assertEqual(len(lead.stn_requisito_ids), 17)
        self.assertEqual(len(lead.stn_seguimiento_ids), 7)
        self.assertTrue(lead.stn_cambio_ids.filtered(lambda c: c.fuente == 'LICIA'),
                        'El cambio de fecha de apertura debe quedar en el historial')

    def test_03_regla_directores(self):
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        usuario = self.env['res.users'].create({
            'name': 'Auxiliar jurídico', 'login': 'aux_lic_test',
            'group_ids': [(6, 0, [self.env.ref('stn_perlop_licitaciones.group_licitaciones_user').id])]})
        lead_u = lead.with_user(usuario)
        with self.assertRaises(UserError):
            lead_u.write({'stage_id': lead._stn_etapa('revision').id})
        accion = lead_u.action_stn_pasar_preparacion()
        self.assertEqual(accion['res_model'], 'stn.licitacion.aprobar.wizard', 'Al aprobar se elige al líder')
        wiz = self.env['stn.licitacion.aprobar.wizard'].with_user(usuario).with_context(accion['context']).create(
            {'lider_id': usuario.id})
        wiz.action_confirmar()
        self.assertEqual(lead.stage_id.stn_codigo, 'preparacion')
        self.assertEqual(lead.stn_lider_id, usuario)
        self.assertTrue(lead.stn_fecha_aprobacion)

    def test_04b_ganado_exige_fallo_y_crea_pendientes(self):
        import base64
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        with self.assertRaises(UserError):
            lead.action_stn_pasar_ganado()
        lead.stn_acta_fallo = base64.b64encode(b'%PDF-1.4 acta')
        lead.stn_partida_ids.filtered(lambda p: p.numero in (1, 2)).write({'participamos': 'si', 'ganada': 'si'})
        lead.stn_partida_ids.filtered(lambda p: p.numero == 3).write({'participamos': 'si', 'ganada': 'no'})
        lead.stn_partida_ids.filtered(lambda p: p.numero > 3).write({'participamos': 'no'})
        lead.action_stn_pasar_ganado()
        self.assertEqual(lead.stage_id.stn_codigo, 'ganado')
        self.assertEqual(lead.stn_resultado, 'parcial')
        nombres = lead.stn_pendiente_ids.mapped('name')
        self.assertIn('Fianza de cumplimiento', nombres)
        self.assertTrue(all(p.estado == 'activo' for p in lead.stn_pendiente_ids))

    def test_04c_numero_y_semaforo_por_licitacion(self):
        from dateutil.relativedelta import relativedelta
        from odoo import fields
        lead = self.Lead.create({'name': 'Prueba', 'type': 'opportunity',
                                 'team_id': self.env.ref('stn_perlop_licitaciones.team_licitaciones').id,
                                 'stn_no_procedimiento': 'LA-50-GYR-050GYR075-N-151-2026'})
        self.assertEqual(lead.stn_tipo_procedimiento_id.code, 'LA')
        self.assertEqual(lead.stn_caracter, 'nacional')
        self.assertEqual(lead.stn_unidad_compradora_clave, '050GYR075')
        hoy = fields.Date.today()
        doc = self.env['stn.requisito'].create({'name': 'Estudios clínicos EMA', 'fecha_emision': hoy - relativedelta(days=80),
                                                'vigencia_meses': 6, 'dias_tramite': 10})
        req = self.env['stn.licitacion.requisito'].create({'lead_id': lead.id, 'name': 'Estudios', 'requisito_id': doc.id,
                                                            'antiguedad_max_dias': 90,
                                                            'fecha_referencia': hoy + relativedelta(days=5)})
        self.assertEqual(req.semaforo, 'amarillo')
        req.fecha_referencia = hoy + relativedelta(days=30)   # se difiere la apertura
        self.assertEqual(req.semaforo, 'naranja')
        req.fecha_referencia = hoy + relativedelta(days=12)
        doc.dias_tramite = 20
        self.assertEqual(req.semaforo, 'rojo')

    def test_04d_aviso_y_escalamiento(self):
        from datetime import timedelta
        from odoo import fields
        gerente = self.env['res.users'].create({'name': 'Gerencia', 'login': 'ger_lic_test'})
        self.env.company.stn_usuarios_gerencia_ids = [(6, 0, gerente.ids)]
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        ev = lead.stn_evento_ids.filtered(lambda e: e.tipo == 'limite_preguntas')
        ev.write({'fecha_oficial': fields.Datetime.now() + timedelta(days=3), 'anticipacion_horas': 48})
        self.assertTrue(ev.activity_id)
        self.assertTrue(lead.stn_cambio_ids.filtered(lambda c: c.campo == 'Límite para preguntas'))
        ev._cron_stn_avisos()
        self.assertTrue(ev.aviso_enviado)
        # límite vencido, fecha oficial aún por venir → se escala una sola vez
        ev.write({'fecha_oficial': fields.Datetime.now() + timedelta(hours=2), 'anticipacion_horas': 5})
        self.assertFalse(ev.escalado)
        ev._cron_stn_avisos()
        ev._cron_stn_avisos()
        self.assertTrue(ev.escalado)
        vencidos = lead.activity_ids.filtered(lambda a: a.user_id == gerente and a.summary.startswith('VENCIDO'))
        self.assertEqual(len(vencidos), 1)

    def test_07_avisos_sin_ruido(self):
        """Revisión 30-oct: publicación/fallo/inicio no generan límite; reenviar la misma fecha no
        vuelve a escalar; la apertura se activa al aprobar; un evento pasado no se escala."""
        from datetime import timedelta
        from odoo import fields
        gerente = self.env['res.users'].create({'name': 'Gerencia 2', 'login': 'ger_lic_test2'})
        self.env.company.stn_usuarios_gerencia_ids = [(6, 0, gerente.ids)]
        ahora = fields.Datetime.now()
        fmt = lambda dt: fields.Datetime.context_timestamp(
            self.env['crm.lead'].with_context(tz='America/Mexico_City'), dt).strftime('%Y-%m-%d %H:%M')
        datos = {
            'numero_procedimiento': 'LA-50-GYR-050GYR041-N-135-2026', 'nombre_oportunidad': 'Tlaxcala',
            'eventos': [
                {'tipo': 'publicacion', 'fecha_oficial': fmt(ahora - timedelta(days=5))},
                {'tipo': 'limite_preguntas', 'fecha_oficial': fmt(ahora + timedelta(hours=3)),
                 'fecha_limite_interna': fmt(ahora - timedelta(hours=1))},
                {'tipo': 'junta', 'fecha_oficial': fmt(ahora - timedelta(hours=2)),
                 'fecha_limite_interna': fmt(ahora - timedelta(hours=26))},
                {'tipo': 'apertura', 'fecha_oficial': fmt(ahora + timedelta(days=6)),
                 'fecha_limite_interna': fmt(ahora + timedelta(days=3))},
                {'tipo': 'fallo', 'fecha_oficial': fmt(ahora + timedelta(days=9))},
                {'tipo': 'inicio_contrato', 'fecha_oficial': fmt(ahora + timedelta(days=20))},
            ]}
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha(datos)['lead_id'])
        self.assertEqual(lead.stage_id.stn_codigo, 'nueva')
        ev = {e.tipo: e for e in lead.stn_evento_ids}
        for tipo in ('publicacion', 'fallo', 'inicio_contrato'):
            self.assertFalse(ev[tipo].fecha_limite_interna, tipo)
            self.assertFalse(ev[tipo].activity_id, tipo)
        self.assertAlmostEqual(ev['apertura'].anticipacion_horas, 72.0, 1)
        self.assertFalse(ev['apertura'].activity_id, 'Plazo de preparación: aún no aprobada')
        for _i in range(3):  # tres corridas diarias con las mismas fechas
            self.Lead.stn_upsert_ficha(datos)
            self.env['stn.licitacion.evento']._cron_stn_avisos()
        vencidos = lead.activity_ids.filtered(lambda a: (a.summary or '').startswith('VENCIDO'))
        self.assertEqual(vencidos.mapped('summary'), ['VENCIDO sin atender: Límite para preguntas'],
                         'Solo el límite de preguntas (oficial aún por venir), una vez')
        self.assertTrue(ev['junta'].escalado, 'La junta ya pasó: se marca sin escalar')
        lead.stn_lider_id = self.env.user
        lead._stn_mover('preparacion')
        self.assertTrue(ev['apertura'].activity_id, 'Al aprobar se activa el límite de la apertura')
        # completar la actividad del límite → el evento queda hecho y no se recrea
        ev['apertura'].activity_id.action_feedback(feedback='Lista')
        self.assertTrue(ev['apertura'].hecho)
        self.Lead.stn_upsert_ficha(datos)
        self.assertFalse(ev['apertura'].activity_id.filtered('active'), 'No se recrea la actividad ya hecha')

    def test_08_partidas_y_sedes_se_reemplazan(self):
        base = {'numero_procedimiento': 'LA-50-GYR-050GYR017-N-3-2027', 'nombre_oportunidad': 'Hidalgo'}
        dia1 = dict(base, partidas=[
            {'clave': 'Partida 1', 'maximo': 100, 'unidad': 'HGZ 1', 'domicilio': 'Calle 1', 'corredor': 'Pachuca'},
            {'clave': 'Partida 2', 'maximo': 200, 'unidad': 'HGZ 2', 'domicilio': 'Calle 2'},
            {'clave': 'Partida 3', 'maximo': 300},
            {'clave': 'Partida 4', 'maximo': 400}])
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha(dia1)['lead_id'])
        self.assertEqual(len(lead.stn_partida_ids), 4)
        self.assertEqual(sorted(lead.stn_sede_ids.mapped('unidad')), ['HGZ 1', 'HGZ 2'],
                         'La logística de la partida pasa a Sedes')
        p1 = lead.stn_partida_ids.filtered(lambda p: p.clave == 'Partida 1')
        self.assertEqual(p1.sede_ids.unidad, 'HGZ 1')
        lead.stn_partida_ids.filtered(lambda p: p.clave == 'Partida 4').ganada = 'si'
        dia2 = dict(base, partidas=[{'clave': '1', 'maximo': 110}, {'clave': '02', 'maximo': 220}],
                    sedes=[{'unidad': 'HGZ 5', 'partidas': ['1', '2'], 'domicilio': 'Calle 5'}])
        res = self.Lead.stn_upsert_ficha(dia2)
        self.assertEqual(sorted(lead.stn_partida_ids.mapped('maximo')), [110, 220, 400],
                         'Mismas partidas con otra forma de nombrarlas; la 3 se va; la 4 se queda (ganada)')
        self.assertTrue(res['advertencias'])
        self.assertEqual(lead.stn_sede_ids.mapped('unidad'), ['HGZ 5'])
        manual = self.env['stn.licitacion.sede'].create({'lead_id': lead.id, 'unidad': 'Almacén manual'})
        self.Lead.stn_upsert_ficha(dia2)
        self.assertTrue(manual.exists(), 'Las sedes capturadas a mano se respetan')

    def test_09_deteccion_area_cierre_y_actividad_unica(self):
        from datetime import timedelta
        from odoo import fields
        datos = {'numero_procedimiento': 'IA-11-B00-011B00001-N-4968-2026', 'nombre_oportunidad': 'IPN',
                 'fecha_deteccion': '2026-10-29 08:30',
                 'unidad_compradora': '011B00001 Dirección de Recursos Materiales',
                 'area_requirente': 'Dirección de Recursos Materiales'}
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha(datos)['lead_id'])
        detectada = lead.stn_fecha_deteccion
        self.assertTrue(detectada)
        self.assertFalse(lead.stn_area_requirente, 'Repetir la unidad compradora no es área requirente')
        self.Lead.stn_upsert_ficha(dict(datos, fecha_deteccion='2026-10-30 08:30',
                                        area_requirente='Coordinación de Servicios Sociales'))
        self.assertEqual(lead.stn_fecha_deteccion, detectada, '«Detectada» guarda la primera detección')
        self.assertEqual(lead.stn_area_requirente, 'Coordinación de Servicios Sociales')
        # avisos de etapa sin duplicar
        analista = self.env['res.users'].create({'name': 'Analista', 'login': 'ana_lic_test'})
        lead._stn_notificar(analista, 'Revisar y analizar licitación')
        lead._stn_notificar(analista, 'Revisar y analizar licitación')
        self.assertEqual(len(lead.activity_ids.filtered(lambda a: a.user_id == analista)), 1)
        # apertura pasada sin aprobar → se cierra «Fuera de plazo»
        self.env['ir.config_parameter'].sudo().set_param('stn_licitaciones.cerrar_no_presentadas', 'True')
        lead.stn_fecha_apertura = fields.Datetime.now() - timedelta(hours=1)
        self.Lead._cron_stn_evaluacion()
        self.assertFalse(lead.active)
        self.assertEqual(lead.lost_reason_id, self.env.ref('stn_perlop_licitaciones.lost_fuera_plazo'))

    def test_10_etapas_y_lider(self):
        nombres = {e.stn_codigo: e.name for e in self.env['crm.stage'].search([('stn_codigo', '!=', False)])}
        self.assertEqual(nombres['analisis'], 'Análisis de participación')
        self.assertEqual(nombres['preparacion'], 'Preparación de propuesta')
        self.assertEqual(nombres['revision'], 'Integración final')
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        self.assertEqual(lead.stage_id.stn_codigo, 'analisis')
        with self.assertRaises(UserError):  # sin líder no pasa a preparación
            lead.write({'stage_id': lead._stn_etapa('preparacion').id})
        lider = self.env['res.users'].create({'name': 'Líder', 'login': 'lider_lic_test'})
        self.env['stn.licitacion.aprobar.wizard'].create({'lead_id': lead.id, 'lider_id': lider.id}).action_confirmar()
        self.assertEqual(lead.stage_id.stn_codigo, 'preparacion')
        self.assertEqual(lead.stn_lider_id, lider)
        self.assertTrue(lead.activity_ids.filtered(lambda a: a.user_id == lider))

    def test_11_im_sale_la_licitacion(self):
        datos = {'numero_procedimiento': 'IM-2026-000379', 'tipo_registro': 'INVESTIGACION DE MERCADO',
                 'nombre_oportunidad': 'IM víveres IMSS Sonora', 'dependencia': 'IMSS',
                 'convocante': 'IMSS - OOAD Sonora', 'objeto': 'Víveres 2027', 'estado': 'Sonora', 'nivel_licia': 5}
        im = self.Lead.browse(self.Lead.stn_upsert_ficha(datos)['lead_id'])
        self.assertEqual(im.stn_tipo_registro, 'investigacion_mercado')
        self.assertEqual(im.stage_id.stn_codigo, 'nueva', 'Una IM no entra al flujo de licitaciones')
        accion = im.action_stn_salio_licitacion()
        wiz = self.env['stn.licitacion.publicada.wizard'].with_context(accion['context']).create(
            {'numero': 'LA-50-GYR-050GYR026-N-12-2027'})
        wiz._onchange_numero()
        res = wiz.action_confirmar()
        lic = self.Lead.browse(res['res_id'])
        self.assertEqual(lic.stn_tipo_registro, 'licitacion')
        self.assertEqual(lic.stage_id.stn_codigo, 'analisis', 'Sale directo a análisis de participación')
        self.assertEqual(lic.stn_convocante_id, im.stn_convocante_id)
        self.assertEqual(lic.state_id.name, 'Sonora')
        self.assertEqual(im.stn_im_estado, 'publicada')
        self.assertNotEqual(lic, im)
        # LICIA manda después la misma licitación: se actualiza, no se duplica ni regresa a Nuevas
        self.Lead.stn_upsert_ficha({'numero_procedimiento': 'LA-50-GYR-050GYR026-N-12-2027', 'objeto': 'Víveres'})
        self.assertEqual(self.Lead.search_count([('stn_no_procedimiento', '=', 'LA-50-GYR-050GYR026-N-12-2027')]), 1)
        self.assertEqual(lic.stage_id.stn_codigo, 'analisis')

    def test_12_avance_por_pestana_y_casilla(self):
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha(ficha())['lead_id'])
        reqs = lead.stn_requisito_ids
        self.assertTrue(all(r.pestana for r in reqs.filtered('tipo')))
        legales = lead._stn_requisitos_por_pestana('legal')
        self.assertTrue(legales)
        for i, r in enumerate(legales, 1):
            r.orden_casilla = str(i)
        legales[:2].write({'avance': 'completo'})
        legales[2:3].write({'avance': 'incompleto'})
        cuenta = legales.filtered(lambda r: r.avance != 'no_aplica')
        self.assertAlmostEqual(lead.stn_avance_legal, round(100.0 * 2 / len(cuenta), 1), 1)
        self.assertIn('L ', lead.stn_avance_corto)
        html = str(lead.stn_avance_html)
        self.assertIn('text-bg-success', html)
        self.assertIn('text-bg-warning', html)
        self.assertIn('>1<', html)

    def test_13_documentos_de_prueba(self):
        empresa = self.env['res.partner'].create({'name': 'Empresa Prueba Docs', 'is_company': True})
        self.env.company.stn_empresa_grupo_ids = [(4, empresa.id)]
        wiz = self.env['stn.requisito.prueba.wizard'].create({'empresa_id': empresa.id})
        wiz.action_cargar()
        docs = self.env['stn.requisito'].search([('empresa_id', '=', empresa.id)])
        self.assertEqual(len(docs), 22)
        self.assertTrue(all(d._stn_archivos() for d in docs))
        self.assertTrue(docs[0]._stn_archivos()[0].raw.startswith(b'%PDF'))
        self.assertEqual(self.env['stn.requisito']._stn_buscar_por_archivo(docs[0]._stn_archivos()[:1]), docs[0])
        codigos = set(docs.mapped('stage_code'))
        self.assertTrue({'vigente', 'vencido', 'proximo', 'sin_vencimiento'} <= codigos, codigos)
        wiz.action_cargar()  # no duplica
        self.assertEqual(self.env['stn.requisito'].search_count([('empresa_id', '=', empresa.id)]), 22)
        wiz.action_quitar()
        self.assertFalse(self.env['stn.requisito'].search_count([('empresa_id', '=', empresa.id)]))

    def test_14_requisitos_se_reemplazan(self):
        base = {'numero_procedimiento': 'LA-50-GYR-050GYR069-N-3-2027', 'nombre_oportunidad': 'Campeche'}
        dia1 = dict(base, requisitos=[
            {'referencia': '4.1.1', 'requisito': 'Acreditamiento de personalidad', 'tipo': 'Legal'},
            {'referencia': '4.1.4', 'requisito': 'Declaración de integridad', 'tipo': 'Legal'},
            {'referencia': '4.1.13', 'requisito': 'Opinión SAT', 'tipo': 'Legal'},
            {'referencia': '', 'requisito': 'Escrito sin referencia', 'tipo': 'Forma'},
        ])
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha(dia1)['lead_id'])
        self.assertEqual(len(lead.stn_requisito_ids), 4)
        opinion = lead.stn_requisito_ids.filtered(lambda r: r.referencia == '4.1.13')
        opinion.avance = 'completo'  # el equipo ya lo trabajó
        dia2 = dict(base, requisitos=[
            {'referencia': '4.1.1', 'requisito': 'Acreditamiento de la personalidad jurídica', 'tipo': 'Legal'},
            {'referencia': '', 'requisito': 'Escrito sin referencia', 'tipo': 'Forma'},
            {'referencia': '4.1.5', 'requisito': 'Manifiesto de vínculos', 'tipo': 'Legal'},
        ])
        res = self.Lead.stn_upsert_ficha(dia2)
        refs = sorted(lead.stn_requisito_ids.mapped(lambda r: r.referencia or ''))
        self.assertEqual(refs, ['', '4.1.1', '4.1.13', '4.1.5'],
                         'Misma referencia = mismo requisito; el que ya no viene se va, salvo el trabajado')
        self.assertEqual(lead.stn_requisito_ids.filtered(lambda r: r.referencia == '4.1.1').name,
                         'Acreditamiento de la personalidad jurídica')
        self.assertTrue(opinion.exists())
        self.assertTrue(res['advertencias'])
        self.Lead.stn_upsert_ficha(dia2)
        self.assertEqual(len(lead.stn_requisito_ids), 4, 'Reenviar la misma ficha no duplica')

    def test_04e_reporte_diario(self):
        import json as _json, os as _os
        with open(_os.path.join(_os.path.dirname(__file__), 'reporte_diario_ejemplo_v1.json'), encoding='utf-8') as f:
            datos = _json.load(f)
        rep = self.env['stn.licia.reporte'].stn_registrar(datos)
        self.assertEqual(rep.revisados, 214)
        self.assertEqual(len(rep.linea_ids), 2)
        self.assertTrue(rep.message_id)

    def test_04f_ficha_binaria_partidas_por_grupo_y_sedes(self):
        datos = {
            'numero_procedimiento': 'LA-50-GYR-050GYR012-N-134-2026',
            'nombre_oportunidad': 'LA-50-GYR-050GYR012-N-134-2026 · Víveres · IMSS Colima',
            'nivel_licia': 4, 'accion': 'PERSEGUIR · participar realizando los ajustes',
            'dependencia': 'IMSS', 'convocante': 'IMSS - OOAD Regional Colima',
            'tipo_procedimiento': 'Licitación pública electrónica', 'criterio': 'Binario',
            'minimo_tecnico': 'N/A', 'monto_minimo': 'N/A', 'monto_maximo': 'N/A',
            'monto_minimo_estimado': 726767, 'monto_maximo_estimado': 1785466,
            'fecha_apertura': '2026-10-13 09:30', 'fecha_limite_interna': '2026-10-10 09:30',
            'fecha_fallo': '2026-10-15 12:00',
            'condiciones_entrega': 'Horario 06:00-08:00; pan y tortilla diarios.',
            'partidas': [
                {'clave': 'G3', 'ganador_anterior': 'Sustenta Alimentos', 'maximo_anterior': 5354726.05,
                 'suma_precios_ganador': 1000, 'nuestra_suma_precios': 1464, 'maximo': 400000, 'maximo_estimado': 'SI'},
                {'clave': 'G7A', 'ganador_anterior': 'Sustenta Alimentos'},
                {'clave': 'G7B', 'ganador_anterior': 'Sustenta Alimentos'},
            ],
            'sedes': [
                {'unidad': 'HGZ 1', 'partidas': ['G3', 'G4', 'G5', 'G6', 'G7A', 'G7B', 'G8'], 'corredor': 'Zona conurbada',
                 'vehiculos': '1 caja seca + 2 refrigerados', 'cedis': 'Almacén Colima · sin medir'},
                {'unidad': 'HGZ 10', 'corredor': 'Costa'},
            ],
            'requisitos': [{'referencia': '3.1.1 I', 'requisito': 'Acreditamiento de personalidad', 'tipo': 'Legal',
                            'situacion': 'TENEMOS', 'nota': 'acuse 29-jul: ¿socios vigentes?', 'efecto': 'Cumplimiento'}],
        }
        res = self.Lead.stn_upsert_ficha(datos)
        lead = self.Lead.browse(res['lead_id'])
        self.assertEqual(lead.stn_modalidad, 'electronica')
        self.assertEqual(lead.stn_tipo_procedimiento_id.code, 'LA')
        self.assertFalse(lead.stn_monto_maximo)
        self.assertAlmostEqual(lead.expected_revenue, 1785466.0)
        self.assertEqual(str(lead.date_deadline), '2026-10-15')
        self.assertEqual(lead.stn_partida_ids.mapped('clave'), ['G3', 'G7A', 'G7B'])
        g3 = lead.stn_partida_ids.filtered(lambda p: p.clave == 'G3')
        self.assertAlmostEqual(g3.diferencia_pct, 46.4, 1)
        self.assertTrue(g3.ganador_anterior_id.stn_es_competidor)
        self.assertEqual(len(lead.stn_sede_ids), 2)
        self.assertIn('G7A', lead.stn_sede_ids.filtered(lambda x: x.unidad == 'HGZ 1').partidas)
        self.assertEqual(lead.stn_requisito_ids.nota, 'acuse 29-jul: ¿socios vigentes?')
        self.assertTrue(lead.stn_evento_ids.filtered(lambda e: e.tipo == 'apertura').cae_fin_semana is not None)
        # segunda vez: no duplica partidas G7A/G7B
        self.Lead.stn_upsert_ficha(datos)
        self.assertEqual(len(lead.stn_partida_ids), 3)

    def test_04g_analizar_con_licia(self):
        import base64
        from unittest.mock import patch, MagicMock
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('stn_licitaciones.claude_routine_url', 'https://api.anthropic.com/v1/claude_code/routines/trig_x/fire')
        ICP.set_param('stn_licitaciones.claude_routine_token', 'sk-test')
        self.Lead.with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', 'LA-50-GYR-050GYR041-N-135-2026')]).unlink()
        lead = self.Lead.browse(self.Lead.stn_upsert_ficha({'numero_procedimiento': 'LA-50-GYR-050GYR041-N-135-2026',
                                                            'accion': 'ANALIZAR'})['lead_id'])
        with self.assertRaises(UserError):
            lead.action_stn_analizar_licia()   # sin documentos
        att = self.env['ir.attachment'].create({'name': 'Convocatoria.pdf', 'raw': b'%PDF-1.4 convocatoria'})
        lead.stn_documento_ids = [(4, att.id)]
        self.assertEqual((att.res_model, att.res_id), ('crm.lead', lead.id))
        resp = MagicMock(status_code=201, text='{}', headers={'Content-Type': 'application/json'})
        resp.json.return_value = {'claude_code_session_url': 'https://claude.ai/code/session_1'}
        with patch('odoo.addons.stn_perlop_licitaciones.models.stn_licia_service.requests.post',
                   return_value=resp) as post:
            lead.action_stn_analizar_licia()
        texto = post.call_args.kwargs['json']['text']
        self.assertIn('ANALIZAR_PROCEDIMIENTO LA-50-GYR-050GYR041-N-135-2026', texto)
        self.assertIn('/stn/licitaciones/documentos?numero=', texto)
        self.assertEqual(lead.stn_analisis_estado, 'solicitado')
        self.assertEqual(lead.stn_analisis_sesion, 'https://claude.ai/code/session_1')
        params = self.env['stn.licia.service'].stn_parametros()
        self.assertIn('LA-50-GYR-050GYR041-N-135-2026', [p['numero_procedimiento'] for p in params['analisis_pendientes']])
        # LICIA responde con la ficha completa
        self.Lead.stn_upsert_ficha({'numero_procedimiento': 'LA-50-GYR-050GYR041-N-135-2026', 'nivel_licia': 4,
                                    'analisis_documentos': 'SI', 'analisis_resumen': '3 documentos leídos',
                                    'requisitos': [{'referencia': '4.1', 'requisito': 'e.firma', 'tipo': 'Forma',
                                                    'situacion': 'SE GENERA'}],
                                    'adjuntos': [{'nombre': 'Anexo_Tecnico.pdf',
                                                  'contenido_base64': base64.b64encode(b'%PDF anexo').decode()}]})
        self.assertEqual(lead.stn_analisis_estado, 'completado')
        self.assertEqual(lead.stn_viabilidad, '4')
        self.assertEqual(len(lead.stn_requisito_ids), 1)
        self.assertEqual(lead.stn_documentos_count, 2)

    def test_04_ganar_activa_pendientes(self):
        res = self.Lead.stn_upsert_ficha(ficha())
        lead = self.Lead.browse(res['lead_id'])
        lead.stn_resultado = 'parcial'
        self.assertTrue(all(p.estado == 'activo' for p in lead.stn_pendiente_ids))
        self.assertTrue(lead.activity_ids.filtered(lambda a: a.summary == 'Firma del contrato'))

    def test_05_correo_respaldo_clave_valor(self):
        team = self.env.ref('stn_perlop_licitaciones.team_licitaciones')
        cuerpo = '\n'.join([
            'numero_procedimiento: LA-50-GYR-TEST-N-1-2026',
            'nombre_oportunidad: Prueba por correo',
            'nivel_licia: 5',
            'estatus_procedimiento: VIGENTE',
            'monto_maximo: 1000000',
            'fecha_apertura: 2026-11-20 10:00',
        ])
        lead = self.Lead.with_context(default_team_id=team.id).message_new(
            {'subject': '[FICHA LICITACIÓN] LA-50-GYR-TEST-N-1-2026', 'body': '<pre>%s</pre>' % cuerpo,
             'from': 'licia@example.com', 'attachments': []}, {'team_id': team.id})
        self.assertEqual(lead.stn_no_procedimiento, 'LA-50-GYR-TEST-N-1-2026')
        self.assertEqual(lead.stn_viabilidad, '5')
        self.assertAlmostEqual(lead.stn_monto_maximo, 1000000.0)

    def test_06_semaforo_requisito(self):
        from dateutil.relativedelta import relativedelta
        from odoo import fields
        hoy = fields.Date.today()
        req = self.env['stn.requisito'].create({'name': 'Análisis EMA', 'fecha_emision': hoy - relativedelta(months=3, days=-10),
                                                'vigencia_meses': 3, 'dias_tramite': 15})
        req.action_stn_actualizar_semaforo()
        self.assertEqual(req.stage_code, 'proximo')
        self.assertEqual(req.dias_restantes, 10)


@tagged('post_install', '-at_install')
class TestLiciaHttp(HttpCase):

    def test_endpoint(self):
        self.env['crm.lead'].with_context(active_test=False).search(
            [('stn_no_procedimiento', '=', ficha()['numero_procedimiento'])]).unlink()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('stn_licitaciones.activo', 'True')
        ICP.set_param('stn_licitaciones.token', 'tok-prueba')
        ICP.set_param('stn_licitaciones.user_id', self.env.ref('base.user_admin').id)
        r = self.url_open('/stn/licitaciones/ficha', data=json.dumps(ficha()),
                          headers={'Authorization': 'Bearer malo', 'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 401)
        r = self.url_open('/stn/licitaciones/ficha', data=json.dumps(ficha()),
                          headers={'Authorization': 'Bearer tok-prueba', 'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 200, r.text)
        datos = r.json()
        self.assertTrue(datos['ok'])
        self.assertEqual(datos['accion'], 'creada')
        # Sin responsable configurado debe usar al administrador (antes fallaba con res.users())
        ICP.set_param('stn_licitaciones.user_id', False)
        r = self.url_open('/stn/licitaciones/ficha', data=json.dumps({'numero_procedimiento': 'LA-25-C00-025C00001-N-70-2026',
                                                                      'accion': 'ANALIZAR', 'monto_maximo': 1000}),
                          headers={'Authorization': 'Bearer tok-prueba', 'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['accion'], 'creada')
        r = self.url_open('/stn/licitaciones/reporte', data=json.dumps({'fecha': '2026-10-28', 'revisados': 9}),
                          headers={'Authorization': 'Bearer tok-prueba', 'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.url_open('/stn/licitaciones/parametros', headers={'Authorization': 'Bearer tok-prueba'})
        self.assertTrue(r.json()['empresa'])
        # documentos: lista y descarga
        lead = self.env['crm.lead'].search([('stn_no_procedimiento', '=', ficha()['numero_procedimiento'])])
        att = self.env['ir.attachment'].create({'name': 'Convocatoria.pdf', 'raw': b'%PDF-1.4 hola'})
        lead.stn_documento_ids = [(4, att.id)]
        otro = self.env['ir.attachment'].create({'name': 'ajeno.pdf', 'raw': b'secreto'})
        r = self.url_open('/stn/licitaciones/documentos?numero=%s' % lead.stn_no_procedimiento,
                          headers={'Authorization': 'Bearer tok-prueba'})
        self.assertEqual(r.status_code, 200, r.text)
        docs = r.json()['documentos']
        self.assertEqual([d['nombre'] for d in docs], ['Convocatoria.pdf'])
        r = self.url_open('/stn/licitaciones/documento/%s' % att.id, headers={'Authorization': 'Bearer tok-prueba'})
        self.assertEqual(r.content, b'%PDF-1.4 hola')
        r = self.url_open('/stn/licitaciones/documento/%s' % otro.id, headers={'Authorization': 'Bearer tok-prueba'})
        self.assertEqual(r.status_code, 404, 'No debe exponer adjuntos que no son de una licitación')
        r = self.url_open('/stn/licitaciones/documento/%s' % att.id, headers={'Authorization': 'Bearer malo'})
        self.assertEqual(r.status_code, 401)
        r = self.url_open('/stn/licitaciones/parametros', headers={'Authorization': 'Bearer tok-prueba'})
        self.assertEqual(r.status_code, 200)
        params = r.json()
        self.assertIn('IA-50-GYR-050GYR018-N-210-2026',
                      [p['numero_procedimiento'] for p in params['procedimientos_en_seguimiento']])
