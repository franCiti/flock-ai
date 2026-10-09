# Notas del entorno de desarrollo

Aprendizajes del spike inicial (2026-10-09), cuyo código se descartó.
Sirven para no volver a tropezar con lo mismo.

## Red corporativa (proxy con inspección HTTPS)

La red inspecciona el tráfico HTTPS con un certificado propio. Las herramientas
que traen su propio almacén de certificados fallan con errores como
`invalid peer certificate: UnknownIssuer`.

| Herramienta | Solución |
|---|---|
| **uv** | `system-certs = true` en `uv.toml` (o la variable `UV_SYSTEM_CERTS=1`) |
| **Python** (requests, httpx, huggingface) | paquete `truststore` y `truststore.inject_into_ssl()` al iniciar |
| **winget** | usar `--source winget`: la fuente `msstore` falla por certificado |
| **Docker** | descargar imágenes funciona sin configuración extra (probado con `hello-world`) |

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
