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

## Cómo retomar el trabajo

1. Leer el **estado** en `specs/001-bot-respuestas/tasks.md` (`[x]` hechas, `[~]` en curso, `[ ]` pendientes)
   y `git log --oneline` (un commit por tarea, con el id de la tarea en el mensaje).
2. Seguir con la próxima tarea pendiente respetando sus dependencias, salvo que Francisco indique otra.
3. Antes de escribir código: releer la sección del plan que cita la tarea y las decisiones que aplica.

**Desvíos acordados que hay que tener presentes** (detalle en la nota de T18 en `tasks.md`):

- **T12 (ocultar secretos) y T14 (correos) quedaron pendientes** a pedido; la T18 se hizo antes.
  Son puntos de extensión marcados `TODO(T12)` (`knowledge/redaction.py`, hoy no oculta nada) y
  `TODO(T14)` (los `.eml`/`.msg` se omiten). Mientras falte T12, **no cargar conocimiento real**.
- Tests de integración (plan 8.1): `integration_stack` contra Docker Compose (mTLS real) y
  `integration_containers` con Testcontainers (lógica sobre tablas).

## Entorno

- Windows 11, con Git Bash y PowerShell. Python se gestiona con **uv**; Docker Desktop con WSL 2.
- La red puede inspeccionar HTTPS de forma intermitente: ante errores de certificados, ver
  `docs/notas-entorno.md` antes de cambiar código.

### Particularidades para Claude Code en esta PC

- **uv no está en el PATH de Git Bash** (se instaló con winget después de abrir la sesión). En Bash:
  `export PATH="/c/Users/FranciscoNeyrotte/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:$PATH"`.
  En PowerShell: `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`.
  Los hooks de pre-commit (Ruff, mypy) necesitan uv en el PATH del proceso que hace el commit.
- **pre-commit** está en `C:\Users\FranciscoNeyrotte\.local\bin\pre-commit.exe` (instalado con `uv tool install`).
- **Nunca editar archivos con `Set-Content`/`Out-File` de PowerShell 5.1**: agregan BOM. Usar las
  herramientas de edición o `sed`/Python con `newline="\n"`. El hook `fix-byte-order-marker` lo detecta.
- **Entorno de Docker Compose:** `docker compose up -d --wait` desde la raíz (Postgres en `5433`, Kafka
  en `9093`). Verificaciones: `infra/postgres/check.sh`, `infra/kafka/check.sh`. Detalle en `infra/README.md`.
- **Comandos de calidad:** `cd agent-service && uv run pytest` (incluye Testcontainers; necesita Docker),
  `uv run ruff check`, `uv run mypy`; Java: `cd core-api && ./mvnw verify` (Maven Wrapper, no hace
  falta Maven instalado); todo junto: `pre-commit run --all-files`.
- **Hooks de Java:** Spotless y Checkstyle corren vía `scripts/run_maven.py` (en Windows, `bash` es el
  de WSL y `sh` no está en el PATH, así que pre-commit no puede lanzar `mvnw` directamente).
- **Commits:** agregar solo los archivos de la tarea (`git add <rutas>`), nunca `git add -A`: puede
  haber otra sesión trabajando en el mismo árbol.
- **Código generado:** los modelos del contrato (`flock_agent/contracts/generated/`) se regeneran con
  `uv run python scripts/generate_contracts.py`; un test falla si quedan desactualizados.
- **Ingesta manual contra el entorno:** ver `agent-service/README.md` (`flock-ingest run`).
