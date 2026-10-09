import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchCurrentUser,
  login,
  logout,
  type Credentials,
  type CurrentUser,
} from '../../api/auth.ts';
import { ApiError } from '../../api/client.ts';

const sessionKey = ['session'] as const;

/** The signed-in user; null when there is no session. */
export function useSession() {
  return useQuery({ queryKey: sessionKey, queryFn: fetchCurrentUser, staleTime: Infinity });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: Credentials): Promise<CurrentUser> => {
      await login(credentials);
      const user = await fetchCurrentUser();
      if (user === null) {
        // Logged in, but the session cookie did not stick.
        throw new ApiError(401);
      }
      return user;
    },
    onSuccess: (user) => {
      queryClient.setQueryData(sessionKey, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSettled: () => {
      // Nothing cached for the previous user survives the session.
      queryClient.removeQueries();
      queryClient.setQueryData(sessionKey, null);
    },
  });
}
