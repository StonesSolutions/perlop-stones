import json

from odoo import api, fields, models


class StnLiciaLog(models.Model):
    _name = 'stn.licia.log'
    _description = 'Bitácora de integración LICIA'
    _order = 'id desc'
    _rec_name = 'procedimiento'

    fecha = fields.Datetime('Fecha', default=fields.Datetime.now, readonly=True)
    origen = fields.Selection([('http', 'HTTP'), ('email', 'Correo'), ('manual', 'Manual'),
                               ('claude', 'Disparo a Claude')], 'Origen', readonly=True)
    estado = fields.Selection([('ok', 'Correcto'), ('error', 'Error')], 'Estado', readonly=True)
    accion = fields.Char('Acción', readonly=True)
    procedimiento = fields.Char('Procedimiento', readonly=True)
    lead_id = fields.Many2one('crm.lead', 'Licitación', readonly=True, ondelete='set null')
    mensaje = fields.Text('Mensaje', readonly=True)
    payload = fields.Text('Contenido', readonly=True)

    @api.model
    def _stn_registrar(self, origen, payload=None, resultado=None, error=None):
        resultado = resultado or {}
        numero = payload.get('numero_procedimiento') if isinstance(payload, dict) else False
        return self.sudo().create({
            'origen': origen,
            'estado': 'error' if error else 'ok',
            'accion': resultado.get('accion'),
            'procedimiento': numero or False,
            'lead_id': resultado.get('lead_id') or False,
            'mensaje': error or '\n'.join(resultado.get('advertencias') or []) or False,
            'payload': (json.dumps(payload, ensure_ascii=False, indent=1, default=str)
                        if isinstance(payload, (dict, list)) else (payload or ''))[:100000],
        })

    @api.model
    def _cron_limpiar(self, dias=90):
        limite = fields.Datetime.subtract(fields.Datetime.now(), days=dias)
        self.search([('fecha', '<', limite)]).unlink()
