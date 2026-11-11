from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDocumentos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Doc = cls.env['documents.document']
        cls.empresa = cls.env['res.partner'].create({'name': 'PERLOP prueba docs', 'is_company': True})
        cls.otra = cls.env['res.partner'].create({'name': 'JADE prueba docs', 'is_company': True})
        cls.env.company.stn_empresa_grupo_ids = [(6, 0, (cls.empresa | cls.otra).ids)]

    def test_01_estructura_y_alta_en_catalogo(self):
        carpetas = self.Doc._stn_crear_estructura(self.empresa | self.otra)
        n_cat = self.env['stn.requisito.categoria'].search_count([])
        self.assertEqual(len(carpetas), 2 * (n_cat + 1))
        self.assertEqual(self.Doc._stn_crear_estructura(self.empresa), carpetas.filtered(
            lambda c: c.stn_empresa_id == self.empresa), 'No duplica carpetas')
        raiz = self.Doc._stn_raiz()
        self.assertEqual(self.Doc._stn_carpeta_empresa(self.empresa).folder_id, raiz)
        legal = self.env.ref('stn_perlop_licitaciones.cat_legal')
        carpeta = self.Doc._stn_carpeta_categoria(self.empresa, legal)
        self.assertIn('Legal y fiscal', carpeta.name)
        # Subir un archivo a la carpeta → documento maestro con empresa y categoría
        att = self.env['ir.attachment'].create({'name': 'Opinión SAT octubre.pdf', 'raw': b'%PDF-1.4'})
        doc = self.Doc.create({'name': 'Opinión SAT octubre.pdf', 'type': 'binary', 'folder_id': carpeta.id,
                               'attachment_id': att.id})
        req = self.env['stn.requisito'].search([('documento_id', '=', doc.id)])
        self.assertEqual(req.name, 'Opinión SAT octubre')
        self.assertEqual(req.empresa_id, self.empresa)
        self.assertEqual(req.categoria_id, legal)
        self.assertEqual(req._stn_archivos(), att)
        self.assertEqual(self.env['stn.requisito']._stn_buscar_por_archivo(att), req)
        # Un documento maestro capturado antes, con el mismo nombre, se liga en lugar de duplicarse
        previo = self.env['stn.requisito'].create({'name': 'Acta constitutiva', 'empresa_id': self.empresa.id})
        att2 = self.env['ir.attachment'].create({'name': 'Acta constitutiva.pdf', 'raw': b'%PDF-1.4'})
        doc2 = self.Doc.create({'name': 'Acta constitutiva.pdf', 'type': 'binary',
                                'folder_id': self.Doc._stn_carpeta_empresa(self.empresa).id, 'attachment_id': att2.id})
        self.assertEqual(previo.documento_id, doc2)
        # Fuera de las carpetas legales no se registra nada
        suelto = self.Doc.create({'name': 'otro.pdf', 'type': 'binary'})
        self.assertFalse(suelto.stn_requisito_ids)

    def test_02_documentos_de_prueba_en_carpetas(self):
        wiz = self.env['stn.requisito.prueba.wizard'].create({'empresa_id': self.empresa.id})
        wiz.action_cargar()
        reqs = self.env['stn.requisito'].search([('empresa_id', '=', self.empresa.id), ('es_prueba', '=', True)])
        self.assertEqual(len(reqs), 22)
        self.assertTrue(all(r.documento_id for r in reqs))
        self.assertFalse(reqs.mapped('attachment_ids'), 'El archivo vive en Documentos, no como adjunto suelto')
        acta = reqs.filtered(lambda r: r.name == 'Acta constitutiva y reformas')
        self.assertEqual(acta.documento_id.folder_id.stn_categoria_id,
                         self.env.ref('stn_perlop_licitaciones.cat_constitucion'))
        self.assertEqual(acta.documento_id.folder_id.folder_id.stn_empresa_id, self.empresa)
        self.assertEqual(len(reqs.mapped('documento_id')), 22, 'Sin duplicados en el catálogo')
        docs = reqs.mapped('documento_id')
        wiz.action_quitar()
        self.assertFalse(docs.exists())
