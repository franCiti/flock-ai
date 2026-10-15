# Cierre de la etapa 2 (T45)

Fecha: 2026-10-15. Alcance de la etapa (plan 9.1): Core API (login, chat por Kafka con SSE, copias de
lectura, actualizaciones programadas y manuales, auditoría, documentación publicada), front (chat con
streaming y cuenta regresiva, actualizaciones, auditoría) e imágenes de `core-api` y `web`.

## Resultado

| Qué | Resultado |
|---|---|
| Prueba de humo (`scripts/smoke.sh`) con LLM real | **En verde**: `flock-ask` y la web en `http://localhost:8080` |
| Demo en el navegador | Recorrida completa en `http://localhost:8080` (ver más abajo) |
| Evaluación de calidad con LLM real | **Sigue pendiente**, como en el cierre de la etapa 1 (ver más abajo) |
| Tests (`scripts/check.sh`) | En verde: 564 de `agent-service`, 105 de `core-api`, 51 de `web`, y los linters |

## Prueba de humo

`scripts/smoke.sh` levanta todo con Docker Compose, ingesta `examples/knowledge` y le pregunta a
`juan-plataforma` "¿Cómo hago rollback de un deploy?" con `flock-ask`. Desde esta etapa sigue con
`scripts/smoke-web.mjs`, que hace lo mismo que un navegador contra el nginx de la web:

- el front responde en cualquier ruta y trae su Content-Security-Policy;
- `/docs/`, Swagger UI y la documentación AsyncAPI se ven sin sesión;
- login con el usuario inicial de `.env`, sesión abierta, personas y configuración;
- una pregunta por el chat: el stream SSE recibe `accepted`, los `token` y el `final` con
  `answered` y la cita a `procedimientos/rollback.md`;
- "Actualizar ahora": la corrida se completa con las dos personas de ejemplo;
- la pregunta aparece en la auditoría con su resultado y sus fuentes;
- logout y sesión cerrada.

Con `nvidia/nemotron-3-super-120b-a12b:free`, la última corrida completa quedó en verde: por
`flock-ask`, primer fragmento a los 24,3 s y respuesta completa a los 27,9 s; por la web, 34,0 s y
38,1 s. Muy por encima del objetivo de 10 s (informativo): es un modelo gratuito compartido; hay que
medir con el modelo definitivo. Las dos corridas anteriores fallaron en la cita de la web por las
marcas de cita del modelo (ver "Hallazgos").

## Demo en el navegador

Recorrida en `http://localhost:8080` (y en el servidor de desarrollo de Vite) contra el stack:
- login, logout y volver a entrar;
- chat con las dos personas: cuenta regresiva, respuesta progresiva en Markdown, fuentes con su
  sección, derivación ("Preguntale a Juan Pérez"), conversación nueva;
- actualizaciones: historial con las corridas programadas y manuales y su detalle por persona;
- auditoría: filtros, paginación y detalle (incluido un error `LLM_UNAVAILABLE` de un modelo que
  respondió 429);
- vista en celular (375 px) de la pantalla de actualizaciones;
- sin violaciones de la CSP en la consola.

## Lo que queda pendiente

- **Evaluación de calidad con un LLM real** (`flock-eval`, criterios ≥ 80 %, 100 %, 100 %): la cuenta
  de OpenRouter sigue siendo gratuita (50 pedidos por día) y una corrida necesita ~250. Las opciones
  son las de `docs/cierre-etapa-1.md`. Esta etapa no cambió el grafo del agente salvo la lectura de
  las marcas de cita (ver abajo), así que la evaluación de la etapa 1 sigue siendo la referencia.
- **"Sin cambios" en el resumen de una actualización** sale en 0 cuando nada cambió: el conector de
  carpetas no recorre los archivos sin cambios (HU4.5 pide contarlos). Quedó como tarea aparte.
- **`data/knowledge` vacía:** sin `KNOWLEDGE_HOST_DIR` en `.env`, el Ingestion Worker monta
  `data/knowledge`; si está vacía, la próxima actualización programada borra las personas. Para la
  demo con los ejemplos: `KNOWLEDGE_HOST_DIR=../examples/knowledge` en `.env` (`smoke.sh` ya lo fija).
- **Respuestas con una "leyenda" de citas** al final ("[1] para los pasos 1-4…"): el modelo gratuito
  la agrega a veces. Es tema del prompt; revisarlo con el modelo definitivo.

## Hallazgos y correcciones del cierre

- **Marcas de cita en otros formatos:** el modelo gratuito escribió las marcas como `\[1\]` en una
  corrida y como `【1】` en otra, y las respuestas llegaron sin fuentes. El agente ahora las lee igual
  que `[1]`, también con corchetes de ancho completo (`finalize.py`, con tests). Conviene repetir la
  revisión con el modelo definitivo: otros modelos pueden tener otros hábitos.
- **Volver a entrar después de cerrar sesión** daba 403: el logout borra la cookie CSRF y el login no
  pedía una nueva. Arreglado en T44 (`login()` la pide si falta; los tests simulan el CSRF de Spring).
- **Campos vacíos de la API:** la Core API manda `null` donde el OpenAPI dice "opcional"; la pantalla
  de auditoría mostraba "0.0 s" en un tiempo vacío. Arreglado en T43.
