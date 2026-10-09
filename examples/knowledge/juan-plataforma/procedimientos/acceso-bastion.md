# Acceso al bastion de producción

Documento de ejemplo con secretos a propósito: sirve para probar que se ocultan al indexar
(spec HU15.4). Todos los valores son ficticios.

## Cómo entrar

1. Conectarse a la VPN.
2. Entrar por SSH a bastion.example.internal con el usuario `deploy`.
3. password: Bastion-Example-2026!

## Credenciales de la herramienta de backups

- AWS access key: AKIAIOSFODNN7EXAMPLE
- AWS secret key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
- Token de GitHub para el job de releases: ghp_EXAMPLEtokenEXAMPLEtokenEXAMPLE1234

## Cada cuánto se rotan

Las credenciales del bastion se rotan cada 90 días.
