# Contrato de integración LICIA → Odoo · v1.4

Este contrato define cómo LICIA manda cada ficha de licitación a Odoo para que quede **capturada en sus campos**, no solo adjunta. Hay un ejemplo completo, tomado de la ficha real IA-50-GYR-050GYR018-N-210-2026, en `ficha_ejemplo_v1.json`.

## 1. Flujo diario

1. **Leer parámetros.** LICIA consulta `GET {ODOO}/stn/licitaciones/parametros`, que devuelve:
   - palabras clave, estados donde operamos, segmentos y nivel mínimo para enviar;
   - horas de anticipación para el límite interno;
   - la lista `procedimientos_en_seguimiento`, que son los que debe volver a revisar aunque ya no aparezcan en los anuncios.
2. **Buscar y analizar.** Busca en ComprasMX con y sin acento, y analiza los documentos como lo hace hoy.
3. **Enviar.** Por cada procedimiento con nivel mayor o igual al mínimo, o que esté en seguimiento, hace `POST {ODOO}/stn/licitaciones/ficha` con la ficha en JSON.
4. **Respuesta de Odoo:**
   - Busca por `numero_procedimiento`.
   - Si no existe, crea la licitación en la etapa *Nuevas*. Con nivel 4 o más pasa sola a *Análisis y decisión*.
   - Si existe, actualiza la licitación y agrega al historial los cambios de fecha y estatus.
   - **Nunca pisa** las decisiones del equipo: "¿participamos?", "¿ganada?" y el estado de los pendientes.

### Encabezados

```
Authorization: Bearer <token de Ajustes › CRM › LICIA>
Content-Type: application/json
```

### Respuesta

```json
{"ok": true, "accion": "creada|actualizada", "lead_id": 7, "name": "…", "url": "https://…/odoo/crm/7", "advertencias": []}
```

Códigos de respuesta:
- `401`: token inválido.
- `503`: integración desactivada.
- `400`: JSON inválido.
- `422`: ficha rechazada (viene el error).
- `207`: en un lote, algunas fichas entraron y otras no.

### Respaldo por correo

Si no hay conexión HTTP, LICIA manda un correo al alias del equipo Licitaciones (por ejemplo `licitaciones@<dominio>`):
- Asunto: `[FICHA LICITACIÓN] <numero_procedimiento> · …`.
- Adjunto: `ficha_<numero>.json`, con el mismo JSON.
- Si no puede adjuntar, pone el bloque `clave: valor` (encabezado plano) en el cuerpo.

## 2. Reglas de formato

| Tipo | Formato | Ejemplo |
|---|---|---|
| Fecha y hora | `AAAA-MM-DD HH:MM`, **hora local CDMX** | `2026-10-15 10:00` |
| Fecha | `AAAA-MM-DD` | `2026-11-10` |
| Monto | número sin signo ni comas, **sin IVA** | `13168217.17` |
| Sí/No | `SI` / `NO` | |
| No existe | `N/A` (Odoo lo deja vacío) | |
| Nivel | entero del 0 al 5 | `4` |

Los textos de catálogo (estatus, criterio, tipo de procedimiento, tipo de servicio, categoría de requisito) se reconocen sin importar acentos ni mayúsculas. Si un valor no existe, Odoo lo da de alta.

## 3. Campos del encabezado → Odoo

