import { AlertTriangle, FlaskConical, GitCompareArrows, KeyRound, Network, ShieldCheck, Unplug } from 'lucide-react'
import type { Config, Drift, Endpoint, TestStatus } from './types'

function Stat({ icon, label, value, hint, tone }: { icon: React.ReactNode; label: string; value: string | number; hint?: string; tone: string }) {
  return (
    <div className="card fade-up p-4">
      <div className={`mb-3 grid h-9 w-9 place-items-center rounded-xl ${tone}`}>{icon}</div>
      <div className="text-2xl font-bold tabular-nums tracking-tight">{value}</div>
      <div className="text-xs font-medium text-slate-300">{label}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
    </div>
  )
}

export function Dashboard({ endpoints, drift, groups, config, testStatuses }: {
  endpoints: Endpoint[]; drift: Drift; groups: string[]; config: Config | null
  testStatuses?: Record<string, TestStatus>
}) {
  const routed = endpoints.filter((e) => e.drift === 'ok').length
  const pct = endpoints.length ? Math.round((routed / endpoints.length) * 100) : 0
  const specs = new Set(endpoints.map((e) => e.spec_file)).size

  const testedCount = endpoints.filter((e) => {
    const st = testStatuses ? (testStatuses[e.id] ?? e.test_status) : e.test_status
    return st === 'passed' || st === 'failed'
  }).length
  const untestedCount = endpoints.length - testedCount
  const passedCount = endpoints.filter((e) => {
    const st = testStatuses ? (testStatuses[e.id] ?? e.test_status) : e.test_status
    return st === 'passed'
  }).length
  const failedCount = endpoints.filter((e) => {
    const st = testStatuses ? (testStatuses[e.id] ?? e.test_status) : e.test_status
    return st === 'failed'
  }).length

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="fade-up">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Overview</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Pick an API to <span className="gradient-text">generate its test matrix</span></h1>
        <p className="mt-2 max-w-xl text-sm text-slate-400">
          Select an operation in the explorer. Positive, negative, polymorphic and Kong security tests are generated instantly and can be edited and run live.
        </p>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat icon={<Network size={18} />} label="Operations" value={endpoints.length} hint={`${specs} spec file${specs === 1 ? '' : 's'}`} tone="bg-brand-500/15 text-brand-400" />
        <Stat icon={<FlaskConical size={18} />} label="Untested APIs" value={untestedCount} hint={testedCount > 0 ? `${testedCount} tested (${passedCount} pass, ${failedCount} fail)` : 'All operations untested'} tone={untestedCount > 0 ? 'border border-dashed border-amber-400/40 bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300'} />
        <Stat icon={<GitCompareArrows size={18} />} label="Routed in Kong" value={`${pct}%`} hint={`${routed} of ${endpoints.length}`} tone="bg-emerald-500/15 text-emerald-300" />
        <Stat icon={<Unplug size={18} />} label="Unrouted operations" value={drift.unrouted_operations.length} hint="In OAS, missing in Kong" tone="bg-rose-500/15 text-rose-300" />
        <Stat icon={<AlertTriangle size={18} />} label="Orphaned routes" value={drift.orphaned_routes.length} hint="In Kong, missing in OAS" tone="bg-amber-500/15 text-amber-300" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={16} className="text-emerald-300" /> ACL groups</h2>
          <div className="flex flex-wrap gap-1.5">
            {groups.length ? groups.map((g) => {
              const has = config?.credentials.some((c) => c.group === g && (c.token || c.password))
              return (
                <span key={g} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${has ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-400/30 bg-amber-500/10 text-amber-300'}`}>
                  <KeyRound size={11} /> {g} <span className="text-[10px] opacity-70">{has ? 'credential set' : 'no credential'}</span>
                </span>
              )
            }) : <span className="text-xs text-slate-500">No ACL groups found in Kong config.</span>}
          </div>
        </section>
        <section className="card p-5">
          <h2 className="mb-3 text-sm font-semibold">Sources</h2>
          <dl className="space-y-2 text-xs">
            <div><dt className="text-slate-500">OAS directory</dt><dd className="truncate font-mono text-slate-300" title={config?.oas_dir}>{config?.oas_dir}</dd></div>
            <div><dt className="text-slate-500">Kong directory</dt><dd className="truncate font-mono text-slate-300" title={config?.kong_dir}>{config?.kong_dir}</dd></div>
            <div><dt className="text-slate-500">Kong files</dt><dd className="font-mono text-slate-300">{config?.status.kong_files.join(', ') || '—'}</dd></div>
          </dl>
        </section>
      </div>
    </div>
  )
}
