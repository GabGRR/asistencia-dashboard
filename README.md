# Dashboard de asistencia diaria

Aplicación Streamlit independiente para contar qué personas tienen al menos una checada en una fecha seleccionada. No califica retardos, faltas, salidas ni justificaciones.

## Ejecutar localmente

```powershell
cd C:\Users\Ggame\OneDrive\Documentos\AnalisisChecadas\asistencia_dashboard
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
streamlit run app.py
```

## Catálogos Excel

La aplicación acepta dos fuentes independientes y también funciona si solo se carga una:

- **PAAE:** busca una tabla con `ID`, nombre, apellidos, `HORA ENTRADA` y `HORA SALIDA`. El turno se infiere desde la entrada: antes de las 12:00 es matutino; desde las 12:00 es vespertino.
- **DOCENTES:** lee preferentemente la hoja `DOCENTES 2026-21`, detectando el encabezado aunque la tabla comience varias filas abajo. Usa `No. EMPLEADO`, nombre, apellidos y `TURNO`. Los horarios docentes quedan vacíos por ahora.

Ambas fuentes se normalizan al formato:

`empleado_id`, `nombre_completo`, `apellido_paterno`, `apellido_materno`, `nombre`, `tipo_personal`, `turno`, `hora_entrada`, `hora_salida`, `activo`, `fuente`.

La vista de depuración muestra registros leídos, duplicados por ID, personas sin turno, sin ID y sin nombre.

## Catálogos remotos

En Streamlit Cloud agrega estos secretos sin escribir las URLs en el repositorio:

```toml
PAAE_CATALOG_URL = "URL_PRIVADA_O_COMPARTIDA_DEL_XLSX"
DOCENTES_CATALOG_URL = "URL_PRIVADA_O_COMPARTIDA_DEL_XLSX"
```

En otro hosting también pueden configurarse como variables de entorno con los mismos nombres. La descarga se realiza en memoria y la interfaz no muestra la URL completa. Si una fuente remota falla, el uploader manual permanece disponible como respaldo.

## Regla de asistencia

Una persona queda como `CON_CHECADA` cuando la fila de la fecha seleccionada contiene al menos una hora. Cero horas significa `SIN_CHECADA`. El cruce se hace primero por ID y después por nombre normalizado.

## Privacidad

El PDF y el Excel se leen desde memoria y la aplicación no los guarda en disco. No deben agregarse archivos reales al repositorio.

## Limitaciones del MVP

- Funciona con PDFs que contienen texto seleccionable; no realiza OCR de documentos escaneados.
- El parser está ajustado al formato actual de `Reporte de Tarjeta`.
- Nombres muy distintos entre PDF y catálogo no se cruzan automáticamente.
- Duplicados de ID o nombre se marcan para revisión.
- No se persisten resultados entre sesiones.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Siguiente etapa

Una futura versión puede guardar cada corte diario en SQLite o PostgreSQL con fecha, empleado, estado, checadas y momento de consulta. Eso permitiría históricos, tendencias por grupo, comparaciones quincenales y auditoría de cambios sin alterar este flujo de carga.
