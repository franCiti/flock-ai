import { QueryClient } from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // A 401 or a validation error does not get better by retrying.
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  });
}
