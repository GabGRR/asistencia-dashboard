# DASHBOARD_CONTEXT

Este documento conserva el contexto técnico y operativo de `asistencia_dashboard`. Antes de realizar cambios, leer este archivo y contrastarlo con el código actual.

## 1. Objetivo del proyecto

`asistencia_dashboard` es una aplicación independiente en Streamlit. Recibe un PDF de checadas con formato **Reporte de Tarjeta** y calcula, para una fecha seleccionada, cuántas personas tienen o no tienen al menos una checada.

El sistema responde:

- quién tiene al menos una checada en la fecha;
- quién no tiene checada;
- conteos por tipo de personal y turno;
- problemas de cruce entre el PDF y los catálogos.

No califica retardos, faltas administrativas, salidas anticipadas ni justificaciones. Tampoco determina si una persona cumplió su horario o jornada completa.

## 2. Uso operativo real

La aplicación se utiliza como corte de asistencia diaria, especialmente alrededor de las 6 p. m., para consultar rápidamente:

- cuántos PAAE matutinos vinieron;
- cuántos PAAE vespertinos vinieron;
- cuántos docentes matutinos vinieron;
- cuántos docentes vespertinos vinieron;
- quiénes no tienen checada;
- qué personas no pudieron cruzarse correctamente entre PDF y catálogo.

## 3. Flujo actual

1. La app intenta cargar los catálogos remotos configurados en Streamlit Secrets o variables de entorno:
   - `PAAE_CATALOG_URL`;
   - `DOCENTES_CATALOG_URL`.
2. También ofrece uploaders de Excel independientes como respaldo. Un archivo subido reemplaza la fuente remota correspondiente durante esa sesión.
3. Los catálogos PAAE y Docentes se normalizan y se unen en un solo catálogo.
4. El usuario sube el PDF de checadas. Los archivos se procesan en memoria.
5. El parser detecta páginas, empleados, fechas y horas registradas por fecha.
6. Si hay una fecha, se selecciona automáticamente. Si hay varias, se muestra un selector.
7. Las fechas se presentan con día de la semana, por ejemplo `Sábado 23/05/2026`, pero internamente conservan el formato `DD/MM/AAAA`.
8. La app cruza las páginas del PDF contra el catálogo unificado, primero por ID y después por nombre normalizado.
9. Se muestran métricas generales, desglose por tipo y turno, una pestaña de Consulta con búsqueda/filtros y problemas de cruce.
10. La interfaz `v1.5.0` usa una cabecera compacta en tres bloques: identidad del corte, carga del PDF y fecha seleccionada.
11. La búsqueda de Consulta ofrece autocompletado por nombre, apellido o ID con opciones `ID · nombre`, sin impedir búsquedas escritas manualmente.
12. Los resultados pueden descargarse como Excel o CSV.
13. Desde `v1.6.0`, la barra lateral permite elegir entre `Oscuro guinda actual` y `Product UI claro`; la misma barra concentra los reemplazos y el estado de los catálogos.

## 4. Catálogos

### PAAE

- Fuente remota: `PAAE_CATALOG_URL`.
- Total operativo esperado actual: aproximadamente 108 personas.
- El formato habitual contiene `ID`, apellidos, nombre, hora de entrada y hora de salida.
- El turno se infiere desde la hora de entrada: antes de las 12:00 es `MATUTINO`; desde las 12:00 es `VESPERTINO`. Sin una hora válida queda `SIN TURNO / REVISAR`.

### Docentes

- Fuente remota: `DOCENTES_CATALOG_URL`.
- Total operativo esperado actual: aproximadamente 236 personas.
- Puede recibirse en formato normalizado o en el formato original.
- El cargador inspecciona encabezados y admite, en este orden general:
  1. `Catalogo_normalizado` compatible;
  2. `Hoja1` compatible;
  3. otras hojas con estructura normalizada;
  4. `DOCENTES 2026-21` con formato original;
  5. otras hojas compatibles con el formato original.
- El formato original puede tener el encabezado varias filas debajo del inicio de la hoja e incluye campos como `No. EMPLEADO`, nombre, apellidos y `TURNO`.
- Si ninguna hoja es compatible, se genera un diagnóstico con hojas inspeccionadas, posible fila de encabezado, columnas encontradas y motivo del rechazo.

### Catálogo unificado esperado

Las cifras son referencias operativas y pueden cambiar cuando cambien los archivos fuente:

- PAAE: aproximadamente 108;
- Docentes: aproximadamente 236;
- Total: aproximadamente 344;
- Matutino: alrededor de 190;
- Vespertino: alrededor de 139;
- Sin turno/Revisar: alrededor de 15.

## 5. Formato interno del catálogo

Los dos orígenes se normalizan a estas columnas:

- `empleado_id`;
- `nombre_completo`;
- `apellido_paterno`;
- `apellido_materno`;
- `nombre`;
- `tipo_personal`;
- `turno`;
- `hora_entrada`;
- `hora_salida`;
- `activo`;
- `fuente`.

