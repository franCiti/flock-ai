import { screen, within } from '@testing-library/react';
import type { IngestionRun } from '../../api/ingestion.ts';
import { renderApp } from '../../test/renderApp.tsx';
import { mockAuthApi, mockIngestionApi } from '../../test/server.ts';

const completed: IngestionRun = {
  jobId: 'job-a',
  trigger: 'scheduled',
  status: 'completed',
  requestedAt: '2026-10-15T14:30:00Z',
  startedAt: '2026-10-15T14:30:01Z',
  finishedAt: '2026-10-15T14:30:40Z',
  totals: {
    personas: 2,
    added: 3,
    modified: 1,
    deleted: 2,
    unchanged: 17,
    skipped: 1,
    secretsMasked: 4,
    sourceErrors: 0,
  },
  personas: [
    {
      personaId: 'ana-datos',
      displayName: 'Ana Gómez',
      added: 3,
      modified: 1,
      deleted: 2,
      unchanged: 9,
      secretsMasked: 4,
      skipped: [{ path: 'scans/contrato.pdf', reason: 'no extractable text' }],
      sourceErrors: [],
    },
  ],
  removedPersonas: ['pedro-viejo'],
};

const failed: IngestionRun = {
  jobId: 'job-b',
  trigger: 'manual',
  status: 'failed',
  requestedAt: '2026-10-15T13:00:00Z',
  personas: [],
  removedPersonas: [],
  reason: 'knowledge root not found',
};

const rejected: IngestionRun = {
  jobId: 'job-c',
  trigger: 'manual',
  status: 'rejected',
  requestedAt: '2026-10-15T12:00:00Z',
  personas: [],
  removedPersonas: [],
  reason: 'another update is in progress',
};

function rowOf(text: string): HTMLElement {
  const row = screen.getByText(text).closest('tr');
  if (row === null) {
    throw new Error(`No row with ${text}`);
  }
  return row;
}

describe('updates screen', () => {
  it('shows the history with the summary of each update', async () => {
    mockAuthApi({ signedIn: true });
    mockIngestionApi({ history: [completed, failed, rejected] });
    const { user } = renderApp('/sources');

    expect(await screen.findByText('Completada')).toBeInTheDocument();
    const row = rowOf('Completada');
    expect(within(row).getByText('Programada')).toBeInTheDocument();
    expect(
      within(row)
        .getAllByRole('cell')
        .slice(3)
        .map((cell) => cell.textContent),
    ).toEqual(['2', '3', '1', '2', '17', '1', '4']);
    expect(within(rowOf('Falló')).getByText('Manual')).toBeInTheDocument();
    expect(screen.getByText('Rechazada')).toBeInTheDocument();

    // The detail: per persona, the skipped files with their reason, and removed personas.
    const [detail] = screen.getAllByText('Detalle');
    if (detail === undefined) {
      throw new Error('No detail');
    }
    await user.click(detail);
    expect(screen.getByRole('heading', { name: 'Ana Gómez' })).toBeInTheDocument();
    expect(screen.getByText(/9 sin cambios/)).toBeInTheDocument();
    expect(
      within(screen.getByRole('list', { name: 'Omitidos de Ana Gómez' })).getByRole('listitem'),
    ).toHaveTextContent('scans/contrato.pdf: no extractable text');
    expect(screen.getByText(/Personas quitadas.*pedro-viejo/)).toBeInTheDocument();
    expect(screen.getByText('Motivo: knowledge root not found')).toBeInTheDocument();
    expect(screen.getByText('Motivo: another update is in progress')).toBeInTheDocument();
  });

  it('asks for an update now and shows it as requested', async () => {
    mockAuthApi({ signedIn: true });
    const api = mockIngestionApi({ history: [completed] });
    const { user } = renderApp('/sources');
    await screen.findByText('Completada');

    await user.click(screen.getByRole('button', { name: 'Actualizar ahora' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Actualización pedida');
    expect(api.requested).toHaveLength(1);
    expect(await screen.findByText('Pedida')).toBeInTheDocument();
    // Only one update at a time (spec HU4.9).
    expect(screen.getByRole('button', { name: 'Actualización en curso…' })).toBeDisabled();
  });

  it('follows an update in progress until it ends', async () => {
    mockAuthApi({ signedIn: true });
    let calls = 0;
    mockIngestionApi({
      history: () => {
        calls += 1;
        return [{ ...completed, status: calls === 1 ? 'running' : 'completed' }];
      },
    });
    renderApp('/sources');

    expect(await screen.findByText('En curso')).toBeInTheDocument();
    expect(await screen.findByText('Completada', {}, { timeout: 6_000 })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actualizar ahora' })).toBeEnabled();
  });

  it('tells when the update could not be requested', async () => {
    mockAuthApi({ signedIn: true });
    mockIngestionApi({ history: [], requestStatus: 503 });
    const { user } = renderApp('/sources');
    expect(await screen.findByText('Todavía no hubo actualizaciones.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Actualizar ahora' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No se pudo pedir la actualización.',
    );
  });
});
