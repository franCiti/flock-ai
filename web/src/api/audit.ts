import { ApiError, api } from './client.ts';
import type { components, operations } from './schema.ts';

export type AuditRecord = components['schemas']['AuditRecord'];
export type AuditPage = components['schemas']['AuditPage'];
export type AuditQuery = NonNullable<operations['find']['parameters']['query']>;
export type AuditOutcome = NonNullable<AuditRecord['outcome']>;
export type AuditFlag = NonNullable<AuditQuery['flag']>[number];

/** A page of the audit log, newest first; the filters apply together (plan 6.3). */
export async function fetchAudit(query: AuditQuery): Promise<AuditPage> {
  const { data, response } = await api.GET('/api/audit', { params: { query } });
  if (data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}
