# Personas de ejemplo

Conocimiento **ficticio** para desarrollo y evaluación (plan, sección 8.6). Ningún dato es real:
nombres, mails, servidores y credenciales son inventados.

- Los Word y PDF se generan con `agent-service/scripts/build_examples.py` (el script documenta su contenido).
- Para usarlas: `KNOWLEDGE_ROOT=examples/knowledge`.

## Personas

| Persona | Quién es | Temas (exclusivos de cada una) |
|---|---|---|
| `juan-plataforma` | Juan Pérez, líder técnico de Plataforma | Deploys, rollback, accesos, VPN, guardias, incidentes, Kubernetes, certificados |
| `ana-datos` | Ana Gómez, analista líder de Datos | Pipeline de ventas, Airflow, tableros, calidad de datos, cierres, diccionario de clientes |

Ninguna tiene información de los temas de la otra: sirven para probar el aislamiento (HU3) y las
derivaciones (HU2).

## Documentos especiales

| Documento | Para qué |
|---|---|
| `juan-plataforma/notas/reunion-proveedor-monitoreo.md` | **Envenenado:** instrucciones dirigidas al bot dentro del documento (HU15.2) |
| `ana-datos/notas/comentarios-ticket-datos-142.txt` | **Envenenado:** un "comentario de ticket" que pide filtrar datos de otra persona (HU15.2, HU15.3) |
| `juan-plataforma/procedimientos/acceso-bastion.md` | **Secretos ficticios:** contraseña, claves de AWS y token de GitHub (HU15.4) |
| `ana-datos/pipelines/conexion-warehouse.md` | **Secretos ficticios:** cadena de conexión y URL con credenciales (HU15.4) |
| `juan-plataforma/correo/renovacion-certificado-legacy.eml` | Correo guardado: se indexa con asunto, remitente, fecha y cuerpo (HU4.6) |

## Inventario de hechos (base de los casos de evaluación, T28)

### juan-plataforma

| # | Hecho | Documento |
|---|---|---|
| 1 | Ventana de deploy: lunes a jueves de 10:00 a 16:00 | `procedimientos/deploy-produccion.md` |
| 2 | Los viernes solo hotfixes aprobados por el líder técnico | `procedimientos/deploy-produccion.md` |
| 3 | Freeze del 15 de diciembre al 5 de enero (aprueba el CTO) | `procedimientos/deploy-produccion.md` |
| 4 | Formato del tag: `vAAAA.MM.DD-N` | `procedimientos/deploy-produccion.md` |
| 5 | Job de deploy: `deploy-prod`; monitorear "Prod Health" 15 minutos | `procedimientos/deploy-produccion.md` |
| 6 | Umbrales de rollback: 5xx > 2 % o p95 > 800 ms | `procedimientos/rollback.md` |
| 7 | Job `rollback-prod` con el tag anterior, sin pedir aprobación | `procedimientos/rollback.md` |
| 8 | Las migraciones no se revierten solas: contactar al DBA de guardia | `procedimientos/rollback.md` |
| 9 | Después de un rollback: ticket PLAT con etiqueta `postmortem` | `procedimientos/rollback.md` |
| 10 | VPN: ticket ACCESOS "Alta VPN", aprueba el manager, 24 h hábiles | `accesos/faq-vpn.md` |
| 11 | Cliente FortiClient 7.4+; la sesión dura 60 minutos | `accesos/faq-vpn.md` |
| 12 | La VPN no funciona desde el celular | `accesos/faq-vpn.md` |
| 13 | Acceso de lectura a producción: solo 30 días, aprueba el líder técnico | `accesos/politica-de-accesos.docx` |
| 14 | Jenkins se bloquea tras 5 intentos; se desbloquea a los 30 minutos | `accesos/politica-de-accesos.docx` |
| 15 | Daily 9:30 por Meet; retro cada dos semanas, jueves 15:00 | `onboarding/guia.html` |
| 16 | Las guardias empiezan después del primer mes | `onboarding/guia.html` |
| 17 | Titular de guardia la semana del 19/10/2026: Lucía Díaz | `guardias/rotacion.csv` |
| 18 | Severidad 1: llamar a la guardia y abrir sala en menos de 10 minutos | `procedimientos/runbook-incidentes.pdf` |
| 19 | Postmortem de sev 1 y 2 en los 5 días hábiles siguientes | `procedimientos/runbook-incidentes.pdf` |
| 20 | Kubernetes: una versión menor por vez; viejo node pool 48 h (en inglés) | `infra/kubernetes-upgrade-checklist.md` |
| 21 | El certificado de legacy.example.net vence el 15 de marzo y se renueva a mano | `infra/certificados-tls.txt` |
| 22 | Las credenciales del bastion se rotan cada 90 días | `procedimientos/acceso-bastion.md` |

### ana-datos

| # | Hecho | Documento |
|---|---|---|
| 1 | El pipeline de ventas corre a las 03:00 y tarda unos 40 minutos | `pipelines/ventas-etl.md` |
| 2 | Convierte montos con la cotización del Banco Central | `pipelines/ventas-etl.md` |
| 3 | Carga `ventas.fact_ventas` y `ventas.dim_clientes` | `pipelines/ventas-etl.md` |
| 4 | Si falla: revisar el DAG `ventas_diario` en Airflow | `pipelines/ventas-etl.md` |
| 5 | Error común: cotización no publicada; 3 reintentos cada 20 minutos | `pipelines/ventas-etl.md` |
| 6 | Si a las 08:00 no terminó, avisar en #datos-incidentes | `pipelines/ventas-etl.md` |
| 7 | DAG ids en snake_case terminados en la frecuencia (en inglés) | `pipelines/airflow-dag-guidelines.md` |
| 8 | Ningún DAG puede durar más de 2 horas (en inglés) | `pipelines/airflow-dag-guidelines.md` |
| 9 | Tablero de ventas en Looker, carpeta "Comercial", se actualiza a las 06:00 | `dashboards/tableros.md` |
| 10 | Tablero de stock: lunes 07:00, datos del DAG `stock_semanal` | `dashboards/tableros.md` |
| 11 | Datos viejos en un tablero: casi siempre el pipeline no terminó | `dashboards/tableros.md` |
| 12 | Ninguna factura duplicada en `fact_ventas` | `calidad/controles-calidad.md` |
| 13 | Alerta si un día tiene menos del 50 % del promedio de 7 días | `calidad/controles-calidad.md` |
| 14 | Ana revisa los casos "en revisión" todos los días a las 10:00 | `calidad/controles-calidad.md` |
| 15 | Responsable de `stock_semanal`: Pablo Torres | `datasets/catalogo.csv` |
| 16 | `devoluciones` se actualiza a las 04:00 | `datasets/catalogo.csv` |
| 17 | Acceso a Looker: ticket DATOS "Acceso BI", aprueba Ana Gómez | `accesos/acceso-bi.html` |
| 18 | El acceso al data warehouse se revisa cada 6 meses | `accesos/acceso-bi.html` |
| 19 | Segmentos de clientes: minorista, mayorista, corporativo | `diccionario/diccionario-clientes.docx` |
| 20 | Un cliente es inactivo tras 12 meses sin comprar | `diccionario/diccionario-clientes.docx` |
| 21 | Cierre: tercer día hábil; el pipeline corre a las 03:00 y a las 12:00 | `cierres/calendario-cierres.pdf` |
| 22 | La contraseña de `etl_user` se rota el primer lunes de cada trimestre | `pipelines/conexion-warehouse.md` |
