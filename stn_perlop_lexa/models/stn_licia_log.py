from odoo import fields, models


class StnLiciaLog(models.Model):
    _inherit = 'stn.licia.log'

    origen = fields.Selection(selection_add=[('lexa', 'LEXA')], ondelete={'lexa': 'cascade'})