Los IDs, nombres, encabezados, turnos y horas se limpian antes de construir el catálogo unificado. Los nombres se normalizan sin acentos y en mayúsculas para facilitar el cruce.

## 6. Regla de asistencia

Para la fecha seleccionada:

- `CON_CHECADA`: la persona tiene al menos una hora o registro en la fecha.
- `SIN_CHECADA`: la persona del catálogo fue localizada en el PDF, pero no tiene horas en esa fecha. También se usa cuando su página existe pero no contiene la fecha seleccionada, dejando el detalle correspondiente.
- `NO_ENCONTRADO_EN_PDF`: la persona está en el catálogo activo, pero no se encontró en el PDF.
- `AMBIGUO`: el cruce no es seguro, por ejemplo por duplicados o más de una página coincidente.
- `PDF_ONLY`: concepto usado para las páginas/personas que aparecen en el PDF pero no se cruzaron de forma única con el catálogo. En el código se conserva en la colección `pdf_only` y se transforma en un problema estandarizado.

El cruce intenta primero por `empleado_id`; si no encuentra coincidencia, intenta por `nombre_completo` normalizado.

Importante: **“vino” significa únicamente que existe al menos una checada**. No significa que llegó puntual, que completó su jornada o que cumplió un horario determinado.

## 7. Archivos principales

### `app.py`

Punto de entrada de Streamlit. Configura la página, carga catálogos remotos o manuales, unifica el padrón, recibe el PDF, permite seleccionar fecha, ejecuta el análisis y muestra métricas, tarjetas, gráfica, tablas, descargas y diagnóstico.

### `core/pdf_daily_parser.py`

Abre el PDF desde bytes con PyMuPDF, extrae texto y líneas posicionadas, detecta ID, nombre, fechas y horas por página, reúne diagnósticos y ordena las fechas. También formatea las etiquetas de fecha con el día de la semana.

### `core/catalog.py`

Normaliza IDs, nombres, columnas, horarios y turnos. Detecta y carga los formatos PAAE y Docentes, elige hojas y filas de encabezado compatibles, descarga catálogos remotos en memoria, lee Secrets o variables de entorno, unifica ambos catálogos y genera diagnósticos de calidad.

### `core/attendance.py`

Construye índices del PDF por ID y nombre, cruza cada persona del catálogo, determina su estado para la fecha seleccionada y genera resultados individuales, métricas generales, resumen por tipo/turno y páginas del PDF no cruzadas.

### `core/export.py`

Convierte DataFrames a CSV UTF-8 y genera un Excel en memoria con resumen general, resumen por grupos, personas con checada, personas sin checada y problemas de cruce.

### `core/problem_reporting.py`

Convierte listas, diccionarios y DataFrames heterogéneos a una tabla robusta de problemas. Elimina columnas duplicadas, reinicia índices y estandariza la salida para evitar errores durante `concat` o `drop_duplicates`.

Las columnas estándar son:

- `fuente`;
- `tipo_problema`;
- `empleado_id`;
- `nombre_completo`;
- `tipo_personal`;
- `turno`;
- `detalle`.

### `core/query.py`

Filtra la tabla de resultados sin alterar los datos base. Permite búsqueda normalizada por nombre o ID y combina filtros de estado, tipo de personal, turno y tipo de coincidencia.

### `tests/test_dashboard.py`

Contiene pruebas unitarias del parser en memoria, etiqueta de día de semana, carga PAAE, formatos docentes original y normalizados, unificación, clasificación de asistencia, duplicados ambiguos, consulta filtrada y normalización robusta de la tabla de problemas.

### `requirements.txt`

Declara las dependencias de ejecución: Streamlit, PyMuPDF, pandas, openpyxl, xlrd y requests.

### `README.md`

Documentación pública breve para instalación, ejecución, estructura de catálogos, configuración remota, privacidad, regla de asistencia, limitaciones y pruebas. No debe contener URLs privadas.

## 8. Streamlit Secrets

Las URLs reales no deben aparecer en código, documentación pública, commits ni interfaz. Se configuran en Streamlit Cloud o mediante variables de entorno:

```toml
PAAE_CATALOG_URL = "https://..."
DOCENTES_CATALOG_URL = "https://..."
```

Reglas:

- no hardcodear enlaces reales;
- no mostrar URLs completas en la interfaz ni en diagnósticos;
- no subir `.streamlit/secrets.toml` a Git;
- mantener `.streamlit/secrets.toml.example` únicamente con placeholders cuando dicho archivo exista o se agregue;
- conservar los uploaders manuales como respaldo.

El `.gitignore` excluye `.streamlit/secrets.toml`, PDFs, Excels, `data/`, cachés de Python y entornos virtuales.

## 9. GitHub y despliegue

