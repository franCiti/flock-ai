# Kubernetes cluster upgrade checklist

Fictional document of the Platform team.

## Before the upgrade

- Upgrades are done one minor version at a time (for example 1.30 to 1.31, never 1.30 to 1.32).
- Check deprecated APIs with the `pluto` tool against every Helm release.
- Announce the maintenance window in #plataforma-anuncios at least 3 business days before.

## During the upgrade

1. Upgrade the control plane first, then the node pools one by one.
2. Drain each node with a 10 minute timeout.
3. Keep at least 2 replicas of every critical service during the drain.

## After the upgrade

Run the smoke tests job `k8s-smoke` and keep the old node pool for 48 hours before deleting it.