| Clave JSON | Campo Odoo | Notas |
|---|---|---|
| `numero_procedimiento` * | `stn_no_procedimiento` | **Obligatorio.** Es la llave |
| `nombre_oportunidad` | `name` | Solo se usa al crear |
| `nivel_licia` | `stn_viabilidad` | 0–5 |
| `accion` | `stn_accion` + `stn_accion_detalle` | perseguir / con condición / en espera / descartar |
| `estatus_procedimiento` | `stn_estatus_id` | VIGENTE, EN APERTURA, SUSPENDIDO, EN EVALUACIÓN, FALLADO, DESIERTO, CANCELADO |
| `plataforma`, `url_ficha` | `stn_plataforma`, `stn_url_ficha` | ComprasMX o CFE |
| `folio_plataforma` | `stn_folio_plataforma` | Folio del expediente (2026-A-L-NAC-…). **No** es el número de procedimiento |
| `fechas_verificadas` | `stn_fechas_verificadas` | Cuándo verificó LICIA las fechas en la ficha (para la cuenta regresiva) |
| `dependencia` | `stn_dependencia_id` | Cliente: IMSS, IMSS-Bienestar, ISSSTE, ASA, CFE… El convocante (OOAD) queda como hijo |
| `plaza` | `stn_plaza` | Ciudad o sede del servicio |
| `requiere_poliza_rc` | `stn_requiere_rc` | Si es SI, al ganar se crea también el pendiente de la póliza de RC |
| `empresa_licitante` | `stn_empresa_licitante_id` | PERLOP, JADE o JD. Si no viene, se usa la empresa de Odoo |
| `modalidad` | `stn_modalidad` | Electrónica, presencial o mixta. Si no viene, se lee de `tipo_procedimiento` («… electrónica») |
| `monto_minimo_estimado`, `monto_maximo_estimado` | `stn_monto_*_estimado` | Estimaciones de LICIA cuando la convocatoria no publica montos. Sin máximo oficial, el ingreso esperado toma el máximo estimado |
| `condiciones_entrega` | `stn_condiciones_entrega` | Horario, anticipación de órdenes, reposición de rechazos, pan y tortilla |
| `tipo_procedimiento` | `stn_tipo_procedimiento_id` + detalle | |
| `caracter` | `stn_caracter` | Nacional / Internacional |
| `criterio`, `minimo_tecnico` | `stn_criterio_id`, `stn_minimo_tecnico` | |
| `convocante` | `stn_convocante_id` | Contacto (empresa) |
| `unidad_compradora` | `partner_id` + `stn_unidad_compradora_clave` | La clave (`050GYR018`) se separa sola; el contacto queda como hijo del convocante |
| `area_requirente` | `stn_area_requirente` | |
| `estado`, `operamos_en_estado` | `state_id`, `stn_operamos_estado` | |
| `objeto`, `cucop`, `tipo_servicio` | `stn_objeto`, `stn_cucop`, `stn_tipo_servicio_id` | |
| `monto_minimo`, `monto_maximo` | `stn_monto_minimo`, `stn_monto_maximo` (= ingreso esperado) | |
| `nota_montos` | `stn_nota_montos` | |
| `vigencia_inicio`, `vigencia_fin` | `stn_vigencia_inicio`, `stn_vigencia_fin` | |
| `garantia_pct`, `conjunta_permitida` | `stn_garantia_pct`, `stn_conjunta_permitida` | |
| `cliente_nuevo` | `stn_cliente_nuevo` | |
| `lectura`, `razon_nivel` | `stn_lectura`, `stn_razon_nivel` | |
| `fecha_deteccion` … `fecha_inicio_contrato` | `stn_fecha_*` | `fecha_limite_interna` también llena el *Cierre esperado* |
| `junta.aplica / aclaraciones / acta` | `stn_junta_aplica`, `stn_aclaraciones`, `stn_acta_aclaraciones` | |
| `logistica_nota` | `stn_logistica_nota` | |
| `documentos.carpeta` | `stn_carpeta` | |
| `version`, `corte` | `stn_licia_version`, `stn_licia_corte` | |

### Investigaciones de mercado y proyectos de convocatoria (v1.4)

`tipo_registro`: `LICITACION` (por defecto) | `INVESTIGACION DE MERCADO` | `PROYECTO DE CONVOCATORIA`. Las IM y los proyectos se crean en su propio tablero y no entran al flujo de licitaciones. LICIA **no** las liga con la convocatoria real. Cuando sale la licitación, LICIA la manda como una licitación más, con su propio número. Si el equipo ya la creó con el botón «Salió la licitación», la ficha la actualiza sin regresarla a Nuevas. `tipo_registro` solo se toma al crear: una licitación nunca se vuelve IM.

