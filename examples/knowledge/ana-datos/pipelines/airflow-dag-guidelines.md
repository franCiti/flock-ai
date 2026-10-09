# Airflow DAG guidelines

Fictional document of the Data team.

## Naming

- DAG ids use snake_case and end with the schedule: `ventas_diario`, `stock_semanal`.
- Every DAG has an owner tag with the team name: `tags=["datos"]`.

## Reliability

- Every task sets `retries=3` and `retry_delay` of 20 minutes.
- Tasks must be idempotent: running a day twice cannot duplicate rows.
- No DAG may run longer than 2 hours: set `dagrun_timeout`.

## Reviews

New DAGs need a review from the Data team before being enabled in production.
