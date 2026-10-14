# Certificado raíz corporativo (opcional)

Si la red inspecciona HTTPS, los builds de las imágenes no pueden descargar dependencias. En ese
caso se exporta acá el certificado raíz que presenta la red, como `.crt` en Base64, y se
reconstruyen las imágenes (plan 7.8). El procedimiento está en `docs/notas-entorno.md`.

Los Dockerfiles agregan a su lista de confianza **todos** los `.crt` de esta carpeta; si no hay
ninguno, no cambian nada. Los `.crt` no se suben a git (`.gitignore`).
