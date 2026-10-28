{
    'name': 'PERLOP · CRM Licitaciones + LICIA',
    'version': '19.0.1.3.1',
    'summary': 'CRM de licitaciones públicas para PERLOP con ingesta automática de fichas del agente LICIA (Claude).',
    'description': """
Módulo que concentra toda la configuración del CRM "Licitaciones" de PERLOP
(antes hecha en Studio) y la amplía con la estructura completa de la ficha
de licitación que genera el agente LICIA.

- Campos de la licitación (sin duplicados de Studio) y catálogos.
- Requisitos maestros con semáforo de vigencias y requisitos por licitación.
- Eventos con fecha límite interna, partidas por unidad con renglones,
  puntos, preguntas de aclaración, antecedentes, competidores, resultado,
  pendientes post-fallo, historial de cambios y seguimiento diario.
- Etapas, botones de flujo, actividades automáticas y regla de Directores.
- Ingesta de la ficha por HTTP (token) y por correo (alias del equipo),
  con alta o actualización por número de procedimiento.
- Ajustes: parámetros de búsqueda para LICIA y conexión con la rutina
  de Claude (disparo por API).
    """,
    'author': 'STONES Business Group',
    'website': 'https://www.stones.mx',
    'category': 'Sales/CRM',
    'license': 'LGPL-3',
    'depends': ['crm', 'mail', 'calendar', 'product'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/stn_security.xml',
        'security/ir.model.access.csv',
        'data/stn_catalogos_data.xml',
        'data/crm_data.xml',
        'data/ir_cron_data.xml',
        'views/catalogos_views.xml',
        'views/stn_requisito_views.xml',
        'views/crm_lead_views.xml',
        'views/crm_stage_team_views.xml',
        'views/stn_licia_log_views.xml',
        'views/stn_licia_reporte_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
