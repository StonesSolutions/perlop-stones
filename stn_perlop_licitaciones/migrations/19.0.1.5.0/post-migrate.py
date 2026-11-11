"""v1.5.0 · etapas renombradas (acuerdo con Perlop) y avance de requisitos por pestaña."""
from odoo import SUPERUSER_ID, api

from odoo.addons.stn_perlop_licitaciones.models.crm_lead_lines import PESTANA_POR_TIPO

NOMBRES = {
    'stage_analisis': 'Análisis de participación',
    'stage_preparacion': 'Preparación de propuesta',
    'stage_revision': 'Integración final',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, nombre in NOMBRES.items():
        etapa = env.ref('stn_perlop_licitaciones.%s' % xmlid, raise_if_not_found=False)
        if etapa:
            for code, _name in env['res.lang'].get_installed():
                etapa.with_context(lang=code).name = nombre
    Req = env['stn.licitacion.requisito']
    for tipo, pestana in PESTANA_POR_TIPO.items():
        Req.search([('tipo', '=', tipo), ('pestana', '=', False)]).write({'pestana': pestana})
    Req.search([('situacion', '=', 'no_aplica'), ('avance', '=', 'falta')]).write({'avance': 'no_aplica'})
    cr.execute("UPDATE crm_lead SET stn_tipo_registro = 'licitacion' WHERE stn_tipo_registro IS NULL")
