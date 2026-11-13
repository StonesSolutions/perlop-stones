{
    'name': 'PERLOP · LEXA (proposición legal y técnica)',
    'version': '19.0.1.1.1',
    'summary': 'Integra a LEXA con el CRM de Licitaciones: matriz de cotejo por casilla de ComprasMX, '
               'aprobación humana, faltantes y revisión «cumple / no cumple» de nuestros archivos.',
    'description': """
LEXA es el agente de PERLOP que arma la proposición legal y técnica. Este módulo:

* recibe la matriz de cotejo de LEXA (casillas de «Mi proposición», requisitos con texto íntegro,
  causal literal, huella, soportes…) y la deja lista para que una persona la apruebe;
* pide a LEXA, con un botón en «Revisión IA», que revise los archivos que preparó el equipo
  y diga, requisito por requisito, si cumplen o no;
* registra los faltantes con dónde se buscaron y a quién se pidieron;
* marca los encargos como «requiere regenerar» cuando cambia la fecha de apertura.

LEXA nunca escribe aprobaciones: la aprobación de la matriz y «subido a ComprasMX» los marca una persona.
    """,
    'author': 'STONES Business Group',
    'website': 'https://www.stones.mx',
    'category': 'Sales/CRM',
    'license': 'LGPL-3',
    'depends': ['stn_perlop_licitaciones'],
    'data': [
        'security/ir.model.access.csv',
        'data/stn_lexa_data.xml',
        'views/stn_lexa_views.xml',
        'views/crm_lead_views.xml',
        'views/stn_requisito_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/stn_lexa_solicitud_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
