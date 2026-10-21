import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, FolderSync, KeyRound, Loader2, Moon, Settings, Sun } from 'lucide-react'
import { api } from './api'
import { Drawer } from './Drawer'
import { CredentialsModal, SettingsModal } from './Modals'
import { Dashboard } from './Dashboard'
import { Explorer } from './Explorer'
import { Workspace } from './Workspace'
import type { Config, Drift, Endpoint, Result, TestCase, TestStatus } from './types'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [endpoints, setEndpoints] = useState<Endpoint[]>([])
  const [drift, setDrift] = useState<Drift>({ unrouted_operations: [], orphaned_routes: [] })
  const [groups, setGroups] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [tests, setTests] = useState<TestCase[]>([])
  const [loadingTests, setLoadingTests] = useState(false)
  const [allResults, setAllResults] = useState<Record<string, Record<string, Result>>>(() => {
    try { return JSON.parse(localStorage.getItem('workbench.test_results') ?? '{}') } catch { return {} }
  })
  const [running, setRunning] = useState<Set<string>>(new Set())
  const [drawerId, setDrawerId] = useState<string>()
  const [modal, setModal] = useState<'settings' | 'creds' | null>(null)
  const [scanning, setScanning] = useState(false)
  const [targetUrl, setTargetUrl] = useState('')
  const [error, setError] = useState('')
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('theme') as 'dark' | 'light') || 'dark')
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('theme', theme) }, [theme])

  const load = useCallback(async () => {
    try {
      const [c, e, res] = await Promise.all([
        api.config(),
        api.endpoints(),
        api.results().catch(() => ({} as Record<string, Record<string, Result>>)),
      ])
      setConfig(c); setTargetUrl((t) => t || c.target_url)
      setEndpoints(e.endpoints); setDrift(e.drift); setGroups(e.acl_groups); setError('')
      if (res && Object.keys(res).length > 0) {
        setAllResults((prev) => {
          const merged = { ...res, ...prev }
          try { localStorage.setItem('workbench.test_results', JSON.stringify(merged)) } catch {}
          return merged
        })
      }
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

  const testStatuses = useMemo(() => {
    const map: Record<string, TestStatus> = {}
    for (const ep of endpoints) {
      const epRes = allResults[ep.id]
      if (!epRes || Object.keys(epRes).length === 0) {
        map[ep.id] = ep.test_status ?? 'untested'
      } else {
        const vals = Object.values(epRes)
        if (vals.some((v) => v.passed === false)) map[ep.id] = 'failed'
        else if (vals.some((v) => v.passed === true)) map[ep.id] = 'passed'
        else map[ep.id] = ep.test_status ?? 'untested'
      }
    }
    return map
  }, [endpoints, allResults])

  const untestedCount = useMemo(() => {
    return endpoints.filter((e) => (testStatuses[e.id] ?? e.test_status ?? 'untested') === 'untested').length
  }, [endpoints, testStatuses])

  const selected = endpoints.find((e) => e.id === selectedId)
  useEffect(() => {
    if (!selectedId) return
    setLoadingTests(true); setTests([]); setDrawerId(undefined)
    api.testcases(selectedId).then((r) => setTests(r.testcases)).catch((e) => setError(e.message)).finally(() => setLoadingTests(false))
  }, [selectedId, config?.status.scanned_at])

  const currentResults = (selectedId && allResults[selectedId]) || {}

  const runCase = useCallback(async (t: TestCase) => {
    if (!selectedId) return
    setRunning((s) => new Set(s).add(t.id))
    setTests((ts) => ts.map((x) => (x.id === t.id ? t : x)))
    try {
      const r = await api.execute(selectedId, t, targetUrl)
      setAllResults((prev) => {
        const epMap = { ...(prev[selectedId] ?? {}), [t.id]: r }
        const next = { ...prev, [selectedId]: epMap }
        try { localStorage.setItem('workbench.test_results', JSON.stringify(next)) } catch {}
        return next
      })
    } catch (e) {
      setAllResults((prev) => {
        const epMap = { ...(prev[selectedId] ?? {}), [t.id]: { passed: false, error: (e as Error).message } }
        const next = { ...prev, [selectedId]: epMap }
        try { localStorage.setItem('workbench.test_results', JSON.stringify(next)) } catch {}
        return next
      })
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
      <header className="z-20 flex flex-wrap items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-4 py-2.5 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 pr-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-base font-bold text-white shadow-lg shadow-brand-500/40">⇄</div>
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight">OAS ⇄ Kong</div>
            <div className="text-[10px] font-medium uppercase tracking-widest text-slate-500">Workbench</div>
          </div>
        </div>

        <div className="hidden items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5 text-[11px] text-slate-400 lg:flex"
          title={`OAS: ${config?.oas_dir}\nKong: ${config?.kong_dir}`}>
          <span className="live-dot h-2 w-2 rounded-full bg-emerald-400" />
          <span className="tabular-nums text-slate-300">{endpoints.length}</span> ops
          <span className="text-slate-600">·</span>
          <span className="tabular-nums font-semibold text-amber-300" title={`${untestedCount} of ${endpoints.length} operations not yet tested`}>{untestedCount} untested</span>
          <span className="text-slate-600">·</span>
          <span className="tabular-nums text-slate-300">{config?.status.kong_routes ?? 0}</span> routes
          {config?.status.scanned_at && <><span className="text-slate-600">·</span>scanned {new Date(config.status.scanned_at * 1000).toLocaleTimeString()}</>}
        </div>

        <button id="rescan-btn" className="btn btn-ghost" onClick={rescan} disabled={scanning} title="Re-scan Local Folders">
          {scanning ? <Loader2 size={14} className="animate-spin" /> : <FolderSync size={14} />} Re-scan
        </button>

        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] pl-3">
            <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500" htmlFor="target-url">Target</label>
            <input id="target-url" className="w-64 bg-transparent py-2 pr-3 font-mono text-xs outline-none placeholder:text-slate-600" value={targetUrl}
              placeholder="http://localhost:8000" onChange={(e) => setTargetUrl(e.target.value)} onBlur={saveTarget} />
          </div>
          <button id="creds-btn" className="btn btn-primary" onClick={() => setModal('creds')}><KeyRound size={14} /> ACL Tokens</button>
          <button id="settings-btn" className="btn btn-ghost !px-2.5" onClick={() => setModal('settings')} aria-label="Settings" title="Directory settings"><Settings size={15} /></button>
          <button id="theme-btn" className="btn btn-ghost !px-2.5" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label="Toggle theme" title="Toggle light / dark">{theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}</button>
        </div>
      </header>

      {(error || config?.status.errors.length) ? (
        <div className="flex items-center gap-2 border-b border-rose-400/30 bg-rose-500/10 px-4 py-2 text-xs font-medium text-rose-300">
          <AlertTriangle size={14} /> {error || config?.status.errors.join(' · ')}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <Explorer endpoints={endpoints} selectedId={selectedId} onSelect={setSelectedId} orphaned={drift.orphaned_routes} testStatuses={testStatuses} />

        {/* ---------------- workspace ---------------- */}
        <main className="min-w-0 flex-1 overflow-y-auto">
          {selected ? (
            <Workspace endpoint={selected} tests={tests} loading={loadingTests} results={currentResults} running={running}
              selected={drawerId} onSelect={(t) => setDrawerId(t.id)} onRun={runCase} onRunAll={runAll} />
          ) : (
            <Dashboard endpoints={endpoints} drift={drift} groups={groups} config={config} testStatuses={testStatuses} />
          )}
        </main>
      </div>
      {drawerTc && <Drawer tc={drawerTc} result={currentResults[drawerTc.id]} running={running.has(drawerTc.id)} onRun={runCase} onClose={() => setDrawerId(undefined)} />}
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
