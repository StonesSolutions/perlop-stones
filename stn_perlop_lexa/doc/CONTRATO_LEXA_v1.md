# Contrato de integración LEXA ↔ Odoo · v1.1 (fase 1 + documentos legales en Odoo)

Módulo: `stn_perlop_lexa` (depende de `stn_perlop_licitaciones` v1.5). Esquema del JSON: `lexa.encargo/1.0`, basado en la propuesta que hizo LEXA el 06-nov-2026 («LEXA-campos-Odoo-ejemplo.json»).

## 1. Cómo fluye

1. **El equipo pide el trabajo en Odoo** con un botón de la licitación:
   - **Armar matriz con LEXA**, en las etapas Preparación de propuesta y Revisión IA. LEXA arma la matriz de cotejo por casilla de ComprasMX.
   - **Revisar con LEXA**, en las etapas Revisión IA e Integración final. LEXA revisa los archivos que subió el equipo en Requerimientos › «Nuestros archivos» y dice, requisito por requisito, si cumplen o no.

   Cada pedido crea un **encargo**: tipo (matriz o revisión), parte (legal o técnica), versión de la matriz y estado.
2. **LEXA recibe el encargo** de una de dos formas, que se eligen en Ajustes › CRM › LEXA:
   - **Cola** (LEXA en la Mac): LEXA consulta `GET /stn/lexa/pendientes`, ya sea cuando la persona le dice «revisa los pendientes de Odoo» o con una tarea programada en la Mac.
   - **Tarea de Claude** (LEXA en la nube): Odoo dispara la tarea de LEXA con su activador API, igual que con LICIA, y le manda este texto:
     ```
     LEXA_ENCARGO <id>
     PROCEDIMIENTO <número>
     TIPO MATRIZ|REVISION
     PARTE LEGAL|TECNICA
     EXPEDIENTE <url>
     SOLICITADO_POR <nombre>
     ```
3. **LEXA lee el expediente** con `GET /stn/lexa/expediente?encargo_id=<id>`, que pasa el encargo a «LEXA trabajando». El expediente trae:
   - los datos de la licitación y sus fechas;
   - la convocatoria y sus anexos;
   - las casillas;
   - los requisitos, con su texto íntegro y «nuestros archivos»;
   - los faltantes;
   - qué matriz está aprobada;
   - **los documentos legales de la empresa que licita** (`soportes_empresa`). Odoo es la fuente única: ya no se buscan en OneDrive.

   Los archivos se descargan con `GET /stn/lexa/archivo/<id>`.
4. **LEXA responde** con `POST /stn/lexa/encargo`.
5. **Una persona decide en Odoo:**
   - con «Aprobar matriz» aprueba la matriz. Pueden hacerlo el líder de proyecto o un Director;
   - con «Pedir cambios» crea un encargo nuevo con la versión siguiente;
   - con «Marcar subido» marca cada casilla como subida.

## 2. Autenticación

Encabezado `Authorization: Bearer <token de LEXA>`. El token es **distinto al de LICIA**: Ajustes › CRM › LEXA › «Generar nuevo token». Todas las rutas responden 503 si la integración está apagada y 401 si el token no es válido.

## 3. Rutas

| Ruta | Método | Para qué |
|---|---|---|
| `/stn/lexa/ping` | GET | Probar conexión |
| `/stn/lexa/pendientes` | GET | Encargos en estado «solicitado» o «requiere regenerar» |
| `/stn/lexa/expediente?encargo_id=` (o `?numero=`) | GET | Todo lo que LEXA necesita leer |
| `/stn/lexa/archivo/<id>` | GET | Descarga. Solo se pueden bajar archivos de la convocatoria, «nuestros archivos», archivos de subida, la matriz o documentos legales de una empresa del grupo |
| `/stn/lexa/encargo` | POST | Matriz, revisión, casillas y faltantes |

