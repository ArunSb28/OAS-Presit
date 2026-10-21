export type Kong = {
  routes: string[]; service: string | null; public_path: string; strip_path: boolean
  plugins: { name: string; config: Record<string, unknown>; scope: string }[]
  auth: string[]; acl_allow: string[]; acl_deny: string[]
}
export type Endpoint = {
  id: string; method: string; path: string; full_path: string; spec_file: string
  operation_id: string | null; summary: string; tags: string[]; deprecated: boolean
  kong: Kong | null; drift: 'ok' | 'unrouted'
}
export type Drift = {
  unrouted_operations: { id: string; method: string; path: string }[]
  orphaned_routes: { name: string; paths: string[]; methods: string[]; service: string | null }[]
}
export type Status = {
  scanned_at: number | null; errors: string[]; operations: number; kong_routes: number
  kong_files: string[]; unrouted: number; orphaned: number
}
export type Credential = { group: string; username: string; password: string; token: string }
export type Config = {
  oas_dir: string; kong_dir: string; target_url: string; verify_tls: boolean
  credentials: Credential[]; status: Status
}
export type Request = {
  path_params: Record<string, unknown>; query: Record<string, unknown>
  headers: Record<string, string>; body: unknown; content_type: string | null
}
export type TestCase = {
  id: string; group: string; subgroup: string | null; name: string; description: string
  method: string; path: string; public_path: string; request: Request; expected: string[]
  auth: { mode: 'group' | 'none'; group: string | null; scheme: unknown }
  validate_contract: boolean
}
export type Result = {
  passed: boolean | null; skipped?: boolean; error?: string; status?: number; status_ok?: boolean
  expected?: string[]; time_ms?: number | null; url?: string
  request_headers?: Record<string, string>; headers?: Record<string, string>
  body?: unknown; is_json?: boolean
  contract?: { validated: boolean; valid: boolean | null; errors: { path: string; message: string }[]; note?: string } | null
}
