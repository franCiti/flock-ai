import { ApiError, api } from './client.ts';
import type { components } from './schema.ts';

export type IngestionRun = components['schemas']['IngestionRun'];
export type PersonaSummary = components['schemas']['PersonaSummary'];
export type Totals = components['schemas']['Totals'];

/** History of the knowledge updates, newest first. */
export async function fetchRuns(limit = 20): Promise<IngestionRun[]> {
  const { data, response } = await api.GET('/api/ingestion/runs', {
    params: { query: { limit } },
  });
  if (data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}

/** Asks for an update now; its progress shows in the history. */
export async function requestUpdate(): Promise<string> {
  const { data, response } = await api.POST('/api/ingestion/runs');
  if (data?.jobId === undefined) {
    throw new ApiError(response.status);
  }
  return data.jobId;
}