Respuesta del POST: `{"ok": true, "encargo_id", "estado", "lead_id", "casillas", "requisitos", "revisados", "advertencias": [...]}`. Si hay error, responde 422 con `{"ok": false, "error": "..."}`. Cada envío queda en la Bitácora (origen «LEXA»).

## 4. JSON `lexa.encargo/1.0`

Hay dos ejemplos completos en `ejemplo_encargo_matriz.json` y `ejemplo_encargo_revision.json`.

### Llave

- `encargo_id`: el del pendiente. Si viene, manda sobre la llave.
- `llave.numero_procedimiento`: obligatorio si no hay `encargo_id`.
- `llave.empresa`, `llave.parte` (`legal` | `tecnica`) y `llave.version_matriz`.
- `tipo`: `matriz` | `revision`.

Reglas:

- **LEXA no crea licitaciones.** Si el número no existe en Odoo, el envío se rechaza.
- **Triple cotejo.** Si el número no coincide con el del encargo, se rechaza.
- **Nunca se mezclan empresas.** Si la `empresa` no coincide con la «Empresa del grupo que licita» de Odoo, se rechaza. La empresa la define una persona.
- **Una versión nueva de una matriz ya aprobada es un encargo nuevo**, y empieza sin aprobar.

### Qué escribe LEXA en Odoo

| Bloque del JSON | Dónde queda en Odoo | Llave / regla |
|---|---|---|
| `casillas[]`: `pestana`, `orden`, `nombre_exacto`, `obligatoria`, `estado` | Pestaña LEXA › Casillas | `pestana` + `orden`. **Reemplaza, no acumula**: las casillas de LEXA que ya no vienen se quitan, salvo las que ya tienen archivo o están subidas. LEXA nunca marca `subido` |
| `requisitos[]` (renglones de la matriz) | Pestaña Requerimientos (amplía el requisito) | Busca primero por `id` (el que viene en el expediente), luego por `orden_casilla`, luego por `numeral` y al final por `documento_solicitado`. Si no encuentra el requisito, lo crea con origen LEXA. **Reemplaza**: los renglones que LEXA creó antes en esa pestaña y ya no vienen se quitan, salvo los que tienen archivos o avance «Completo» |
| `orden_casilla` «1.4» | Casilla 1 + subíndice 4 | Ordena la pestaña y el avance por casilla |
| `numeral`, `texto_integro`, `anexo_o_formato`, `soportes_que_manda_acompanar`, `causal_desechamiento_literal`, `huella`, `fundamento`, `clase_formato`, `quien_lo_hace`, `informacion_localizada`, `informacion_pendiente`, `semaforo`, `explicacion_en_corto`, `firma_requerida`, `evidencia_archivo_pagina`, `vigencia_maxima`, `situacion`, `tipo`, `cambiado_por_junta` | Columnas del requisito | `texto_integro` → extracto literal; `informacion_localizada` → detalle de situación; la causal llena «Efecto» y la marca «Desecha» |
| `revision[]`: `requisito_id` o `orden_casilla` o `numeral`, `dictamen` (CUMPLE / NO CUMPLE / PARCIAL), `observacion`, `evidencia` | Columna «Revisión LEXA» + observación | El dictamen actualiza el **avance**: Cumple → Completo; No cumple o Parcial → Incompleto. «No aplica» no se toca |
| `faltantes[]`: `documento`, `requisito`, `dato_faltante`, `donde_se_busco`, `lugar_en_documento`, `consecuencia`, `desecha`, `solicitado_a`, `estado` | Pestaña LEXA › Faltantes | `documento` + `requisito`. Si viene `solicitado_a` (nombre de un usuario de Odoo), se crea una actividad. Lo que LEXA ya no reporta queda «resuelto». Lo que una persona cerró no se reabre |
| `matriz` `{nombre, contenido_base64}` | Archivo del encargo | Una versión por encargo |
| `resumen`, `estado`, `error` | Encargo | Estados: `en_proceso`, `matriz_lista`, `revisado`, `error` |

