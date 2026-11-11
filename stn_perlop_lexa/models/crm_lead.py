from odoo import _, fields, models
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    stn_lexa_encargo_ids = fields.One2many('stn.lexa.encargo', 'lead_id', 'Encargos de LEXA')
    stn_lexa_casilla_ids = fields.One2many('stn.lexa.casilla', 'lead_id', 'Casillas de ComprasMX')
    stn_lexa_faltante_ids = fields.One2many('stn.lexa.faltante', 'lead_id', 'Faltantes')
    stn_lexa_faltantes_abiertos = fields.Integer('Faltantes abiertos', compute='_compute_stn_lexa_resumen')
    stn_lexa_no_cumplen = fields.Integer('Requisitos que no cumplen (LEXA)', compute='_compute_stn_lexa_resumen')
    stn_lexa_estado = fields.Char('LEXA', compute='_compute_stn_lexa_resumen')

    def _compute_stn_lexa_resumen(self):
        estados = dict(self.env['stn.lexa.encargo']._fields['estado'].selection)
        for lead in self:
            lead.stn_lexa_faltantes_abiertos = len(lead.stn_lexa_faltante_ids.filtered(
                lambda f: f.estado in ('abierto', 'en_tramite')))
            lead.stn_lexa_no_cumplen = len(lead.stn_requisito_ids.filtered(
                lambda r: r.lexa_dictamen in ('no_cumple', 'parcial')))
            ultimo = lead.stn_lexa_encargo_ids.filtered(lambda e: e.estado != 'cancelado')[:1]
            lead.stn_lexa_estado = ('%s · %s' % (ultimo.name.split(' · ', 1)[-1], estados.get(ultimo.estado))) \
                if ultimo else False

    def _stn_lexa_wizard(self, tipo):
        self.ensure_one()
        if self.stn_tipo_registro != 'licitacion':
            raise UserError(_('LEXA trabaja licitaciones, no investigaciones de mercado ni proyectos.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revisar con LEXA') if tipo == 'revision' else _('Armar matriz con LEXA'),
            'res_model': 'stn.lexa.solicitud.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_id': self.id, 'default_tipo': tipo,
                        'default_parte': 'ambas' if tipo == 'revision' else 'legal'},
        }

    def action_stn_lexa_matriz(self):
        return self._stn_lexa_wizard('matriz')

    def action_stn_lexa_revisar(self):
        return self._stn_lexa_wizard('revision')

    def write(self, vals):
        aperturas = {l.id: l.stn_fecha_apertura for l in self} if 'stn_fecha_apertura' in vals else {}
        res = super().write(vals)
        if aperturas:
            for lead in self.filtered(lambda l: aperturas.get(l.id) and l.stn_fecha_apertura != aperturas[l.id]):
                lead._stn_lexa_requiere_regenerar(aperturas[lead.id])
        return res

    def _stn_lexa_requiere_regenerar(self, apertura_anterior):
        """La fecha de apertura es la fecha de todos los escritos y la referencia de vigencias:
        si cambia, lo que LEXA ya entregó se tiene que regenerar."""
        self.ensure_one()
        encargos = self.stn_lexa_encargo_ids.filtered(
            lambda e: e.estado in ('matriz_lista', 'aprobada', 'revisado'))
        if not encargos:
            return
        encargos.write({'estado': 'requiere_regenerar'})
        tz = self._stn_tz()
        fmt = lambda dt: fields.Datetime.context_timestamp(self.with_context(tz=tz), dt).strftime('%Y-%m-%d %H:%M') \
            if dt else '-'
        self.message_post(
            body=_('La apertura cambió de %(antes)s a %(despues)s: LEXA debe regenerar fechas de los escritos y '
                   'volver a medir vigencias (%(n)s encargo(s) marcados «Requiere regenerar»).',
                   antes=fmt(apertura_anterior), despues=fmt(self.stn_fecha_apertura), n=len(encargos)),
            partner_ids=self.stn_lider_id.partner_id.ids, message_type='comment', subtype_xmlid='mail.mt_comment')
