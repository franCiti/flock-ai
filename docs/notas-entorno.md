# Notas del entorno de desarrollo

Aprendizajes del spike inicial (2026-10-09), cuyo código se descartó.
Sirven para no volver a tropezar con lo mismo.

## Inspección HTTPS (intermitente)

**Lo que se vio (mañana del 2026-10-09):** fallaron a la vez descargas de uv
(`invalid peer certificate: UnknownIssuer`), la fuente `msstore` de winget y el arranque de Docker.
Es el comportamiento típico de una red o un antivirus que inspecciona HTTPS con un certificado propio.

**Lo que se comprobó después (tarea T05, mismo día):** no había inspección. 14 sitios (GitHub,
PyPI, Maven, Alpine, Docker Hub, Hugging Face, OpenRouter, Microsoft Store, npm...) presentaban
sus certificados públicos legítimos, el almacén de Windows no tenía raíces de antivirus, proxy o
firewall, y uv descargaba sin `system-certs`.

**Conclusión:** la inspección es **intermitente**; probablemente depende de la red (oficina, VPN)
o del escaneo HTTPS del antivirus. Sin confirmar.

**Confirmado (2026-10-15, T31):** es el **antivirus Avast** ("Web/Mail Shield"). La cadena que recibe
Maven de `repo.maven.apache.org` termina en `CN=Avast Web/Mail Shield Root` (generada por Avast para
el escaneo SSL/TLS). Esa raíz está en el almacén de Windows, no en el de Java.

- **Maven:** falla con `PKIX path building failed`. Defensa: que la JVM de Maven use el almacén de
  Windows. `scripts/run_maven.py` (hooks de pre-commit) lo hace solo; para `./mvnw` a mano:
  `MAVEN_OPTS="-Djavax.net.ssl.trustStoreType=Windows-ROOT" ./mvnw verify`.
- **Java contra Kafka en la PC (`localhost:9093`):** Avast también intercepta ese TLS y reemplaza el
  certificado del broker por uno propio (`Avast Web/Mail Shield Untrusted Root`): **no hay mTLS
  posible desde Java en esta PC** mientras pasa (es intermitente: la misma prueba, horas después,
  pasó sin intercepción). Python (`flock-ask`) y Postgres (TLS dentro de su protocolo) no
  se ven afectados, ni Java dentro de Docker. `MutualTlsStackTest` omite su parte de Kafka con este
  motivo. Para usar la Core API en la PC contra Kafka hace falta una excepción en Avast (para
  `localhost` o para `java.exe`); es una configuración de seguridad del equipo y la decide Francisco.
- **Sockets locales de Java:** dentro de los tests de Maven, el JDK no puede conectar los sockets de
  dominio Unix que usa internamente en la carpeta temporal ("Unable to establish loopback
  connection" al crear un cliente de Kafka). `core-api/pom.xml` los ubica en `target/`
  (`jdk.net.unixdomain.tmpdir`). Probablemente también por el antivirus; sin confirmar.

**Defensas que quedan activas** (no molestan sin inspección y protegen con ella):

| Herramienta | Defensa |
|---|---|
| **uv** | `system-certs = true` en `agent-service/uv.toml` (o `UV_SYSTEM_CERTS=1`) |
| **Python** (requests, httpx, huggingface) | `truststore.inject_into_ssl()` al iniciar (`common/bootstrap.py`) |
| **winget** | usar `--source winget` si la fuente `msstore` falla por certificado |
| **Builds de Docker** | si hay archivos `.crt` en `infra/corp-ca/`, los Dockerfiles los agregan a la lista de confianza (T27); si la carpeta está vacía, no hacen nada |

**Si vuelven los errores de certificado:** identificar el certificado raíz que presenta la red
(conectarse a un sitio como `github.com` y mirar la raíz de la cadena; si no es una CA pública
conocida, es el corporativo), exportarlo desde el almacén de Windows como `.crt` (Base64) a
`infra/corp-ca/` y reconstruir las imágenes. La carpeta está fuera de git.

## Herramientas instaladas

- **Java 21** (Temurin): ya estaba.
- **uv 0.12** (instalado con winget, a nivel usuario) y **Python 3.12.15** (instalado con uv).
  - `uv python install` muestra el error "Missing expected target directory for
    Python minor version link". Es cosmético: Python queda instalado y `uv python find 3.12` lo encuentra.
- **Docker Desktop 4.35.1** con backend WSL 2.

## Docker Desktop: falla al arrancar

**Síntoma:** Docker abre, muestra un diálogo de error y el engine nunca levanta
(`docker info` falla con `open //./pipe/dockerDesktopLinuxEngine`).

**Causa (en `%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log`):**

```
removing stale socket: remove ...\AppData\Local\Docker\run\userAnalyticsOtlpHttp.sock:
The file cannot be accessed by the system.
```

Ese archivo quedó de una sesión anterior y el sistema no deja accederlo; probablemente
lo bloquea el antivirus corporativo (sin confirmar). No se puede borrar, ni siquiera con Docker cerrado.

**Qué funcionó:** volver a abrir Docker Desktop. En el segundo intento arrancó bien,
aunque el archivo sigue ahí.

**Si vuelve a pasar:** reabrir Docker; si no alcanza, reiniciar la PC o actualizar
Docker Desktop (la 4.35.1 es vieja). Si persiste, consultar con IT por el antivirus.

## Embeddings locales

El modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed,
384 dimensiones, multilingüe) se descargó y funcionó en CPU sin API key. Es un candidato
válido para desarrollo, a confirmar en las definiciones técnicas.
