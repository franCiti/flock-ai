import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState, type SyntheticEvent } from 'react';
import { fetchAudit, type AuditRecord } from '../../api/audit.ts';
import type { Citation } from '../../api/chat.ts';
import { fetchPersonas } from '../../api/chat.ts';
import { formatDateTime } from '../../components/format.ts';
import { citationLinks } from '../chat/citationLinks.ts';
import { Citations } from '../chat/Citations.tsx';
import { SafeMarkdown } from '../chat/SafeMarkdown.tsx';
import {
  PAGE_SIZE,
  flagLabels,
  noFilters,
  outcomeChips,
  outcomeLabels,
  toQuery,
  type AuditFilters,
} from './auditFilters.ts';
import styles from './AuditPage.module.css';

/** The record of the processed questions, with filters and the detail of each one (spec HU8). */
export function AuditPage() {
  const personas = useQuery({ queryKey: ['personas'], queryFn: fetchPersonas });
  const [form, setForm] = useState<AuditFilters>(noFilters);
  const [filters, setFilters] = useState<AuditFilters>(noFilters);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string>();

  const audit = useQuery({
    queryKey: ['audit', filters, page],
    queryFn: () => fetchAudit(toQuery(filters, page)),
    placeholderData: keepPreviousData,
  });

  const personaName = (id: string | undefined) =>
    personas.data?.find((persona) => persona.id === id)?.displayName ?? id ?? '—';

  const search = (next: AuditFilters) => {
    setFilters(next);
    setPage(0);
    setSelectedId(undefined);
  };

  const handleSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    search(form);
  };

  const set = <K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const items = audit.data?.items ?? [];
  const total = audit.data?.totalItems ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const selected = items.find((item) => item.id === selectedId);

  return (
    <section className={styles.page} aria-labelledby="page-title">
      <h1 id="page-title">Auditoría</h1>

      <form
        className={`panel ${styles.filters ?? ''}`}
        onSubmit={handleSubmit}
        aria-label="Filtros"
      >
        <div className="field">
          <label htmlFor="audit-persona">Persona</label>
          <select
            id="audit-persona"
            value={form.personaId}
            onChange={(event) => {
              set('personaId', event.target.value);
            }}
          >
            <option value="">Todas</option>
            {personas.data?.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.displayName}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="audit-from">Desde</label>
          <input
            id="audit-from"
            type="date"
            value={form.from}
            onChange={(event) => {
              set('from', event.target.value);
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="audit-to">Hasta</label>
          <input
            id="audit-to"
            type="date"
            value={form.to}
            onChange={(event) => {
              set('to', event.target.value);
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="audit-outcome">Resultado</label>
          <select
            id="audit-outcome"
            value={form.outcome}
            onChange={(event) => {
              set('outcome', event.target.value as AuditFilters['outcome']);
            }}
          >
            <option value="">Todos</option>
            {Object.entries(outcomeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="audit-flag">Marca</label>
          <select
            id="audit-flag"
            value={form.flag}
            onChange={(event) => {
              set('flag', event.target.value as AuditFilters['flag']);
            }}
          >
            <option value="">Todas</option>
            <option value="rejected">Pedidos rechazados</option>
            {Object.entries(flagLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={form.referredOnly}
            onChange={(event) => {
              set('referredOnly', event.target.checked);
            }}
          />
          Solo con derivación
        </label>
        <div className={styles.actions}>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              setForm(noFilters);
              search(noFilters);
            }}
          >
            Limpiar
          </button>
          <button type="submit" className="button button-primary">
            Buscar
          </button>
        </div>
      </form>

      {audit.isError ? (
        <p role="alert" className={styles.alert}>
          No se pudo cargar el registro.
        </p>
      ) : null}
      {audit.isPending ? <p className={styles.muted}>Cargando…</p> : null}
      {audit.isSuccess && items.length === 0 ? (
        <p className={styles.muted}>No hay preguntas registradas con estos filtros.</p>
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Persona</th>
                  <th>Pregunta</th>
                  <th>Resultado</th>
                  <th>Marcas</th>
                  <th>Derivación</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={item.id === selectedId ? styles.selected : undefined}
                  >
                    <td className="nowrap">{formatDateTime(item.createdAt)}</td>
                    <td className="nowrap">{personaName(item.personaId)}</td>
                    <td className={styles.question}>
                      <button
                        type="button"
                        className={styles.rowButton}
                        onClick={() => {
                          setSelectedId(item.id);
                        }}
                      >
                        {item.question ?? '—'}
                      </button>
                    </td>
                    <td>
                      <OutcomeChip record={item} />
                    </td>
                    <td>
                      <Flags record={item} />
                    </td>
                    <td className="nowrap">
                      {item.referralPersonaId ? personaName(item.referralPersonaId) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className={styles.pager} aria-label="Páginas">
            <button
              type="button"
              className="button button-ghost"
              disabled={page === 0}
              onClick={() => {
                setPage(page - 1);
              }}
            >
              Anterior
            </button>
            <span>
              Página {page + 1} de {pages} · {total} preguntas
            </span>
            <button
              type="button"
              className="button button-ghost"
              disabled={page + 1 >= pages}
              onClick={() => {
                setPage(page + 1);
              }}
            >
              Siguiente
            </button>
          </nav>
        </>
      ) : null}

      {selected === undefined ? null : (
        <AuditDetail
          record={selected}
          personaName={personaName}
          onClose={() => {
            setSelectedId(undefined);
          }}
        />
      )}
    </section>
  );
}

function OutcomeChip({ record }: { record: AuditRecord }) {
  if (record.outcome === undefined) {
    return <>—</>;
  }
  return (
    <span className={`chip ${outcomeChips[record.outcome]}`}>{outcomeLabels[record.outcome]}</span>
  );
}

function Flags({ record }: { record: AuditRecord }) {
  const flags = record.flags ?? [];
  if (flags.length === 0) {
    return <>—</>;
  }
  return (
    <span className={styles.flags}>
      {flags.map((flag) => (
        <span key={flag} className="chip chip-blocked">
          {flagLabels[flag]}
        </span>
      ))}
    </span>
  );
}

function AuditDetail({
  record,
  personaName,
  onClose,
}: {
  record: AuditRecord;
  personaName: (id: string | undefined) => string;
  onClose: () => void;
}) {
  const citations: Citation[] = (record.citations ?? []).map((citation) => ({
    documentId: citation.documentId ?? '',
    title: citation.title ?? citation.path ?? '',
    url: citation.url ?? null,
    path: citation.path ?? null,
    section: citation.section ?? null,
    sourceType: citation.sourceType ?? 'file',
  }));
  return (
    <article className={`panel ${styles.detail ?? ''}`} aria-labelledby="audit-detail-title">
      <header className={styles.detailHeader}>
        <h2 id="audit-detail-title">Detalle</h2>
        <button type="button" className="button button-ghost" onClick={onClose}>
          Cerrar
        </button>
      </header>
      <dl className={styles.facts}>
        <dt>Fecha</dt>
        <dd>{formatDateTime(record.createdAt)}</dd>
        <dt>Persona</dt>
        <dd>{personaName(record.personaId)}</dd>
        <dt>Resultado</dt>
        <dd>
          <OutcomeChip record={record} /> {record.errorCode ? `(${record.errorCode})` : null}
        </dd>
        <dt>Marcas</dt>
        <dd>
          <Flags record={record} />
        </dd>
        <dt>Derivación</dt>
        <dd>{record.referralPersonaId ? personaName(record.referralPersonaId) : '—'}</dd>
        <dt>App cliente</dt>
        <dd>{record.clientId ?? '—'}</dd>
        <dt>Conversación</dt>
        <dd className={styles.mono}>{record.conversationId ?? '—'}</dd>
        <dt>Modelo</dt>
        <dd className={styles.mono}>
          {record.llmModel ?? '—'}
          {record.promptVersion ? ` · prompt ${record.promptVersion}` : ''}
        </dd>
        <dt>Tiempos</dt>
        <dd className={styles.mono}>
          primer fragmento {formatMs(record.firstTokenMs)} · total {formatMs(record.totalMs)}
        </dd>
      </dl>
      <h3 className={styles.label}>Pregunta</h3>
      <p className={styles.text}>{record.question ?? '—'}</p>
      <h3 className={styles.label}>Respuesta</h3>
      {record.answer ? (
        <div className={styles.answer}>
          <SafeMarkdown text={record.answer} links={citationLinks(citations)} />
        </div>
      ) : (
        <p className={styles.text}>—</p>
      )}
      <Citations citations={citations} />
    </article>
  );
}

/** The Core API sends null for a missing time (e.g. no token before an error). */
function formatMs(ms: number | undefined): string {
  return typeof ms === 'number' ? `${(ms / 1000).toFixed(1)} s` : '—';
}
