# Cierre de la etapa 1 (T29)

Fecha: 2026-10-14. Alcance de la etapa (plan 9.1): contrato, infraestructura con mTLS, ingesta de
carpetas (con secretos ocultos y correos), Agent Worker completo, auditoría y cliente `flock-ask`.

## Resultado

| Qué | Resultado |
|---|---|
| Tests de `agent-service` | 558 en verde (unitarios, integración con Testcontainers y mTLS contra Docker Compose) |
| Prueba de humo (`scripts/smoke.sh`) con LLM real | **En verde** con `nvidia/nemotron-3-super-120b-a12b:free` |
| Evaluación de calidad con LLM real | **Pendiente** (ver más abajo) |
| Evaluación con el LLM falso | Corre completa: 51 casos, verifica la mecánica (19/51, esperable) |
| `REFERRAL_MIN_SCORE` | Calibrado en **0,40** |

## Prueba de humo

`scripts/smoke.sh` levanta todo con Docker Compose, ingesta `examples/knowledge` y le pregunta a
`juan-plataforma` "¿Cómo hago rollback de un deploy?" con `flock-ask` (certificado `cli`).

Con `nvidia/nemotron-3-super-120b-a12b:free` (cuenta gratuita de OpenRouter):
- Respuesta correcta y completa, solo con información de la base, con 3 citas a las secciones de
  `procedimientos/rollback.md` (cómo hacerlo, migraciones, cuándo hacerlo).
- Primer fragmento: **16,5 s**; total: 18,1 s. Por encima del objetivo de 10 s (informativo): es un
  modelo gratuito compartido; hay que volver a medirlo con el modelo definitivo.
- `google/gemma-4-31b-it:free` respondió 429: el proveedor limita el uso compartido de los modelos
  gratuitos. El agente lo informó bien como `LLM_UNAVAILABLE` (reintentable).

## Calibración de `REFERRAL_MIN_SCORE`

Con `agent-service/scripts/calibrate_referral.py` (solo embeddings, sin LLM): similitud del mejor
fragmento de otra persona para las preguntas que deben derivar y las que no.

| Grupo | Casos | Similitud |
|---|---|---|
| Deben derivar | referral y partial (6) | 0,43 – 0,76 |
| No deben derivar | no_information y out_of_scope (6) | 0,14 – 0,52 |

Los grupos se superponen por un caso ("¿cuántos días de vacaciones me corresponden?", 0,52). Con
**0,40** pasan todas las derivaciones correctas y se descartan 5 de los 6 casos sin llamar al LLM;
el restante lo decide la confirmación del LLM (`find_referral`). Repetir la calibración en cada
cierre de etapa.

## Lo que queda pendiente (acordado)

La **evaluación de calidad con un LLM real** (`flock-eval`, criterios ≥ 80 %, 100 %, 100 %) no se
corrió: la cuenta de OpenRouter es gratuita y sin créditos, y permite 50 pedidos por día a modelos
`:free` (20 por minuto). Una corrida son ~250 pedidos por modelo (51 casos × ~5 llamadas).

Para hacerla, cualquiera de estas opciones:
1. **Cargar US$ 10 una vez** en OpenRouter: el límite de los modelos `:free` sube a 1.000 por día
   (y los créditos quedan disponibles para modelos pagos). Permite comparar 2–3 modelos en un día.
2. **Repartirla en varios días** con la cuenta gratuita (~10 casos por día con `--case`).

Hasta entonces, `LLM_MODEL` provisorio: `nvidia/nemotron-3-super-120b-a12b:free`.

**Privacidad (D08):** muchos proveedores de modelos gratuitos guardan los prompts o los usan para
entrenar. Sirve para las personas ficticias; antes de cargar conocimiento real hay que usar un modelo
y una configuración de cuenta que no registren ni entrenen con los datos.

## Hallazgos y correcciones del cierre

- Un error de cuenta de OpenRouter (401, 402 sin créditos, 403) se informaba como `INTERNAL_ERROR`;
  ahora es `LLM_UNAVAILABLE` (reintentable), como un LLM caído.
