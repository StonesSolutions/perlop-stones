# stn_perlop_licitaciones · CRM Licitaciones + LICIA (Odoo 19)

Este módulo concentra en código toda la configuración del CRM "Licitaciones" de PERLOP, que antes estaba en Studio, y le agrega la estructura completa de la ficha que genera el agente LICIA (Claude).

**Reemplaza a:**
- Las personalizaciones de Studio de la base de pruebas.
- El módulo `stn_crm_stage_directores`. No hay que instalarlo junto con este: su regla ya viene aquí y aplica solo a los equipos de licitación.

## Instalación (base nueva)

1. Sube la carpeta a la rama de Odoo.sh e instala **PERLOP · CRM Licitaciones + LICIA**.
2. Ve a *CRM › Configuración › Ajustes › Licitaciones*:
   - Elige el equipo y el responsable por defecto.
   - Activa la **Integración LICIA**.
   - Pulsa **Generar nuevo token**.
   - Captura los estados donde operan y los segmentos de interés.
3. Asigna los grupos a los usuarios:
   - *Licitaciones / Usuario*: auxiliares jurídicos.
   - *Licitaciones / Directores*: Abelardo y gerencia.
4. Si se usará correo, configura el dominio de alias. El equipo trae el alias `licitaciones@…`.

## Mapeo Studio → módulo

| Studio | Módulo | Nota |
|---|---|---|
| `x_studio_no_de_procedimiento` | `stn_no_procedimiento` | Llave de alta o actualización; es único |
| `x_studio_objeto`, `x_studio_objeto_2` | `stn_objeto` | Se quitó el duplicado |
| `x_studio_criterio`, `_2`, `_3` | `stn_criterio_id` (catálogo `stn.licitacion.criterio`) | Tres campos → uno |
| `x_studio_estatus_del_procedimiento` | `stn_estatus_id` + `stn_resultado` | Se separan el estatus en la plataforma y el resultado. Se agrega *Suspendido* |
| `x_studio_viabilidad_de_la_licitacion` | `stn_viabilidad` (0–5) | Es el nivel LICIA |
| `x_studio_fecha_de_publicacion` | `stn_fecha_publicacion` | |
| `x_studio_fecha_junta_de_aclaraciones` (float) y `_1` (datetime) | `stn_fecha_junta` | Se quitó el `float` |
| `x_studio_fecha_limite_de_aclaraciones` | `stn_fecha_limite_preguntas` | |
| `x_studio_fecha_de_apertura_de_proposiciones` | `stn_fecha_apertura` | |
| `x_studio_fecha_de_fallo` | `stn_fecha_fallo` | |
| `x_studio_vigencia_del_contrato` | `stn_vigencia_inicio` / `stn_vigencia_fin` | Rango completo |
| `x_studio_cliente_nuevo` | `stn_cliente_nuevo` | |
| `x_studio_requisitos` (archivo) | `stn_requisitos_file` | |
| `x_studio_requerimientos_de_la_licitacion` (`x_crm_lead_line_265ca`) | `stn_requisito_ids` (`stn.licitacion.requisito`) | Se agregan referencia, tipo, situación, efecto y vigencia máxima |
| `x_requisitos` | `stn.requisito` | Semáforo con cron diario y tiempo de trámite |
| `x_requisitos_stage` | `stn.requisito.etapa` | Con código fijo |
| `x_categorias_de_requis`, `x_tipos_de_servicio`, `x_tipos_de_criterio` | `stn.requisito.categoria`, `stn.tipo.servicio`, `stn.licitacion.criterio` | Con sinónimos, para que LICIA las encuentre |
| `sale.order.line.x_studio_grupo` | — | Se deja para el módulo de Órdenes de suministro |
| Botón «Pasar a análisis» | `action_stn_pasar_analisis` | Más botones por etapa: preparar, revisión IA, revisión, alta |
| Botón «Pasar a revisión IA» | `action_stn_pasar_revision_ia` | |
| Automatización «Viabilidad ≥4 → Análisis» | `_stn_aplicar_viabilidad` | El nivel se configura en Ajustes |
| Automatización «Notificación nueva licitación» | Ajustes › *Notificar nueva licitación* | Los usuarios se eligen en Ajustes |
| Automatización «Notificación revisión y análisis» | Ajustes › *Notificar paso a análisis* | |
| 8 etapas de Studio | 8 etapas acordadas en el glosario v2 (`stn_codigo`) | Nuevas → Análisis y decisión → Preparación → Revisión IA → Revisión → Presentada en ComprasMX → En evaluación → **Ganado**. *Perdido* es el botón de cierre. Firma, fianza y RC salen del tablero y se llevan como pendientes |
| Motivos de pérdida | `crm.lost.reason` | No participamos, Desechada legal, Desechada técnica, Precio, Desierta, Cancelada, Fuera de plazo |

## Lo nuevo que pide la ficha LICIA

