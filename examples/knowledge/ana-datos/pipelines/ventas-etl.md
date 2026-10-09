# Pipeline de datos de ventas

Documento ficticio del equipo de Datos. Responsable: Ana Gómez.

## Qué hace

Toma las ventas del ERP, las limpia y las carga en el data warehouse, en el esquema `ventas`.
Corre todos los días a las 03:00 y tarda unos 40 minutos.

## Etapas

1. **Extracción:** lee la tabla `facturas` del ERP con un corte por fecha de modificación.
2. **Transformación:** convierte los montos a pesos usando la cotización del día del Banco Central.
3. **Carga:** inserta en `ventas.fact_ventas` y actualiza `ventas.dim_clientes`.

## Si el pipeline falla

- Revisar el DAG `ventas_diario` en Airflow: el log de la tarea que falló dice el motivo.
- El error más común es que la cotización del día no esté publicada: la tarea reintenta 3 veces cada 20 minutos.
- Si a las 08:00 no terminó, avisar en #datos-incidentes, porque los tableros comerciales muestran datos del día anterior.
