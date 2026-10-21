import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, FolderSync, KeyRound, Loader2, Search, Settings, Unplug } from 'lucide-react'
import { api } from './api'
import { Drawer } from './Drawer'
import { CredentialsModal, SettingsModal } from './Modals'
import { MethodBadge, Pill } from './ui'
import { Workspace } from './Workspace'
import type { Config, Drift, Endpoint, Result, TestCase } from './types'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [endpoints, setEndpoints] = useState<Endpoint[]>([])
  const [drift, setDrift] = useState<Drift>({ unrouted_operations: [], orphaned_routes: [] })
  const [groups, setGroups] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('all')
  const [selectedId, setSelectedId] = useState<string>()
  const [tests, setTests] = useState<TestCase[]>([])
  const [loadingTests, setLoadingTests] = useState(false)
  const [results, setResults] = useState<Record<string, Result>>({})
  const [running, setRunning] = useState<Set<string>>(new Set())
  const [drawerId, setDrawerId] = useState<string>()
  const [modal, setModal] = useState<'settings' | 'creds' | null>(null)
  const [scanning, setScanning] = useState(false)
  const [targetUrl, setTargetUrl] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [c, e] = await Promise.all([api.config(), api.endpoints()])
      setConfig(c); setTargetUrl((t) => t || c.target_url)
      setEndpoints(e.endpoints); setDrift(e.drift); setGroups(e.acl_groups); setError('')
    } catch (err) { setError((err as Error).message) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { // pick up file-watcher re-indexing
    const t = setInterval(async () => {
      try {
        const c = await api.config()
        if (c.status.scanned_at !== config?.status.scanned_at) load()
      } catch { /* backend offline */ }
    }, 4000)
    return () => clearInterval(t)
  }, [config?.status.scanned_at, load])

  const selected = endpoints.find((e) => e.id === selectedId)
  useEffect(() => {
    if (!selectedId) return
    setLoadingTests(true); setTests([]); setResults({}); setDrawerId(undefined)
    api.testcases(selectedId).then((r) => setTests(r.testcases)).catch((e) => setError(e.message)).finally(() => setLoadingTests(false))
  }, [selectedId, config?.status.scanned_at])

  const tags = useMemo(() => ['all', ...new Set(endpoints.flatMap((e) => e.tags))], [endpoints])
  const visible = useMemo(() => endpoints.filter((e) =>
    (tag === 'all' || e.tags.includes(tag)) &&
    `${e.method} ${e.full_path} ${e.summary} ${e.operation_id}`.toLowerCase().includes(query.toLowerCase())), [endpoints, tag, query])

  const runCase = useCallback(async (t: TestCase) => {
    if (!selectedId) return
    setRunning((s) => new Set(s).add(t.id))
    setTests((ts) => ts.map((x) => (x.id === t.id ? t : x)))
    try {
      const r = await api.execute(selectedId, t, targetUrl)
      setResults((m) => ({ ...m, [t.id]: r }))
    } catch (e) {
      setResults((m) => ({ ...m, [t.id]: { passed: false, error: (e as Error).message } }))
    } finally {
      setRunning((s) => { const n = new Set(s); n.delete(t.id); return n })
    }
  }, [selectedId, targetUrl])

  const runAll = async () => {
    const queue = [...tests]
    await Promise.all(Array.from({ length: 4 }, async () => {
      for (let t = queue.shift(); t; t = queue.shift()) await runCase(t)
    }))
  }

  const rescan = async () => {
    setScanning(true)
    try { await api.rescan(); await load() } finally { setScanning(false) }
  }

  const saveTarget = () => { if (config && targetUrl !== config.target_url) api.saveConfig({ target_url: targetUrl }).then(setConfig) }
  const drawerTc = tests.find((t) => t.id === drawerId)

  return (
    <div className="flex h-full flex-col">
      {/* ---------------- top bar ---------------- */}
      <header className="glass z-20 flex flex-wrap items-center gap-3 border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2 pr-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-500 text-sm font-bold shadow-lg shadow-brand-500/40">⇄</div>
          <div className="leading-tight">
            <div className="text-sm font-bold">OAS ⇄ Kong Workbench</div>
            <div className="text-[10px] text-slate-500">Test generation &amp; execution</div>
          </div>
        </div>
        <div className="hidden min-w-0 max-w-sm flex-col text-[10px] leading-snug text-slate-500 xl:flex">
          <span className="truncate" title={config?.oas_dir}>OAS&nbsp;&nbsp;<code className="text-slate-300">{config?.oas_dir}</code></span>
          <span className="truncate" title={config?.kong_dir}>KONG <code className="text-slate-300">{config?.kong_dir}</code></span>
        </div>
        <button id="rescan-btn" className="btn btn-ghost" onClick={rescan} disabled={scanning}>
          {scanning ? <Loader2 size={14} className="animate-spin" /> : <FolderSync size={14} />} Re-scan Local Folders
        </button>
        <button id="settings-btn" className="btn btn-ghost" onClick={() => setModal('settings')} aria-label="Settings"><Settings size={14} /></button>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500" htmlFor="target-url">Target</label>
          <input id="target-url" className="input w-72 font-mono" value={targetUrl} placeholder="http://localhost:8000"
            onChange={(e) => setTargetUrl(e.target.value)} onBlur={saveTarget} />
          <button id="creds-btn" className="btn btn-primary" onClick={() => setModal('creds')}><KeyRound size={14} /> ACL Tokens</button>
        </div>
      </header>

      {(error || config?.status.errors.length) ? (
        <div className="flex items-center gap-2 bg-rose-500/15 px-4 py-2 text-xs text-rose-300">
          <AlertTriangle size={14} /> {error || config?.status.errors.join(' · ')}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        {/* ---------------- sidebar ---------------- */}
        <nav className="glass flex w-80 shrink-0 flex-col border-r border-white/10" aria-label="Endpoints">
          <div className="space-y-2 p-3">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" />
              <input id="search" className="input pl-8" placeholder="Search endpoints…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-1">
              {tags.map((t) => (
                <button key={t} onClick={() => setTag(t)}
                  className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition ${tag === t ? 'border-brand-500 bg-brand-500/20 text-brand-400' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}>{t}</button>
              ))}
            </div>
            <div className="flex gap-1.5 text-[10px]">
              <Pill tone="slate">{config?.status.operations ?? 0} ops</Pill>
              <Pill tone="red" title="OAS operations missing in Kong">{drift.unrouted_operations.length} unrouted</Pill>
              <Pill tone="amber" title="Kong routes missing in OAS">{drift.orphaned_routes.length} orphaned</Pill>
            </div>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {visible.map((e) => (
              <li key={e.id}>
                <button onClick={() => setSelectedId(e.id)}
                  className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs transition hover:bg-white/5 ${selectedId === e.id ? 'bg-brand-500/15 ring-1 ring-brand-500/40' : ''}`}>
                  <MethodBadge method={e.method} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-slate-200">{e.full_path}</span>
                    <span className="block truncate text-[10px] text-slate-500">{e.summary}</span>
                  </span>
                  {e.drift === 'unrouted'
                    ? <Pill tone="red" title="Not routed in Kong"><Unplug size={10} /></Pill>
                    : <Pill tone="green" title={`Kong route: ${e.kong?.routes.join(', ')}`}>kong</Pill>}
                </button>
              </li>
            ))}
            {drift.orphaned_routes.length > 0 && (
              <li className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/5 p-2">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300">Orphaned Kong routes</div>
                {drift.orphaned_routes.map((r) => (
                  <div key={r.name} className="text-[11px] text-slate-400"><code className="text-amber-200">{r.name}</code> {r.paths.join(', ')}</div>
                ))}
              </li>
            )}
          </ul>
        </nav>

        {/* ---------------- workspace ---------------- */}
        <main className="min-w-0 flex-1 overflow-y-auto">
          {selected ? (
            <Workspace endpoint={selected} tests={tests} loading={loadingTests} results={results} running={running}
              selected={drawerId} onSelect={(t) => setDrawerId(t.id)} onRun={runCase} onRunAll={runAll} />
          ) : (
            <div className="grid h-full place-items-center p-8 text-center">
              <div className="fade-up max-w-md">
                <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-500 text-3xl shadow-xl shadow-brand-500/30">⇄</div>
                <h1 className="text-xl font-bold">Select an API to begin</h1>
                <p className="mt-2 text-sm text-slate-400">Pick an endpoint from the sidebar to generate its positive, negative, polymorphic and Kong security test matrix.</p>
              </div>
            </div>
          )}
        </main>
      </div>

      {drawerTc && <Drawer tc={drawerTc} result={results[drawerTc.id]} running={running.has(drawerTc.id)} onRun={runCase} onClose={() => setDrawerId(undefined)} />}
      {modal === 'settings' && config && (
        <SettingsModal config={config} onClose={() => setModal(null)}
          onSave={async (p) => { setConfig(await api.saveConfig(p)); await load() }} />
      )}
      {modal === 'creds' && config && (
        <CredentialsModal config={config} groups={groups} onClose={() => setModal(null)}
          onSave={async (credentials) => setConfig(await api.saveConfig({ credentials }))} />
      )}
    </div>
  )
}