- **Encabezado:**
  - Plataforma, URL de la ficha, tipo de procedimiento y fundamento, carácter, mínimo técnico, CUCoP.
  - Convocante, unidad compradora (con su clave) y área requirente; estado y si operamos en él.
  - Montos mínimo y máximo con nota, garantía, si admite propuesta conjunta.
  - Nivel, acción y lectura de LICIA, y por qué ese nivel.
- **Fechas y seguimiento:**
  - Fechas de detección, límite interno e inicio del contrato.
  - Sellos automáticos de la preparación interna y tiempos en días.
- **Tablas:**
  - Eventos con su límite interno. Generan el evento de calendario y el recordatorio.
  - Historial de cambios.
  - Preguntas de aclaración.
  - **Partidas** por unidad, con sus renglones de producto, nombre contractual y precio (base para las fases siguientes).
  - Puntos.
  - Antecedentes y competidores. Los competidores se crean como contactos.
  - Resultado del acta.
  - Pendientes después del fallo. Se vuelven actividades al marcar la licitación como ganada.
  - Seguimiento diario. Se publica en el chatter sin duplicar.
- **Análisis:** pivot y gráfica por nivel, resultado, convocante, estado, segmento y tipo de procedimiento.

## Cambios v1.1 (glosario de Perlop v2)

- **Etapas:**
  - Se agrega *En evaluación*: la licitación entra sola cuando pasa la apertura.
  - *Ganado* ya es la etapa ganada y exige haber subido el acta de fallo y tener al menos una partida ganada.
  - El resultado (ganada o parcial) se calcula a partir de las partidas.
  - Al ganar se crean los pendientes: firma, fianza de cumplimiento y, si aplica, póliza de RC.
- **Avisos:**
  - Cada evento crea una actividad con responsable para su límite interno.
  - Se manda un aviso previo (los días se configuran en Ajustes).
  - Si el límite vence sin atenderse, se escala a Gerencia.
  - Los cambios de fecha quedan en el historial con la fecha anterior y su origen.
- **Semáforo por licitación:** cada requisito toma su antigüedad máxima y la mide contra la apertura. Se recalcula si la apertura cambia.
- **Más datos de la licitación:**
  - Extracto literal y captura en cada requisito.
  - Dependencia > convocante (OOAD) > unidad compradora; plaza.
  - Folio de la plataforma; ComprasMX o CFE.
  - Tipo, carácter y clave de la UC se leen del número de procedimiento.
- **LICIA:**
  - Reporte diario: se guarda en Odoo y se publica en el canal *Licitaciones · LICIA*.
  - Cuenta regresiva con la fecha en que se verificaron las fechas.

## Cambios v1.2 (propuesta de campos de la IA del cliente, ficha N-134)

- Datos nuevos de la licitación:
  - empresa del grupo que licita (PERLOP, JADE o JD);
  - modalidad: electrónica, presencial o mixta;
  - modo de participación: individual, conjunta o consorcio;
  - montos mínimo y máximo estimados (el ingreso esperado toma el estimado si no hay monto oficial);
  - condiciones de entrega.
- **Partidas por clave alfanumérica** (G3, G7A…), con ganador anterior, suma de precios del ganador, nuestra suma de precios, «nosotros contra el ganador» en % y lugar en precios.
- Tabla nueva de **Sedes y logística**: una línea por unidad, con las partidas que atiende, domicilios, corredor, vehículos, CEDIS y horario.
- En requisitos, nota de LICIA; en eventos, aviso cuando el límite interno cae en fin de semana.
- Nivel LICIA con etiquetas de «Nivel 0» a «Nivel 5»; la acción admite «Analizar» y «No participar por ahora».
- El cierre esperado toma la fecha de fallo.

## Cambios v1.6 (documentos legales en Odoo, 11-nov)

- **Empresas del grupo que licitan** (Ajustes › CRM › Documentos de la empresa).
- **Documento maestro con empresa** (`stn.requisito.empresa_id`). En la licitación, el documento maestro de cada requisito solo se puede elegir entre los de la empresa licitante.
- **Categorías nuevas**, que también son las subcarpetas de Documentos: Constitución y personalidad, Certificaciones, Seguros y fianzas y Personal.
- **Documentos de prueba**: 22 PDF marcados «SIN VALIDEZ», con fechas para todos los colores del semáforo. Se cargan y se quitan desde Ajustes.
- **Puntos de extensión** para el módulo de Documentos (`stn_perlop_documentos`): `_stn_archivos`, `_stn_guardar_archivo` y `_stn_buscar_por_archivo`.

## Cambios v1.5 (comentarios de Perlop, 11-nov)

- **Etapas renombradas** (con migración):
  - Análisis y decisión → **Análisis de participación**;
  - Preparación técnica, legal y económica → **Preparación de propuesta**;
  - Revisión → **Integración final**.
