def post_init_hook(env):
    """Las etapas estándar sin equipo se asignan a los equipos que NO son de licitación,
    para que el embudo de Licitaciones solo muestre sus 8 etapas."""
    otros = env['crm.team'].search([('stn_es_licitacion', '=', False)])
    etapas = env['crm.stage'].search([('team_ids', '=', False), ('stn_codigo', '=', False)])
    if otros and etapas:
        etapas.write({'team_ids': [(6, 0, otros.ids)]})
