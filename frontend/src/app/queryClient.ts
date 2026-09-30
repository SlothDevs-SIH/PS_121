import { QueryClient } from '@tanstack/react-query'

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: 1,
        // Queries run even when the browser reports no network: the service worker may
        // answer from a downloaded well pack (FRONTEND_PLAN §12). The default ('online')
        // would pause them and leave offline screens loading forever.
        networkMode: 'always',
      },
    },
  })
}
