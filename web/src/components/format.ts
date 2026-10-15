const dateTime = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short' });

/** "15/10/26, 14:03" in the time zone of the browser; "—" without a date. */
export function formatDateTime(iso: string | undefined | null): string {
  return iso ? dateTime.format(new Date(iso)) : '—';
}