## 4. Tablas

Cada fila se identifica con una **llave natural**. Si la llave ya existe, la fila se actualiza; si no, se agrega. Lo que el equipo captura a mano no se borra.

**v1.3 · `partidas[]` y `sedes[]` son la lista completa.** Si una ficha trae partidas, Odoo elimina las que ya no vienen, salvo las que tienen resultados capturados por el equipo (ganada, monto ofertado/adjudicado, nuestra suma de precios, dirección de entrega): esas se conservan con una advertencia. Igual con las sedes que mandó LICIA (las capturadas a mano se respetan). Si LICIA no tiene la lista completa, omite la clave. La llave de partida se compara sin el prefijo «Partida/Lote/Grupo» ni ceros a la izquierda («Partida 01» = «1»).

| Lista JSON | Tabla Odoo | Llave | Claves de cada fila |
|---|---|---|---|
| `eventos[]` | Eventos | `tipo` | `tipo` (publicacion, limite_preguntas, junta, cierre_junta, visita, muestras, apertura, fallo, firma, inicio_contrato, otro), `fecha_oficial`, `fecha_limite_interna`, `aplica`, `fuente`, `nota` |
| `historial[]` | Historial de cambios | fecha + campo + antes + después | `fecha`, `campo`, `antes`, `despues`, `fuente` |
| `preguntas[]` | Preguntas de aclaración | `numero` | `numero`, `pregunta`, `numeral`, `estado`, `respuesta` |
| `partidas[]` | Partidas | `clave` (G3, G7A…) o `numero` | `clave`, `numero`, `ganador_anterior`, `suma_precios_ganador`, `nuestra_suma_precios`, `maximo_estimado` (SI/NO), `lugar_precios`, `unidad`, `municipio`, `domicilio`, `domicilio_alterno`, `domicilio_inconsistente`, `corredor`, `vehiculos`, `cedis`, `minimo`, `maximo`, `maximo_anterior`, `participamos`, `ganada`, `nota`, `renglones[]` |
| `sedes[]` | Sedes y logística | `unidad` | `unidad`, `partidas` (lista o texto), `municipio`, `domicilio`, `domicilio_alterno`, `domicilio_inconsistente`, `corredor`, `vehiculos`, `cedis`, `horario`, `nota` |
| `partidas[].renglones[]` | Renglones | `numero` o nombre | `numero`, `nombre_contractual`, `clave`, `unidad_medida`, `cantidad_minima`, `cantidad_maxima`, `precio_unitario` |
| `requisitos[]` | Requerimientos | referencia + requisito | `referencia`, `requisito`, `nota`, `extracto_literal`, `captura_base64`, `tipo`, `situacion`, `efecto`, `vigencia_maxima`, `antiguedad_max_dias`, `categoria` |
| `puntos[]` | Puntos | `rubro` | `rubro`, `puntos`, `entregable`, `situacion` |
| `antecedentes[]` | Antecedentes | `procedimiento` | `procedimiento`, `participamos`, `criterio`, `participantes`, `razon_mismo`, `ganador`, `puntos_ganador`, `contrato`, `como_gano`, `precio_a_vencer`, `monto_maximo`, `vigencia`, `desiertas[]`, `hipotesis` |
| `competidores[]` | Competidores | `nombre` | `nombre`, `historia`, `lectura` |
| `resultado{}` | Pestaña Resultado | — | `apertura_celebrada`, `lugar_precios`, `fallo` (GANADA / PARCIAL / PERDIDA / DESIERTA), `causa_literal` (texto del acta), `motivo_perdida` (uno de los motivos de Odoo) |
| `pendientes_fallo[]` | Pendientes post-fallo | `pendiente` | `pendiente`, `plazo`, `fecha`, `fuente` |
| `seguimiento[]` | Seguimiento diario y chatter | fecha + texto | `fecha`, `texto` |
| `adjuntos[]` | Adjuntos | `nombre` | `nombre`, `mimetype`, `contenido_base64`. El PDF cuyo nombre contiene "Requisitos" se guarda además en el campo *Requisitos* |