### Documentos legales de la empresa (v1.1)

Viven en **Documentos de Odoo**, en `Licitaciones · Documentos de la empresa / <Empresa> / NN <Categoría>`, y están ligados al catálogo «Requisitos (vigencias)».

**En el expediente**, `soportes_empresa[]` trae solo los documentos de la «Empresa del grupo que licita». Si la licitación no tiene empresa, la lista viene vacía. Por cada documento:

- `id`, `nombre`, `categoria`;
- `fecha_emision`, `vigencia_meses`, `fecha_vencimiento`;
- `semaforo`: vigente, proximo, vencido o sin_vencimiento;
- `vigente_a_la_apertura`;
- `es_prueba`: si es un documento de prueba;
- lo que LEXA ya leyó antes;
- `archivos[]`, con la URL de descarga.

**En la matriz**, `requisitos[].documento_maestro` es el `id` (o el nombre del archivo) del documento que LEXA usó para ese requisito. Odoo lo liga al requisito de la licitación y así corre el semáforo por licitación. Si el documento es de otra empresa, no se liga.

**Bloque `soportes[]`** (lo que LEXA lee dentro del documento):

| Clave | Qué hace Odoo |
|---|---|
| `documento_maestro` (id) o `archivo` (nombre) | Identifica el documento, solo dentro de la empresa que licita |
| `rfc_en_documento` | Lo guarda. Si no es el RFC de la empresa, lo marca con alerta, lo avisa y **no lo liga** al requisito |
| `fecha_emision_interna` | Si el catálogo no tiene fecha, la llena y recalcula el semáforo. Si tiene otra, avisa y no la cambia: la corrige una persona |
| `fecha_sello`, `folio_o_numero`, `observacion` | Los guarda |
| `legibilidad` (legible, dudosa, ilegible) | Si es dudosa o ilegible, lo marca con alerta |
| `contradice_declaracion` | Lo guarda y lo marca con alerta |
| `requisito` (orden_casilla o numeral) | Liga el documento al requisito de la licitación |

Las alertas se ven con la cinta «Revisar (LEXA)» y el filtro «Con alerta de LEXA» del catálogo, y quedan en el chatter del documento. LEXA nunca modifica ni reemplaza el archivo.

### Qué NO escribe LEXA (se ignora y se avisa en `advertencias`)

- **Aprobaciones**: `aprobaciones`, `matriz_aprobada_por/fecha`, visto bueno final, «subido a ComprasMX». Las marca una persona en Odoo; si LEXA pudiera escribirlas, la compuerta perdería sentido.
- **Fechas**: las manda LICIA. Si las `fechas` de LEXA no coinciden con las de Odoo, se avisa en el chatter y no se cambian.
- **Fase posterior**: `documentos_convocatoria` (tipo, huella sha256, OCR, legibilidad), `entregables` (Word/PDF, Bates), `verificaciones` (compuertas) y `firmas`. Se guardan en el JSON del encargo para no perderlos.

### `comprasmx_ultima_revision`

Si trae anexos nuevos o reemplazados, actas de junta nuevas o avisos de cambio de fecha, o si `casillas_cuadran_con_matriz` es `false`, Odoo avisa en el chatter al líder de proyecto.

## 5. Lo que hace Odoo por su cuenta

- **Cambio de apertura → «Requiere regenerar».** Si cambia la fecha de apertura, los encargos entregados, aprobados o revisados pasan a ese estado y se avisa al líder. Aparecen otra vez en `/pendientes`.
- **Avisos.** Cuando hay una matriz por aprobar, se crea la actividad «Aprobar matriz de LEXA» para el líder de proyecto (o el vendedor). Si en una revisión hay requisitos que no cumplen, se crea la actividad «Atender observaciones de LEXA».
- **Avance.** El porcentaje legal, técnico y económico y los chips por casilla salen del avance de cada requisito.
