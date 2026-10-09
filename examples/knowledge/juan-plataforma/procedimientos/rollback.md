# Rollback de un deploy

Documento ficticio del equipo de Plataforma.

## Cuándo hacer rollback

- Tasa de errores 5xx mayor al 2 % durante más de 3 minutos.
- Latencia p95 mayor a 800 ms.
- Cualquier error que impida a los usuarios iniciar sesión.

No hace falta pedir aprobación para un rollback: primero se revierte y después se avisa.

## Cómo hacerlo

1. Ejecutar el job `rollback-prod` en Jenkins con el tag del deploy anterior.
2. Verificar en Grafana que la tasa de errores vuelve a la normalidad en menos de 5 minutos.
3. Avisar en #plataforma-incidentes con el tag revertido y el motivo.
4. Abrir un ticket en el proyecto PLAT con la etiqueta `postmortem`.

## Rollback de migraciones de base de datos

Las migraciones no se revierten automáticamente. Si el deploy incluía una migración, hay que
contactar al DBA de guardia antes de ejecutar `rollback-prod`.
