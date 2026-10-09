# flock-ai — guía para Claude Code

Bot que responde con el conocimiento de un empleado (persona virtual): RAG sobre sus documentos,
agente en Python con LangGraph, contrato público por Kafka, app Java + front React como cliente.

## Documentos de referencia

| Documento | Para qué |
|---|---|
| `specs/001-bot-respuestas/spec.md` | Qué hace el sistema (aprobada) |
| `specs/001-bot-respuestas/plan.md` | Cómo se construye (aprobado) |
| `specs/001-bot-respuestas/tasks.md` | Backlog y estado de cada tarea |
| `docs/decisiones.md` | Decisiones técnicas (Dxx) y su motivo |
| `docs/arquitectura.md` | Vista general |
| `docs/notas-entorno.md` | Proxy corporativo, Docker y otras particularidades de esta PC |

## Reglas del proyecto

### Idiomas (D02)
- Conversación, specs y documentación: **español**.
- Todo el código: **inglés** (identificadores, comentarios, docstrings, logs, configuración, mensajes de commit).
- Los textos que ve el usuario final (interfaz web, `messages.yaml`) están en español.

### Forma de trabajo (SDD, D01)
- Se implementan las tareas de `tasks.md` **de a una**, en orden y respetando dependencias.
- Al terminar una tarea: mostrar el resultado y **esperar el OK** antes de empezar la siguiente.
- Si aparece una decisión o un cambio de diseño que el plan no cubre: frenar, acordarlo y
  actualizar spec, plan o decisiones antes de seguir.
- Cada tarea termina con linters y tests en verde y **un commit propio**. Los commits son locales:
  **nunca hacer push** (lo hace Francisco).
- Marcar el estado en `tasks.md`: `[ ]` pendiente · `[~]` en curso · `[x]` terminada.

### Calidad (D03)
- Todo el código pasa los linters: `pre-commit run --all-files`.
- Python: Ruff + mypy estricto · Java: Spotless + Checkstyle · TypeScript: ESLint + Prettier + `tsc` estricto.
- No desactivar reglas para que algo pase; si una regla no aplica, justificarlo en un comentario.

### Secretos y costos
- Nunca pedir ni escribir secretos en el chat, el código o git: van en `.env` (ignorado por git).
- La API key de OpenRouter solo se usa en las tareas de **cierre de etapa** (D41). Los tests usan un LLM falso.

## Comandos

| Qué | Comando |
|---|---|
| Linters | `pre-commit run --all-files` |
| Linters + tests de todo | `scripts/check.sh` |

## Entorno

- Windows 11, con Git Bash y PowerShell. Python se gestiona con **uv**; Docker Desktop con WSL 2.
- La red inspecciona HTTPS: ver `docs/notas-entorno.md` antes de pelear con errores de certificados.
