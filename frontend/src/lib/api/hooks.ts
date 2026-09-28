import { useQuery } from '@tanstack/react-query'

import { api } from './client'

export const queryKeys = {
  readiness: ['readiness'] as const,
  meta: ['meta'] as const,
  me: ['me'] as const,
}

/** Polled so the header status pill reflects outages within ~15 s. */
export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.readiness,
    queryFn: api.readiness,
    refetchInterval: 15_000,
    retry: false,
  })
}

export function useMeta() {
  return useQuery({ queryKey: queryKeys.meta, queryFn: api.meta, staleTime: 60_000 })
}

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: 300_000 })
}