- **Líder de proyecto** (`stn_lider_id`): «Aprobar y preparar» abre un asistente para elegirlo. Sin líder no se pasa a Preparación de propuesta. El líder aparece en la ficha y en la tarjeta del kanban, y recibe la actividad «Líder de proyecto: preparar la propuesta». También hay un filtro «Las que lidero».
- **Investigaciones de mercado y proyectos de convocatoria** (`stn_tipo_registro`):
  - se llevan en su propio tablero (Licitaciones › Investigaciones de mercado y proyectos), con estados Nueva / En seguimiento / Respondida / Salió la licitación / Descartada;
  - **no se ligan a la convocatoria**;
  - el botón «Salió la licitación» pide el número y crea la licitación **directo en Análisis de participación**, con los datos base copiados. Si LICIA ya la había traído, la pasa a análisis;
  - LICIA puede mandarlas con `tipo_registro`.
- **Avance de la propuesta por pestaña de ComprasMX**:
  - cada requisito tiene pestaña (legal, técnica o económica), casilla (1, 2, 1.1…), avance (Falta / Incompleto / Completo / No aplica) y «Nuestros archivos»;
  - la licitación muestra el % legal, técnico y económico en los datos principales y en el kanban;
  - además muestra los chips requisito por requisito en el orden de las casillas (verde, amarillo o rojo).
- Requerimientos se ordena por pestaña y casilla.

## Cambios v1.4 (revisión del cliente, 30-oct)

- **Avisos sin ruido**: el escalamiento «VENCIDO» se reiniciaba cada vez que LICIA reenviaba la misma fecha (bug); ahora solo se reinicia si la fecha cambia. Publicación, cierre de junta, fallo e inicio de contrato no generan límite interno. Apertura y muestras se activan al aprobar. No se escala un evento cuya fecha oficial ya pasó. Marcar hecha la actividad del límite deja el evento atendido y ya no se recrea.
- **Anticipación** calculada cuando LICIA manda el límite interno.
- **Detectada** guarda la primera detección.
- **Partidas y sedes** se reemplazan con la lista que trae la ficha (se respetan las que tienen resultados del equipo y las sedes manuales); claves normalizadas («Partida 01» = «1»).
- **Logística solo en Sedes**; la partida muestra sus sedes.
- **Área requirente** se ignora si repite la unidad compradora.
- Catálogo de estatus: *En aclaraciones*, *En repreguntas*.
- **Cierre fuera de plazo**: al pasar la apertura, las que siguen en Nuevas/Análisis se cierran perdidas «Fuera de plazo»; las de Preparación/Revisión piden al responsable marcarlas presentadas o cerrarlas (Ajustes › Avisos automáticos).
- Actividades de aviso por etapa sin duplicar.
- **Alias de correo** limitado a seguidores del equipo Licitaciones (antes aceptaba a cualquiera).
- Etiqueta «Preliminar · sin nivel» en kanban y formulario.
- Migración `19.0.1.4.0/post-migrate.py`: borra los avisos VENCIDO repetidos y las actividades duplicadas, limpia límites de eventos informativos, corrige «Detectada» y área requirente, marca las sedes existentes como de LICIA y cierra el alias.

## Integración

Los detalles están en `doc/CONTRATO_LICIA_v1.md`.

- `POST /stn/licitaciones/ficha` con el encabezado `Authorization: Bearer <token>`.
  - Recibe una ficha o una lista de fichas.
  - Si el número de procedimiento ya existe, actualiza esa licitación; si no, la crea.
  - Responde `{ok, accion, lead_id, url, advertencias}`.
- `GET /stn/licitaciones/parametros`: devuelve lo que LICIA debe leer antes de buscar (palabras clave, estados, segmentos, nivel mínimo y procedimientos en seguimiento).
- `POST /stn/licitaciones/reporte`: recibe el reporte diario de LICIA.
- `GET /stn/licitaciones/ping`: prueba de conexión.
- **Correo:** se manda al alias del equipo con el JSON adjunto. Si no viene adjunto, se lee el bloque `clave: valor` del cuerpo.
- **Claude:** en *Ajustes › Cuenta de Claude* se captura la URL y el token del disparador API de la rutina.
  - Con **Ejecutar LICIA ahora** Odoo lanza la rutina y le manda los parámetros de búsqueda.
  - Para programarla desde Odoo, activa la acción planificada *Licitaciones: disparar rutina LICIA en Claude*.
- **Bitácora:** cada entrada o disparo queda registrado en *Configuración › Licitaciones › Bitácora LICIA*.

## Pruebas

```
odoo-bin -d <db> -i stn_perlop_licitaciones --test-tags=/stn_perlop_licitaciones --stop-after-init
```

Hay 12 pruebas. Cubren:
- Alta con la ficha real de Tamaulipas.
- Actualización sin duplicar y sin pisar decisiones del equipo.
- Regla de Directores.
- Paso a Ganado: exige el acta de fallo y crea los pendientes.
- Lectura del número de procedimiento y semáforo por licitación.
- Avisos previos y escalamiento a Gerencia.
- Reporte diario.
- Ficha binaria con partidas por grupo y sedes.
- Activación de pendientes al ganar.
- Respaldo por correo.
- Semáforo de requisitos.
- Endpoint HTTP.
