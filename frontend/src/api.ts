import type { Config, Drift, Endpoint, Result, Status, TestCase } from './types'

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  config: () => j<Config>('/api/config'),
  saveConfig: (patch: Partial<Omit<Config, 'status'>>) =>
    j<Config>('/api/config', { method: 'POST', body: JSON.stringify(patch) }),
  rescan: () => j<Status>('/api/rescan', { method: 'POST' }),
  ackBaseline: () => j<Status>('/api/baseline/ack', { method: 'POST' }),
  endpoints: () => j<{ endpoints: Endpoint[]; drift: Drift; acl_groups: string[]; status: Status }>('/api/endpoints'),
  testcases: (id: string) => j<{ endpoint: Endpoint; testcases: TestCase[] }>(`/api/endpoints/${id}/testcases`),
  execute: (endpoint_id: string, testcase: TestCase, base_url: string) =>
    j<Result>('/api/execute', { method: 'POST', body: JSON.stringify({ endpoint_id, testcase, base_url }) }),
  results: () => j<Record<string, Record<string, Result>>>('/api/results'),
  clearResults: () => j<{ status: string }>('/api/results', { method: 'DELETE' }),
}
