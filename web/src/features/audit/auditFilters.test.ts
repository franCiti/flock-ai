import { noFilters, toQuery } from './auditFilters.ts';

describe('audit filters', () => {
  it('without filters asks only for the page', () => {
    expect(toQuery(noFilters, 2)).toEqual({ page: 2, size: 20 });
  });

  it('turns the days into whole local days, "to" included', () => {
    const query = toQuery({ ...noFilters, from: '2026-10-01', to: '2026-10-15' }, 0);
    expect(query.from).toBe(new Date(2026, 9, 1).toISOString());
    expect(query.to).toBe(new Date(2026, 9, 16).toISOString());
  });

  it('maps persona, outcome, flag and referral', () => {
    expect(
      toQuery(
        {
          ...noFilters,
          personaId: 'ana-datos',
          outcome: 'no_information',
          flag: 'injection_suspected',
          referredOnly: true,
        },
        0,
      ),
    ).toEqual({
      page: 0,
      size: 20,
      personaId: 'ana-datos',
      outcome: ['no_information'],
      flag: ['injection_suspected'],
      referred: true,
    });
  });

  it('"rejected requests" are the ones refused by limits or validation', () => {
    expect(toQuery({ ...noFilters, flag: 'rejected' }, 0).flag).toEqual([
      'rate_limited',
      'question_too_long',
      'invalid_request',
    ]);
  });
});
