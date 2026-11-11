"""v1.4.0 · limpieza tras la revisión del 30-oct (ruido de avisos, detección, área requirente, sedes, alias)."""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.stn_perlop_licitaciones.models.crm_lead_lines import EVENTOS_ACCION

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'stn_sin_historial': True})
    Lead = env['crm.lead'].with_context(active_test=False)
    leads = Lead.search([('team_id.stn_es_licitacion', '=', True)])
    Activity = env['mail.activity'].with_context(stn_sin_hecho=True)

    # 1) Avisos «VENCIDO» repetidos: se borran y el cron (corregido) vuelve a escalar solo lo que sigue vigente
    vencidos = Activity.search([('res_model', '=', 'crm.lead'), ('res_id', 'in', leads.ids),
                                ('summary', '=like', 'VENCIDO sin atender:%')])
    _logger.info('STN v1.4.0: %s avisos VENCIDO eliminados', len(vencidos))
    vencidos.unlink()

    # 2) «Revisar y analizar licitación» duplicadas: una por usuario y licitación
    revisar = Activity.search([('res_model', '=', 'crm.lead'), ('res_id', 'in', leads.ids),
                               ('summary', '=', 'Revisar y analizar licitación')], order='id')
    vistos, dup = set(), Activity.browse()
    for act in revisar:
        llave = (act.res_id, act.user_id.id)
        if llave in vistos:
            dup |= act
        vistos.add(llave)
    dup.unlink()

    # 3) Eventos: informativos sin límite; anticipación calculada; escalamiento reiniciado
    Evento = env['stn.licitacion.evento'].with_context(stn_sin_historial=True)
    eventos = Evento.search([('lead_id', 'in', leads.ids)])
    for ev in eventos:
        vals = {'escalado': False}
        if ev.tipo not in EVENTOS_ACCION:
            vals['fecha_limite_interna'] = False
            vals['anticipacion_horas'] = 0.0
        elif ev.fecha_oficial and ev.fecha_limite_interna and not ev.anticipacion_horas:
            vals['anticipacion_horas'] = round((ev.fecha_oficial - ev.fecha_limite_interna).total_seconds() / 3600.0, 2)
        ev.write(vals)
    # actividades de límite que ya no corresponden (informativos / preparación sin aprobar)
    eventos.filtered(lambda e: e.lead_id.active)._stn_sincronizar_agenda()

    # 4) «Detectada»: la primera detección no puede ser posterior a la creación
    for lead in leads.filtered(lambda l: l.stn_fecha_deteccion and l.stn_fecha_deteccion > l.create_date):
        lead.with_context(tracking_disable=True, stn_skip_stage_check=True).write(
            {'stn_fecha_deteccion': lead.create_date})

    # 5) Área requirente que solo repetía la unidad compradora / convocante
    from odoo.addons.stn_perlop_licitaciones.models import licia_parser as P
    for lead in leads.filtered('stn_area_requirente'):
        if P.norm(lead.stn_area_requirente) in {P.norm(lead.partner_id.name), P.norm(lead.stn_convocante_id.name)}:
            lead.with_context(tracking_disable=True, stn_skip_stage_check=True).write({'stn_area_requirente': False})

    # 6) Sedes cargadas hasta hoy vinieron de LICIA (permite reemplazarlas con la siguiente ficha)
    env['stn.licitacion.sede'].search([]).write({'origen': 'licia'})

    # 7) El alias de correo deja de aceptar a cualquiera: solo seguidores del equipo Licitaciones
    team = env.ref('stn_perlop_licitaciones.team_licitaciones', raise_if_not_found=False)
    if team and team.alias_id:
        team.alias_id.alias_contact = 'followers'

    # 8) Parámetro nuevo: cierre automático de las no aprobadas al pasar la apertura
    ICP = env['ir.config_parameter']
    if ICP.get_param('stn_licitaciones.cerrar_no_presentadas') is False:
        ICP.set_param('stn_licitaciones.cerrar_no_presentadas', 'True')
