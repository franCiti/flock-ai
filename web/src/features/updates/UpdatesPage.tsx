import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchRuns,
  requestUpdate,
  type IngestionRun,
  type PersonaSummary,
} from '../../api/ingestion.ts';
import { formatDateTime } from '../../components/format.ts';
import styles from './UpdatesPage.module.css';

/** While an update is in progress the history is read again this often. */
export const ACTIVE_REFRESH_MS = 3_000;

const runsKey = ['ingestion-runs'] as const;

const statuses: Record<string, { label: string; chip: string }> = {
  requested: { label: 'Pedida', chip: 'chip-pending' },
  running: { label: 'En curso', chip: 'chip-progress' },
  completed: { label: 'Completada', chip: 'chip-completed' },
  failed: { label: 'Falló', chip: 'chip-blocked' },
  rejected: { label: 'Rechazada', chip: 'chip-blocked' },
};

const triggers: Record<string, string> = { manual: 'Manual', scheduled: 'Programada' };

function isActive(run: IngestionRun): boolean {
  return run.status === 'requested' || run.status === 'running';
}

/** Knowledge updates: manual trigger and history with the summary of each one (spec HU4, plan 6.6). */
export function UpdatesPage() {
  const queryClient = useQueryClient();
  const runs = useQuery({
    queryKey: runsKey,
    queryFn: () => fetchRuns(),
    refetchInterval: (query) =>
      query.state.data?.some(isActive) === true ? ACTIVE_REFRESH_MS : false,
  });
  const update = useMutation({
    mutationFn: requestUpdate,
    onSettled: () => queryClient.invalidateQueries({ queryKey: runsKey }),
  });

  const inProgress = runs.data?.some(isActive) === true;

  return (
    <section className={styles.page} aria-labelledby="page-title">
      <header className={styles.header}>
        <div>
          <h1 id="page-title">Actualizaciones</h1>
          <p className={styles.lead}>
            El conocimiento se actualiza solo cada cierto tiempo; también se puede pedir ahora.
          </p>
        </div>
        <button
          type="button"
          className="button button-primary"
          onClick={() => {
            update.mutate();
          }}
          disabled={update.isPending || inProgress}
        >
          {inProgress ? 'Actualización en curso…' : 'Actualizar ahora'}
        </button>
      </header>

      {update.isError ? (
        <p role="alert" className={styles.alert}>
          No se pudo pedir la actualización. Probá de nuevo en unos minutos.
        </p>
      ) : null}
      {update.isSuccess ? (
        <p role="status" className={styles.notice}>
          Actualización pedida: su avance aparece en el historial.
        </p>
      ) : null}

      <h2 className={styles.subtitle}>Historial</h2>
      {runs.isPending ? <p className={styles.muted}>Cargando…</p> : null}
      {runs.isError ? (
        <p role="alert" className={styles.alert}>
          No se pudo cargar el historial.
        </p>
      ) : null}
      {runs.data?.length === 0 ? (
        <p className={styles.muted}>Todavía no hubo actualizaciones.</p>
      ) : null}
      {runs.data !== undefined && runs.data.length > 0 ? <RunsTable runs={runs.data} /> : null}
    </section>
  );
}

function RunsTable({ runs }: { runs: IngestionRun[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Origen</th>
            <th>Estado</th>
            <th className="number">Personas</th>
            <th className="number">Agregados</th>
            <th className="number">Modificados</th>
            <th className="number">Borrados</th>
            <th className="number">Sin cambios</th>
            <th className="number">Omitidos</th>
            <th className="number">Datos ocultos</th>
          </tr>
        </thead>
        {runs.map((run, index) => (
          <RunRows key={run.jobId ?? String(index)} run={run} />
        ))}
      </table>
    </div>
  );
}

function RunRows({ run }: { run: IngestionRun }) {
  const status = statuses[run.status ?? ''] ?? { label: run.status ?? '—', chip: 'chip-pending' };
  const totals = run.totals;
  const hasDetail =
    (run.personas?.length ?? 0) > 0 ||
    (run.removedPersonas?.length ?? 0) > 0 ||
    Boolean(run.reason);
  return (
    // One tbody per run: the summary row and its detail.
    <tbody>
      <tr>
        <td className="nowrap">{formatDateTime(run.requestedAt ?? run.startedAt)}</td>
        <td>{triggers[run.trigger ?? ''] ?? run.trigger}</td>
        <td>
          <span className={`chip ${status.chip}`}>{status.label}</span>
        </td>
        <td className="number">{totals?.personas ?? '—'}</td>
        <td className="number">{totals?.added ?? '—'}</td>
        <td className="number">{totals?.modified ?? '—'}</td>
        <td className="number">{totals?.deleted ?? '—'}</td>
        <td className="number">{totals?.unchanged ?? '—'}</td>
        <td className="number">{totals?.skipped ?? '—'}</td>
        <td className="number">{totals?.secretsMasked ?? '—'}</td>
      </tr>
      {hasDetail ? (
        <tr className={styles.detailRow}>
          <td colSpan={10}>
            <details>
              <summary>Detalle</summary>
              <RunDetail run={run} />
            </details>
          </td>
        </tr>
      ) : null}
    </tbody>
  );
}

function RunDetail({ run }: { run: IngestionRun }) {
  return (
    <div className={styles.detail}>
      {run.reason ? <p className={styles.reason}>Motivo: {run.reason}</p> : null}
      {run.personas?.map((persona) => (
        <PersonaDetail key={persona.personaId} persona={persona} />
      ))}
      {(run.removedPersonas?.length ?? 0) > 0 ? (
        <p>Personas quitadas (ya no tienen carpeta): {run.removedPersonas?.join(', ')}</p>
      ) : null}
    </div>
  );
}

function PersonaDetail({ persona }: { persona: PersonaSummary }) {
  const skipped = persona.skipped ?? [];
  const sourceErrors = persona.sourceErrors ?? [];
  return (
    <div className={styles.persona}>
      <h3>{persona.displayName ?? persona.personaId}</h3>
      <p className={styles.counts}>
        {persona.added ?? 0} agregados · {persona.modified ?? 0} modificados ·{' '}
        {persona.deleted ?? 0} borrados · {persona.unchanged ?? 0} sin cambios · {skipped.length}{' '}
        omitidos · {persona.secretsMasked ?? 0} datos ocultos
      </p>
      {skipped.length > 0 ? (
        <ul aria-label={`Omitidos de ${persona.displayName ?? persona.personaId ?? ''}`}>
          {skipped.map((file) => (
            <li key={file.path}>
              <span className={styles.path}>{file.path}</span>: {file.reason}
            </li>
          ))}
        </ul>
      ) : null}
      {sourceErrors.map((error) => (
        <p key={error.sourceId} className={styles.reason}>
          No se pudo leer la fuente {error.sourceId}: {error.reason}
        </p>
      ))}
    </div>
  );
}
