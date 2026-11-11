{
    'name': 'PERLOP · Documentos legales en Documentos de Odoo',
    'version': '19.0.1.0.0',
    'summary': 'Odoo como fuente única de los documentos legales de cada empresa del grupo: carpetas por empresa '
               'y categoría en Documentos, catálogo de vigencias ligado y lectura para LEXA.',
    'description': """
* Crea «Licitaciones · Documentos de la empresa / <Empresa> / <Categoría>» en Documentos.
* Lo que se sube a esas carpetas se registra solo en el catálogo «Requisitos (vigencias)» con su empresa y
  categoría; ahí se capturan emisión y vigencia y corre el semáforo.
* El documento maestro apunta al archivo de Documentos: LEXA lo descarga de ahí (solo lectura).
    """,
    'author': 'STONES Business Group',
    'website': 'https://www.stones.mx',
    'category': 'Productivity/Documents',
    'license': 'LGPL-3',
    'depends': ['documents', 'stn_perlop_licitaciones'],
    'data': [
        'views/stn_requisito_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
