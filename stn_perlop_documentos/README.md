# stn_perlop_documentos · Documentos legales en Documentos de Odoo

Odoo es la **fuente única** de los documentos legales de cada empresa del grupo (PERLOP, JD y JADE). LEXA ya no los toma de una carpeta de la computadora: los descarga de Odoo, en solo lectura.

Depende de `documents` (Enterprise) y de `stn_perlop_licitaciones` v1.6 o superior.

## Estructura de carpetas propuesta

```
Licitaciones · Documentos de la empresa            (carpeta de la compañía, compartida solo con el grupo Licitaciones)
└── <Empresa del grupo>                             (una por empresa: PERLOP, JD, JADE)
    ├── 00 Constitución y personalidad              acta constitutiva y reformas, poderes, identificación y cuadro de personalidad del representante
    ├── 01 Licencia municipal                       licencia de funcionamiento, uso de suelo
    ├── 02 Laboratorios                             análisis microbiológicos, agua, estudios clínicos del personal (EMA)
    ├── 03 Sanitario                                aviso de funcionamiento COFEPRIS, contrato y certificados de fumigación
    ├── 04 Legal y fiscal                           CSF, opiniones SAT/IMSS/INFONAVIT, RUPC, registro patronal, estratificación
    ├── 05 Vehículos                                tarjetas de circulación, verificaciones, permisos
    ├── 06 Experiencia y contratos                  contratos anteriores, cartas de satisfacción, cancelación de fianzas
    ├── 07 Certificaciones                          NMX-R-025 igualdad laboral, Distintivo H, ISO
    ├── 08 Seguros y fianzas                        póliza de responsabilidad civil, fianzas vigentes
    └── 09 Personal                                 DC-3 y capacitación, altas IMSS
```

- Cada subcarpeta es una **categoría** del catálogo «Requisitos (vigencias)». Si se agrega una categoría en Configuración, «Crear carpetas en Documentos» crea su carpeta.
- Las categorías 01 a 06 ya existían en Studio y se conservaron. Las nuevas son 00 (Constitución y personalidad), 07, 08 y 09. Una protección civil, por ejemplo, va en «01 Licencia municipal».

## Cómo se usa

1. **Ajustes › CRM › Documentos de la empresa**: se eligen las empresas del grupo y se pulsa «Crear carpetas en Documentos». Las carpetas se comparten con los usuarios del grupo Licitaciones.
2. **Se sube el archivo a su carpeta** en Documentos. Se registra solo en «Requisitos (vigencias)», con la empresa y la categoría de la carpeta.
3. **Se captura en el catálogo** la fecha de emisión, la vigencia en meses y los días de trámite. Con eso corre el semáforo: vigente, próximo a vencer o vencido, con la actividad de renovación.
4. **Para renovar**, se sube la nueva versión del mismo documento en Documentos y se actualiza la fecha de emisión.
5. **LEXA** recibe en el expediente solo los documentos de la empresa que licita y los descarga de Odoo. Lo que lee (RFC, fecha interna, folio, legibilidad) queda en la pestaña «Revisión de LEXA» del documento.

Si un documento maestro ya estaba capturado con el mismo nombre, el archivo que se sube se liga a ese registro y no se duplica.

## Documentos de prueba

En **Ajustes › CRM › Documentos de la empresa › Documentos de prueba** se cargan 22 PDF marcados «DOCUMENTO DE PRUEBA · SIN VALIDEZ OFICIAL». Quedan en las carpetas de la empresa, con fechas pensadas para que el semáforo muestre todos los casos. El botón «Quitar los de prueba» borra solo esos. En el expediente, LEXA los ve marcados con `es_prueba` y nunca los usa en una proposición real.

## Notas técnicas

- Las carpetas son `documents.document` de tipo `folder`. Se crean con propietario OdooBot (sección «Compañía»), `access_internal = 'none'` y acceso de editor para el grupo Licitaciones mediante `documents.access`.
- El código solo usa los campos que existen en la versión instalada de Documentos.
- Las pruebas locales corrieron contra una réplica mínima de `documents`, porque Documentos es Enterprise. **Hay que validarlo en una rama de staging del Odoo.sh de Perlop antes de producción.**