Valores reconocidos en `situacion`: TENEMOS, SE GENERA, VERIFICAR, CONSEGUIR / FALTA, NO APLICA. El texto original se conserva en el campo de detalle.

Si `tipo` dice "Puntos (14)" se guarda como tipo *Puntos* y el texto original queda en el detalle.

Un requisito se marca como **desecha** cuando su `efecto` contiene "DESECHA", salvo que diga "NO DESECHA".

Del texto de `vigencia_maxima` («3 meses», «30 días», «menos de 6 meses») Odoo calcula la antigüedad máxima en días cuando no viene `antiguedad_max_dias`. El **semáforo se calcula por licitación**: compara el documento maestro contra la fecha de referencia (la apertura). Si la apertura se difiere, se recalcula solo.

Si no viene `tipo_procedimiento` o `caracter`, Odoo los lee del número de procedimiento (LA/IA/AA y N). La clave de la UC también sale del número.

La logística vive solo en **Sedes** (v1.3). Si LICIA aún manda domicilio, corredor, vehículos o CEDIS dentro de una partida, Odoo crea o completa la sede correspondiente y la liga a esa partida; en la tabla de partidas solo se ve la columna *Sedes*.

**Eventos (v1.3):** solo límite de preguntas, junta, visita, muestras, apertura, firma y «otro» llevan límite interno, actividad, aviso y escalamiento. Publicación, cierre de junta, fallo e inicio de contrato son informativos (solo calendario). Apertura y muestras se activan cuando la licitación se aprueba (etapa Preparación). Cada fecha se avisa una vez y se escala una vez; si LICIA reenvía la misma fecha no se repite; si la fecha oficial ya pasó, no se escala. Si LICIA manda el límite interno, Odoo calcula la anticipación en horas.

**Encabezado (v1.3):** `fecha_deteccion` solo se guarda la primera vez. `area_requirente` se ignora si repite la unidad compradora o el convocante. Estatus nuevos en el catálogo: *En aclaraciones* y *En repreguntas*.

La diferencia «nosotros contra el ganador» la calcula Odoo con las dos sumas de precios.

**Las tablas viajan en el JSON**, ya sea en el cuerpo del POST o en el `.json` adjunto al correo. El bloque `clave: valor` del correo solo sirve de respaldo para el encabezado.

## 5. Reporte diario

`POST {ODOO}/stn/licitaciones/reporte`, con los mismos encabezados. Se registra en *Licitaciones › Reportes diarios de LICIA* y se publica en el canal de Discuss **Licitaciones · LICIA**, que sustituye el WhatsApp.

```json
{"fecha": "2026-10-15", "plataformas": ["ComprasMX", "CFE"], "revisados": 214, "nuevos": 2, "enviados": 1,
 "resumen": "…", "procedimientos": [{"numero_procedimiento": "…", "descripcion": "…", "nivel": 4,
 "recomendacion": "Perseguir con condición", "es_nuevo": "SI"}]}
```

Si se manda el mismo día dos veces, el reporte se reemplaza. El ejemplo completo está en `reporte_diario_ejemplo_v1.json`.

## 6. Recomendaciones para LICIA

- Mandar la ficha **completa** cada día que haya cambios. Odoo detecta qué cambió.
- Llenar `historial[]` con los cambios que LICIA detecta en el portal; Odoo agrega aparte los cambios de fecha que observa él mismo.
- Para las licitaciones de `procedimientos_en_seguimiento`, mandar al menos `numero_procedimiento`, `estatus_procedimiento`, las fechas y el `seguimiento[]` del día.
- No mandar comentarios del grupo en `resultado.causa_literal`, solo el texto del acta.
