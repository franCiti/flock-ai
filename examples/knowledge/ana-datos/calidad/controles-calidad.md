# Controles de calidad de datos

Documento ficticio del equipo de Datos.

## Controles automáticos

- **Duplicados:** ninguna factura puede aparecer dos veces en `ventas.fact_ventas`.
- **Montos:** no se aceptan ventas con monto negativo salvo que sean notas de crédito.
- **Volumen:** si un día tiene menos del 50 % de las ventas del promedio de los últimos 7 días, se dispara una alerta.

## Qué pasa cuando un control falla

El control marca el día como "en revisión" y los tableros muestran un aviso. Ana Gómez revisa los
casos en revisión todos los días a las 10:00.
