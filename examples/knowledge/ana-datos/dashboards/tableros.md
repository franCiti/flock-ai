# Tableros comerciales

Documento ficticio del equipo de Datos.

## Tablero de ventas diarias

Está en Looker, carpeta "Comercial". Se actualiza a las 06:00, después del pipeline de ventas.
Muestra ventas por sucursal, por producto y contra el objetivo mensual.

## Tablero de stock

Se actualiza los lunes a las 07:00. Los datos de stock vienen del DAG `stock_semanal`.

## ¿Por qué un tablero muestra datos viejos?

Casi siempre es porque el pipeline de la noche no terminó. Ver el estado en Airflow antes de abrir un ticket.