- Repositorio: `https://github.com/GabGRR/asistencia-dashboard.git`.
- Rama de despliegue: `main`.
- Streamlit Cloud despliega desde el repositorio `asistencia-dashboard`, rama `main`, archivo `app.py`.
- Cada `git push` a la rama configurada actualiza la aplicación desplegada.

Antes de subir cambios, verificar siempre el diff y que no existan archivos sensibles preparados para commit.

## 10. Estado actual conocido

- La app está desplegada en Streamlit Cloud.
- El catálogo remoto PAAE carga correctamente.
- El catálogo remoto Docentes carga correctamente.
- Referencia actual: PAAE 108, Docentes 236, catálogo unificado 344.
- El PDF `MAYO226.pdf` ya se procesó sin `pandas.errors.InvalidIndexError` después de robustecer la tabla de problemas.
- Las fechas detectadas se muestran con día de la semana.
- La app sigue procesando PDFs y Excels en memoria, sin persistencia de base de datos.

## 11. Errores ya corregidos

### Docentes aparecía como 0

El cargador anterior dependía de la hoja `DOCENTES 2026-21` y del encabezado `No. EMPLEADO`. El archivo remoto podía ser una versión normalizada con hojas como `Catalogo_normalizado` o `Hoja1`, por lo que no encontraba registros.

Se corrigió la selección de hojas para aceptar primero formatos normalizados y conservar el formato original como respaldo, además de ofrecer diagnóstico cuando ninguna tabla es compatible.

### `pandas.errors.InvalidIndexError` en problemas

La tabla de problemas concatenaba DataFrames que podían tener columnas duplicadas, índices irregulares o estructuras diferentes. Esto podía romper `pd.concat` o la eliminación de duplicados.

La lógica se movió a `core/problem_reporting.py`, donde cada entrada se transforma a DataFrame, se eliminan nombres de columna duplicados, se reinicia el índice y se proyecta a las columnas estándar antes de concatenar. Si no existen problemas, devuelve un DataFrame vacío con el esquema correcto.

## 12. Cosas que NO debe hacer este dashboard

- No calificar retardos.
- No calcular faltas administrativas.
- No aplicar justificaciones.
- No anotar PDFs.
- No modificar el sistema principal `checadas_app`.
- No guardar PDFs, Excels, catálogos reales ni reportes sensibles en Git.
- No hardcodear URLs reales.
- No mezclar cambios de diseño con cambios del parser.
- No mezclar cambios de diseño con cambios de conteo.
- No implementar base de datos todavía sin un plan explícito.
- No asumir que una checada prueba puntualidad o jornada completa.

## 13. Próximas mejoras posibles

Estas son ideas futuras; no están implementadas ni deben iniciarse sin una solicitud explícita.

### Diseño visual

- mejorar el layout;
- crear tarjetas más claras;
- usar colores por grupo;
- preparar una vista ejecutiva para el jefe;
- limpiar la presentación de tablas;
- agregar filtros rápidos.

### Funcionalidad

- guardar cortes diarios;
- consultar históricos por fecha;
- generar gráficas semanales o quincenales;
- exportar un reporte ejecutivo;
- comparar días;
- detectar ausencias recurrentes;
- evaluar SQLite o PostgreSQL en una etapa posterior.

## 14. Reglas para cambios futuros

1. Leer `DASHBOARD_CONTEXT.md` antes de tocar código.
2. Revisar el código real; este documento orienta, pero el código es la fuente final de verdad.
3. Hacer cambios pequeños y mantener separadas las modificaciones de parser, conteo y diseño.
4. Mantener `APP_VERSION` visible en `app.py` e incrementarla en cada cambio que vaya a desplegarse, para distinguir claramente la versión local, la de GitHub y la de Streamlit Cloud.
5. Probar localmente antes de hacer push.
6. Ejecutar pruebas:

```powershell
python -m unittest discover -s tests -v
```

7. Compilar los módulos principales:

```powershell
python -m py_compile app.py core/catalog.py core/pdf_daily_parser.py core/attendance.py core/export.py core/problem_reporting.py core/query.py
```

8. Ejecutar `git status` antes de preparar archivos.
9. Revisar `git diff` antes del commit.
10. No usar `git add .` si aparecen PDFs, Excels, Secrets, `data/`, reportes o cualquier archivo sensible.
11. No revelar URLs completas en mensajes de error, logs ni capturas.

## 15. Validación base

Después de cada cambio funcional:

- confirmar que los catálogos PAAE y Docentes siguen cargando;
- confirmar que el catálogo unificado conserva ambos tipos de personal;
- probar un PDF con una fecha y otro con varias fechas;
- confirmar que el selector muestra el día de la semana;
- revisar que problemas de cruce aparezcan en tabla sin romper la aplicación;
- ejecutar toda la suite de pruebas;
- compilar los módulos principales;
- verificar `git status` para detectar archivos accidentales o sensibles.
