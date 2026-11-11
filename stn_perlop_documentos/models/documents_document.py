import logging
import os

from odoo import _, api, fields, models

from odoo.addons.stn_perlop_licitaciones.models import licia_parser as P

_logger = logging.getLogger(__name__)

RAIZ = 'Licitaciones · Documentos de la empresa'


class DocumentsDocument(models.Model):
    """Carpetas y archivos de Documentos ligados al catálogo de documentos maestros.

    Estructura: «Licitaciones · Documentos de la empresa / <Empresa> / NN <Categoría>».
    Un archivo que se sube a la carpeta de una empresa crea (o actualiza) su documento maestro
    en «Requisitos (vigencias)».
    """
    _inherit = 'documents.document'

    stn_empresa_id = fields.Many2one('res.partner', 'Empresa del grupo (carpeta)', index=True)
    stn_categoria_id = fields.Many2one('stn.requisito.categoria', 'Categoría (carpeta)')
    stn_es_raiz = fields.Boolean('Raíz de documentos legales')
    stn_requisito_ids = fields.One2many('stn.requisito', 'documento_id', 'Documento maestro')

    # ------------------------------------------------------------------
    # Estructura de carpetas
    # ------------------------------------------------------------------
    @api.model
    def _stn_vals(self, vals):
        """Solo los campos que existen en esta versión de Documentos."""
        return {k: v for k, v in vals.items() if k in self._fields}

    @api.model
    def _stn_carpeta(self, nombre, padre=False, **extra):
        Doc = self.sudo().with_context(active_test=False)
        dominio = [('type', '=', 'folder'), ('folder_id', '=', padre.id if padre else False)]
        if extra.get('stn_es_raiz'):
            dominio.append(('stn_es_raiz', '=', True))
        elif extra.get('stn_categoria_id'):
            dominio.append(('stn_categoria_id', '=', extra['stn_categoria_id']))
        elif extra.get('stn_empresa_id'):
            dominio.append(('stn_empresa_id', '=', extra['stn_empresa_id']))
        else:
            dominio.append(('name', '=', nombre))
        carpeta = Doc.search(dominio, limit=1)
        if carpeta:
            if not carpeta.active:
                carpeta.active = True
            return carpeta
        root = self.env.ref('base.user_root', raise_if_not_found=False)
        vals = {
            'name': nombre, 'type': 'folder', 'folder_id': padre.id if padre else False,
            # Carpeta de la empresa (sección «Compañía»), cerrada: se comparte solo con el equipo de Licitaciones
            'owner_id': root.id if root else False, 'access_internal': 'none', 'company_id': False,
        }
        vals.update(extra)
        return Doc.create(self._stn_vals(vals))

    @api.model
    def _stn_raiz(self):
        return self._stn_carpeta(RAIZ, stn_es_raiz=True)

    @api.model
    def _stn_carpeta_empresa(self, empresa):
        carpeta = self._stn_carpeta(empresa.name, self._stn_raiz(), stn_empresa_id=empresa.id)
        if carpeta.name != empresa.name:
            carpeta.name = empresa.name
        return carpeta

    @api.model
    def _stn_carpeta_categoria(self, empresa, categoria):
        padre = self._stn_carpeta_empresa(empresa)
        if not categoria:
            return padre
        nombre = '%02d %s' % (categoria.sequence or 0, categoria.name)
        return self._stn_carpeta(nombre, padre, stn_categoria_id=categoria.id, stn_empresa_id=empresa.id)

    @api.model
    def _stn_crear_estructura(self, empresas):
        categorias = self.env['stn.requisito.categoria'].search([])
        carpetas = self.browse()
        for empresa in empresas:
            carpetas |= self._stn_carpeta_empresa(empresa)
            for categoria in categorias:
                carpetas |= self._stn_carpeta_categoria(empresa, categoria)
        self._stn_compartir_con_equipo(carpetas | self._stn_raiz())
        return carpetas

    @api.model
    def _stn_compartir_con_equipo(self, carpetas):
        """Da acceso de editor a los usuarios del grupo Licitaciones (si esta versión de Documentos maneja
        accesos por persona). Los documentos legales no quedan abiertos a todos los empleados."""
        if 'documents.access' not in self.env or 'access_ids' not in self._fields:
            return
        Access = self.env['documents.access'].sudo()
        if not {'document_id', 'partner_id', 'role'} <= set(Access._fields):
            return
        grupo = self.env.ref('stn_perlop_licitaciones.group_licitaciones_user', raise_if_not_found=False)
        if not grupo:
            return
        grupo = grupo.sudo()
        usuarios = grupo.all_user_ids if 'all_user_ids' in grupo._fields else grupo.user_ids
        usuarios = usuarios.filtered(lambda u: not u.share)
        for carpeta in carpetas:
            ya = carpeta.sudo().access_ids.mapped('partner_id')
            for partner in usuarios.mapped('partner_id') - ya:
                try:
                    with self.env.cr.savepoint():
                        Access.create({'document_id': carpeta.id, 'partner_id': partner.id, 'role': 'edit'})
                except Exception as e:  # noqa: BLE001 - la API de accesos cambia entre versiones
                    _logger.warning('STN documentos: no se pudo compartir %s con %s: %s', carpeta.name, partner.name, e)
                    return

    def _stn_empresa_y_categoria(self):
        """Sube por las carpetas hasta encontrar la empresa; la primera categoría que aparezca es la del archivo."""
        self.ensure_one()
        empresa = categoria = False
        carpeta = self.folder_id
        vistas = 0
        while carpeta and vistas < 20:
            if not categoria and carpeta.stn_categoria_id:
                categoria = carpeta.stn_categoria_id
            if carpeta.stn_empresa_id:
                empresa = carpeta.stn_empresa_id
                break
            carpeta = carpeta.folder_id
            vistas += 1
        return empresa, categoria

    # ------------------------------------------------------------------
    # Al subir un archivo: alta en el catálogo de vigencias
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        if not self.env.context.get('stn_sin_catalogo'):
            docs.filtered(lambda d: d.type != 'folder')._stn_registrar_en_catalogo()
        return docs

    def write(self, vals):
        res = super().write(vals)
        if 'folder_id' in vals and not self.env.context.get('stn_sin_catalogo'):
            self.filtered(lambda d: d.type != 'folder' and not d.stn_requisito_ids)._stn_registrar_en_catalogo()
        return res

    def _stn_registrar_en_catalogo(self):
        Req = self.env['stn.requisito'].sudo()
        for doc in self:
            empresa, categoria = doc._stn_empresa_y_categoria()
            if not empresa:
                continue
            nombre = os.path.splitext(doc.name or '')[0].strip() or doc.name
            existente = Req.with_context(active_test=False).search(
                [('empresa_id', '=', empresa.id), ('documento_id', '=', False)]).filtered(
                lambda r: P.norm(r.name) == P.norm(nombre))[:1]
            if existente:
                existente.write({'documento_id': doc.id, 'categoria_id': existente.categoria_id.id or
                                 (categoria.id if categoria else False)})
                existente.message_post(body=_('Archivo ligado desde Documentos: %s', doc.name))
                continue
            req = Req.create({'name': nombre, 'empresa_id': empresa.id, 'documento_id': doc.id,
                              'categoria_id': categoria.id if categoria else False})
            req.message_post(body=_('Registrado al subir «%s» a Documentos. Captura la fecha de emisión y la '
                                    'vigencia para que corra el semáforo.', doc.name))
