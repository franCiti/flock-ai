# core-api

Backend Java de flock-ai: API REST para el front y cliente Kafka del agente. Ver la sección 1.4 del
[plan](../specs/001-bot-respuestas/plan.md).

Java 21, Spring Boot y Maven. No hace falta tener Maven instalado: se usa el **Maven Wrapper**
(`./mvnw` en Git Bash, Linux o macOS; `mvnw.cmd` en PowerShell), que lo descarga la primera vez.

## Comandos

| Qué | Comando |
|---|---|
| Build, linters y tests | `./mvnw verify` |
| Formatear el código | `./mvnw spotless:apply` |
| Solo Checkstyle | `./mvnw checkstyle:check` |
| Levantar la app | `./mvnw spring-boot:run` |

Con la app levantada: `http://localhost:8080/actuator/health`, `http://localhost:8080/docs/swagger-ui`
y `http://localhost:8080/docs/openapi`.

## Calidad

- **Spotless** con palantir-java-format (4 espacios). `verify` falla si el código no está formateado.
- **Checkstyle** (`checkstyle.xml`): nombres, imports y buenas prácticas; no repite lo que resuelve el formateador.
- Los dos corren también como hooks de `pre-commit` (vía `scripts/run_maven.py`).

## Clases del contrato (D42)

El paquete `contract` tiene los records de los mensajes de Kafka, escritos a mano a partir de
`contracts/schemas`. `ContractTest` los compara con el contrato en cada build: ida y vuelta de cada
ejemplo de `contracts/examples`, validación contra el JSON Schema, propiedades de cada record y
valores de los enums. Si se cambia el contrato, hay que actualizar los records hasta que ese test pase.
