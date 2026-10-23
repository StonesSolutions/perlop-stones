from markupsafe import Markup, escape

from odoo import _, api, fields, models

from . import licia_parser as P


class StnLiciaReporte(models.Model):
    """Reporte diario de LICIA (glosario §3): cuántos procedimientos revisó, cuáles son
    nuevos y del giro, su nivel y la recomendación. Se publica en el canal de Discuss."""
    _name = 'stn.licia.reporte'
    _description = 'Reporte diario de LICIA'
    _order = 'fecha desc, id desc'
    _rec_name = 'fecha'

    fecha = fields.Date('Fecha', required=True, default=fields.Date.context_today)
    revisados = fields.Integer('Procedimientos revisados')
    nuevos = fields.Integer('Nuevos del giro')
    enviados = fields.Integer('Enviados a Odoo')
    plataformas = fields.Char('Plataformas revisadas')
    resumen = fields.Text('Resumen')
    linea_ids = fields.One2many('stn.licia.reporte.linea', 'reporte_id', 'Procedimientos')
    message_id = fields.Many2one('mail.message', readonly=True)

    @api.model
    def stn_registrar(self, payload):
        fecha = P.fecha(payload.get('fecha')) or fields.Date.context_today(self)
        reporte = self.search([('fecha', '=', fecha)], limit=1)
        vals = {
            'fecha': fecha,
            'revisados': P.entero(payload.get('revisados')) or 0,
            'nuevos': P.entero(payload.get('nuevos')) or 0,
            'enviados': P.entero(payload.get('enviados')) or 0,
            'plataformas': P.texto(payload.get('plataformas')) if not isinstance(payload.get('plataformas'), list)
            else ', '.join(payload['plataformas']),
            'resumen': P.texto(payload.get('resumen')),
        }
        if reporte:
            reporte.linea_ids.unlink()
            reporte.write(vals)
        else:
            reporte = self.create(vals)
        Lead = self.env['crm.lead'].with_context(active_test=False)
        for f in payload.get('procedimientos') or []:
            numero = P.texto(f.get('numero_procedimiento'))
            if not numero:
                continue
            lead = Lead.search([('stn_no_procedimiento', '=', numero)], limit=1)
            self.env['stn.licia.reporte.linea'].create({
                'reporte_id': reporte.id, 'numero_procedimiento': numero,
                'descripcion': P.texto(f.get('descripcion')),
                'nivel': P.entero(f.get('nivel')) or 0,
                'recomendacion': P.texto(f.get('recomendacion')),
                'es_nuevo': bool(P.booleano(f.get('es_nuevo'))),
                'lead_id': lead.id or False,
            })
        reporte._stn_publicar()
        return reporte

    def _stn_publicar(self):
        canal = self.env.ref('stn_perlop_licitaciones.channel_licia', raise_if_not_found=False)
        if not canal:
            return
        for r in self:
            filas = Markup('').join(
                Markup('<li><b>%s</b> · nivel %s · %s%s</li>') % (
                    l.numero_procedimiento, l.nivel, l.recomendacion or '',
                    Markup(' · <i>nuevo</i>') if l.es_nuevo else '')
                for l in r.linea_ids)
            body = Markup('<p><b>%s</b></p><p>%s</p><ul>%s</ul>%s') % (
                _('Reporte LICIA %(f)s · revisados %(r)s · nuevos %(n)s · enviados %(e)s',
                  f=r.fecha, r=r.revisados, n=r.nuevos, e=r.enviados),
                escape(r.resumen or ''), filas, '')
            r.message_id = canal.sudo().message_post(body=body, message_type='comment',
                                                     subtype_xmlid='mail.mt_comment')


class StnLiciaReporteLinea(models.Model):
    _name = 'stn.licia.reporte.linea'
    _description = 'Procedimiento del reporte diario'
    _order = 'nivel desc, id'

    reporte_id = fields.Many2one('stn.licia.reporte', required=True, ondelete='cascade')
    numero_procedimiento = fields.Char('Procedimiento')
    descripcion = fields.Char('Descripción')
    nivel = fields.Integer('Nivel')
    recomendacion = fields.Char('Recomendación')
    es_nuevo = fields.Boolean('Nuevo')
    lead_id = fields.Many2one('crm.lead', 'Licitación')
