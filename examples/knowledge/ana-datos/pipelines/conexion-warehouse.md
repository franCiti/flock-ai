# Conexión al data warehouse para los pipelines

Documento de ejemplo con secretos a propósito: sirve para probar que se ocultan al indexar
(spec HU15.4). Todos los valores son ficticios.

## Cadena de conexión del usuario de los pipelines

Server=dwh.example.internal;Database=ventas;User Id=etl_user;Password=Dwh-Example-2026;

## URL para herramientas de línea de comandos

postgresql://etl_user:Dwh-Example-2026@dwh.example.internal:5432/ventas

## Rotación

La contraseña del usuario `etl_user` se rota el primer lunes de cada trimestre.
