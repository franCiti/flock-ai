# Deploy a producción

Documento ficticio del equipo de Plataforma. Responsable: Juan Pérez.

## Ventana de deploy

Los deploys a producción se hacen de lunes a jueves, entre las 10:00 y las 16:00 (hora de Buenos Aires).
Los viernes solo se permiten hotfixes aprobados por el líder técnico de Plataforma.
Durante el freeze de fin de año (del 15 de diciembre al 5 de enero) no se deploya nada sin aprobación del CTO.

## Requisitos previos

- El pipeline de CI de la rama `main` tiene que estar en verde.
- El cambio tiene que tener al menos dos aprobaciones en el pull request.
- Si el cambio toca la base de datos, la migración tiene que haberse probado en staging.

## Pasos

1. Crear un tag con el formato `vAAAA.MM.DD-N` (por ejemplo, `v2026.10.09-1`).
2. Ejecutar el job `deploy-prod` en Jenkins pasando el tag como parámetro.
3. Avisar en el canal #plataforma-deploys que empezó el deploy.
4. Monitorear el dashboard "Prod Health" en Grafana durante 15 minutos.
5. Si todo está bien, cerrar el aviso en #plataforma-deploys con el resultado.

## Si algo sale mal

Si la tasa de errores 5xx supera el 2 % o la latencia p95 supera los 800 ms, hay que hacer rollback
(ver el procedimiento de rollback). Primero se revierte y después se analiza.
