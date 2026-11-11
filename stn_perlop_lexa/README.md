# stn_perlop_lexa · LEXA en el CRM de Licitaciones (fase 1)

Integra a LEXA, el agente de PERLOP que arma la proposición legal y técnica, con `stn_perlop_licitaciones` (v1.5 o superior).

## Qué agrega

- **Botones en la licitación**
  - «Armar matriz con LEXA», en Preparación de propuesta y Revisión IA.
  - «Revisar con LEXA», en Revisión IA e Integración final.
  - Cada uno crea un **encargo** (matriz o revisión, parte legal o técnica, versión).
- **Pestaña LEXA** con tres tablas:
  - encargos, con «Aprobar matriz» y «Pedir cambios»;
  - casillas de «Mi proposición» de ComprasMX, con «Marcar subido»;
  - faltantes, con dónde se buscaron, si desechan y a quién se pidieron.
- **Requerimientos**: columnas de la matriz y «Revisión LEXA» (cumple / parcial / no cumple), con su observación. Las columnas de la matriz son casilla, subíndice, anexo, soportes, causal literal, huella, clase de formato, quién lo hace, semáforo, explicación en corto, firma, evidencia, fundamento y cambio por junta.
- **Compuerta humana**:
  - LEXA nunca escribe la aprobación de la matriz ni «subido a ComprasMX»;
  - aprueba el líder de proyecto o un Director;
  - una versión nueva de la matriz empieza sin aprobar.
- **Cambio de apertura**: si cambia la fecha de apertura, los encargos pasan a «Requiere regenerar» y se avisa al líder.
- **Ajustes › CRM › LEXA**: activar la integración y tener token propio. Hay dos modos:
  - **Cola**: LEXA en la Mac consulta los pendientes.
  - **Tarea de Claude**: Odoo dispara la tarea de LEXA con un activador API.
- **Menús**: Licitaciones › Encargos de LEXA y Faltantes de proposición.
- **v1.1 · Documentos legales desde Odoo**:
  - el expediente trae los documentos de la empresa que licita (`soportes_empresa`) y LEXA los descarga de Odoo;
  - en la matriz, LEXA indica qué documento maestro respalda cada requisito, y eso alimenta el semáforo por licitación;
  - con el bloque `soportes[]`, LEXA reporta el RFC, la fecha interna, el sello, el folio, la legibilidad y las contradicciones;
  - las alertas se ven con la cinta «Revisar (LEXA)» del catálogo.

## Queda para una fase posterior

Lo que LEXA ya manda queda guardado en el JSON del encargo:

- tipo y huella sha256 de cada documento de la convocatoria, OCR y legibilidad;
- entregables Word/PDF con rango Bates;
- verificaciones (`guardia_matriz`, `auditar_cobertura`, `verificar_firma`, `foliar`);
- lista de firmas.

## Documentos

- `doc/CONTRATO_LEXA_v1.md`: rutas, JSON y reglas.
- `doc/GUIA_LEXA_ODOO.md`: skill para que LEXA tome los encargos y responda.
- `doc/ejemplo_encargo_matriz.json` y `doc/ejemplo_encargo_revision.json`.

## Pruebas

`tests/test_lexa.py` cubre:

- la matriz con sus casillas, faltantes y la aprobación humana;
- el reemplazo de renglones por una versión nueva;
- la revisión cumple / no cumple y su efecto en el avance;
- las validaciones de empresa y número;
- el cambio de apertura;
- los endpoints HTTP con token propio.
