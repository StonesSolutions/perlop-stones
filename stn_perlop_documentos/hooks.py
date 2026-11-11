def post_init_hook(env):
    """Crea las carpetas de las empresas del grupo que ya estén configuradas en Ajustes."""
    empresas = env['res.company'].search([]).mapped('stn_empresa_grupo_ids')
    if empresas:
        env['documents.document']._stn_crear_estructura(empresas)
