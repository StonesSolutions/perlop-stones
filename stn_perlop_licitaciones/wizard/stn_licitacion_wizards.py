from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models import licia_parser as P

# Datos base que pasan de la IM / proyecto a la licitación nueva (sin ligarlas)
CAMPOS_BASE = [
    'partner_id', 'stn_dependencia_id', 'stn_convocante_id', 'stn_unidad_compradora_clave', 'state_id',
    'country_id', 'stn_plaza', 'stn_objeto', 'stn_tipo_servicio_id', 'stn_empresa_licitante_id', 'stn_area_requirente',
    'stn_cucop', 'stn_monto_minimo_estimado', 'stn_monto_maximo_estimado', 'expected_revenue', 'user_id', 'tag_ids',
    'stn_plataforma',
]


class StnLicitacionAprobarWizard(models.TransientModel):
    _name = 'stn.licitacion.aprobar.wizard'
    _description = 'Aprobar licitación y elegir líder de proyecto'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade')
    lider_id = fields.Many2one('res.users', 'Líder de proyecto', required=True, domain=[('share', '=', False)])
    nota = fields.Text('Nota para el equipo')

    def action_confirmar(self):
        self.ensure_one()
        lead = self.lead_id
        etapa = lead._stn_etapa('preparacion')
        if not etapa:
            raise UserError(_('No hay una etapa configurada con el código «preparacion».'))
        lead.with_context(stn_skip_stage_check=True).write({'stn_lider_id': self.lider_id.id, 'stage_id': etapa.id})
        cuerpo = _('Licitación aprobada. Líder de proyecto: %s.', self.lider_id.name)
        if self.nota:
            cuerpo += '\n' + self.nota
        lead.message_post(body=cuerpo, partner_ids=self.lider_id.partner_id.ids, message_type='comment',
                          subtype_xmlid='mail.mt_comment')
        lead._stn_notificar(self.lider_id, _('Líder de proyecto: preparar la propuesta'))
        return {'type': 'ir.actions.act_window_close'}


class StnLicitacionPublicadaWizard(models.TransientModel):
    """Salió la licitación real de una investigación de mercado o de un proyecto de convocatoria.

    Acuerdo con Perlop: la IM / el proyecto NO se ligan a la convocatoria. Se crea la licitación
    nueva directo en «Análisis de participación», con los datos base copiados.
    """
    _name = 'stn.licitacion.publicada.wizard'
    _description = 'Salió la licitación real'

    origen_id = fields.Many2one('crm.lead', 'Investigación / proyecto', required=True, ondelete='cascade')
    numero = fields.Char('No. de procedimiento', required=True)
    nombre = fields.Char('Nombre de la oportunidad')
    fecha_apertura = fields.Datetime('Presentación y apertura')
    url_ficha = fields.Char('URL de la ficha')

    @api.onchange('numero')
    def _onchange_numero(self):
        if self.numero and not self.nombre:
            objeto = self.origen_id.stn_objeto or self.origen_id.name or ''
            self.nombre = '%s · %s' % (self.numero.strip(), objeto[:80])

    def action_confirmar(self):
        self.ensure_one()
        origen = self.origen_id
        if origen.stn_tipo_registro == 'licitacion':
            raise UserError(_('Este registro ya es una licitación.'))
        numero = P.texto(self.numero)
        Lead = self.env['crm.lead'].with_context(active_test=False)
        lead = Lead.search([('stn_no_procedimiento', '=', numero), ('stn_tipo_registro', '=', 'licitacion')], limit=1)
        if lead:
            # LICIA ya la había traído: solo se pasa a análisis si seguía en Nuevas
            if lead.stage_id.stn_codigo in ('nueva', False):
                lead._stn_mover('analisis')
            accion = _('ya existía; se pasó a «Análisis de participación»')
        else:
            vals = {}
            for campo in CAMPOS_BASE:
                valor = origen[campo]
                if origen._fields[campo].type == 'many2many':
                    vals[campo] = [(6, 0, valor.ids)]
                elif origen._fields[campo].type == 'many2one':
                    vals[campo] = valor.id
                else:
                    vals[campo] = valor
            vals.update({
                'type': 'opportunity',
                'team_id': origen.team_id.id,
                'stn_tipo_registro': 'licitacion',
                'stn_no_procedimiento': numero,
                'name': self.nombre or numero,
                'stn_fecha_deteccion': fields.Datetime.now(),
            })
            if self.fecha_apertura:
                vals['stn_fecha_apertura'] = self.fecha_apertura
            if self.url_ficha:
                vals['stn_url_ficha'] = self.url_ficha
            lead = Lead.create(vals)
            lead._stn_mover('analisis')
            accion = _('se creó en «Análisis de participación»')
        tipo = dict(origen._fields['stn_tipo_registro'].selection)[origen.stn_tipo_registro].lower()
        origen.write({'stn_im_estado': 'publicada'})
        origen.message_post(body=_('Salió la licitación %(num)s: %(accion)s.', num=numero, accion=accion),
                            message_type='comment', subtype_xmlid='mail.mt_note')
        lead.message_post(body=_('Datos base tomados de la %(tipo)s «%(nombre)s».', tipo=tipo, nombre=origen.name),
                          message_type='comment', subtype_xmlid='mail.mt_note')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }
