import type { AuditFlag, AuditOutcome, AuditQuery } from '../../api/audit.ts';

export const PAGE_SIZE = 20;

/** What the filter bar holds: plain form values ('' = any). */
export interface AuditFilters {
  personaId: string;
  /** yyyy-mm-dd, local day, included. */
  from: string;
  /** yyyy-mm-dd, local day, included. */
  to: string;
  outcome: '' | AuditOutcome;
  /** A flag, or "rejected": the requests refused by the limits or the validation (spec HU8.2). */
  flag: '' | 'rejected' | AuditFlag;
  referredOnly: boolean;
}

export const noFilters: AuditFilters = {
  personaId: '',
  from: '',
  to: '',
  outcome: '',
  flag: '',
  referredOnly: false,
};

export const outcomeLabels: Record<AuditOutcome, string> = {
  answered: 'Respondida',
  partially_answered: 'Respondida en parte',
  no_information: 'Sin información',
  out_of_scope: 'Fuera de ámbito',
  small_talk: 'Charla',
  about_assistant: 'Sobre el asistente',
  error: 'Error',
};

export const outcomeChips: Record<AuditOutcome, string> = {
  answered: 'chip-completed',
  partially_answered: 'chip-progress',
  no_information: 'chip-pending',
  out_of_scope: 'chip-pending',
  small_talk: 'chip-pending',
  about_assistant: 'chip-pending',
  error: 'chip-blocked',
};

export const flagLabels: Record<AuditFlag, string> = {
  injection_suspected: 'Posible manipulación',
  rate_limited: 'Límite de pedidos',
  question_too_long: 'Pregunta muy larga',
  invalid_request: 'Pedido inválido',
};

const rejectedFlags: AuditFlag[] = ['rate_limited', 'question_too_long', 'invalid_request'];

/** The query of the Core API for these filters and page (dates are whole local days). */
export function toQuery(filters: AuditFilters, page: number): AuditQuery {
  const query: AuditQuery = { page, size: PAGE_SIZE };
  if (filters.personaId !== '') {
    query.personaId = filters.personaId;
  }
  if (filters.from !== '') {
    query.from = startOfDay(filters.from).toISOString();
  }
  if (filters.to !== '') {
    const next = startOfDay(filters.to);
    next.setDate(next.getDate() + 1);
    query.to = next.toISOString();
  }
  if (filters.outcome !== '') {
    query.outcome = [filters.outcome];
  }
  if (filters.flag === 'rejected') {
    query.flag = rejectedFlags;
  } else if (filters.flag !== '') {
    query.flag = [filters.flag];
  }
  if (filters.referredOnly) {
    query.referred = true;
  }
  return query;
}

function startOfDay(day: string): Date {
  const [year = 0, month = 1, date = 1] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}
