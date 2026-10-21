import { useEffect, useState } from 'react'
import Editor from '@monaco-editor/react'
import { Loader2, Play, X } from 'lucide-react'
import { Pill, statusTone } from './ui'
import type { Result, TestCase } from './types'

type Tab = 'params' | 'headers' | 'body'
type RTab = 'body' | 'headers' | 'contract' | 'request'

const pretty = (v: unknown) => JSON.stringify(v ?? {}, null, 2)

export function Drawer({ tc, result, running, onRun, onClose }: {
  tc: TestCase; result?: Result; running: boolean; onRun: (tc: TestCase) => void; onClose: () => void
}) {
  const mt = document.documentElement.dataset.theme === 'light' ? 'light' : 'vs-dark'
  const [tab, setTab] = useState<Tab>('body')
  const [rtab, setRtab] = useState<RTab>('body')
  const [params, setParams] = useState('')
  const [headers, setHeaders] = useState('')
  const [body, setBody] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    setParams(pretty({ path: tc.request.path_params, query: tc.request.query }))
    setHeaders(pretty(tc.request.headers))
    setBody(tc.request.body === null || tc.request.body === undefined ? '' : pretty(tc.request.body))
    setTab(tc.request.body !== null && tc.request.body !== undefined ? 'body' : 'params')
    setErr('')
  }, [tc.id])

  const run = () => {
    try {
      const p = JSON.parse(params || '{}')
      const next: TestCase = {
        ...tc,
        request: {
          ...tc.request,
          path_params: p.path ?? {}, query: p.query ?? {},
          headers: JSON.parse(headers || '{}'),
          body: body.trim() ? JSON.parse(body) : null,
        },
      }
      setErr('')
      onRun(next)
    } catch (e) {
      setErr(`Invalid JSON: ${(e as Error).message}`)
    }
  }

  const value = tab === 'params' ? params : tab === 'headers' ? headers : body
  const setValue = tab === 'params' ? setParams : tab === 'headers' ? setHeaders : setBody
  const tabBtn = (t: Tab, label: string) => (
    <button key={t} onClick={() => setTab(t)}
      className={`rounded-md px-3 py-1 text-xs font-semibold transition ${tab === t ? 'bg-brand-500/25 text-brand-400' : 'text-slate-400 hover:text-slate-200'}`}>{label}</button>
  )
  const rBtn = (t: RTab, label: string) => (
    <button key={t} onClick={() => setRtab(t)}
      className={`rounded-md px-3 py-1 text-xs font-semibold transition ${rtab === t ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200'}`}>{label}</button>
  )
  const c = result?.contract

  return (
    <aside id="test-drawer" className="slide-in fixed right-0 top-0 z-30 flex h-full w-full max-w-[660px] flex-col border-l border-[var(--line)] bg-ink-900 shadow-[-24px_0_60px_-24px_rgba(0,0,0,.6)]">
      <header className="flex items-start justify-between gap-3 border-b border-white/10 p-4">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tc.group}{tc.subgroup ? ` · ${tc.subgroup}` : ''}</div>
          <h3 className="truncate text-sm font-semibold">{tc.name}</h3>
          <p className="mt-0.5 text-xs text-slate-400">{tc.description}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Pill tone="violet">expect {tc.expected.join(' / ')}</Pill>
            <Pill tone="cyan">auth: {tc.auth.mode === 'none' ? 'none' : tc.auth.group ?? 'any'}</Pill>
            <Pill>{tc.method} {tc.public_path}</Pill>
          </div>
        </div>
        <div className="flex gap-2">
          <button id="run-case" className="btn btn-primary" disabled={running} onClick={run}>
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Run Case
          </button>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close drawer"><X size={14} /></button>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-1 px-4 pt-3">
          {tabBtn('params', 'Path & Query')}{tabBtn('headers', 'Headers')}{tabBtn('body', 'Body')}
          {err && <span className="ml-auto text-xs text-rose-400">{err}</span>}
        </div>
        <div className="mx-4 mt-2 h-56 overflow-hidden rounded-xl border border-white/10">
          <Editor height="100%" language="json" theme={mt} value={value} onChange={(v) => setValue(v ?? '')}
            options={{ minimap: { enabled: false }, fontSize: 12, scrollBeyondLastLine: false, tabSize: 2, automaticLayout: true }} />
        </div>

        <div className="mt-4 flex items-center gap-2 px-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Response</h4>
          {running && <Loader2 size={14} className="animate-spin text-brand-400" />}
          {result && !running && (<>
            {result.passed === true && <Pill tone="green">PASS</Pill>}
            {result.passed === false && <Pill tone="red">FAIL</Pill>}
            {result.skipped && <Pill tone="amber">SKIPPED</Pill>}
            {result.status !== undefined && <Pill tone={statusTone(result.status)}>{result.status}</Pill>}
            {result.time_ms != null && <Pill>{result.time_ms} ms</Pill>}
          </>)}
        </div>

        {!result && !running && <p className="px-4 pt-3 text-xs text-slate-500">Edit the request above and press <b>Run Case</b>.</p>}
        {result?.error && <p className="mx-4 mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 p-3 text-xs text-rose-300">{result.error}</p>}
        {result && result.status !== undefined && (
          <div className="mt-2 flex min-h-0 flex-1 flex-col px-4 pb-4">
            <div className="flex gap-1">
              {rBtn('body', 'Body')}{rBtn('headers', 'Headers')}{rBtn('contract', `Contract ${c?.validated ? (c.valid ? '✓' : '✗') : ''}`)}{rBtn('request', 'Request')}
            </div>
            <div className="mt-2 min-h-0 flex-1 overflow-auto rounded-xl border border-white/10 bg-black/30">
              {rtab === 'body' && (
                <Editor height="100%" language={result.is_json ? 'json' : 'plaintext'} theme={mt}
                  value={typeof result.body === 'string' ? result.body : pretty(result.body)}
                  options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, automaticLayout: true, scrollBeyondLastLine: false }} />
              )}
              {rtab === 'headers' && <KV data={result.headers} />}
              {rtab === 'request' && <KV data={{ url: result.url, ...result.request_headers }} />}
              {rtab === 'contract' && (
                <div className="space-y-2 p-3 text-xs">
                  {!c?.validated && <p className="text-slate-400">{c?.note ?? 'Contract validation not applied to this case.'}</p>}
                  {c?.validated && c.valid && <p className="text-emerald-300">Response conforms to the OAS schema.</p>}
                  {c?.errors?.map((e: { path?: string; message?: string }, i: number) => (
                    <div key={i} className="rounded-lg border border-rose-400/30 bg-rose-500/10 p-2">
                      <code className="text-rose-300">{e.path}</code><div className="text-slate-300">{e.message}</div>
                    </div>
                  ))}
                  {!result.status_ok && <p className="text-amber-300">Status {result.status} not in expected [{result.expected?.join(', ')}].</p>}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </aside>
  )
}

function KV({ data }: { data?: Record<string, unknown> }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {Object.entries(data ?? {}).map(([k, v]) => (
          <tr key={k} className="border-b border-white/5 align-top">
            <td className="whitespace-nowrap px-3 py-1.5 font-mono text-brand-400">{k}</td>
            <td className="break-all px-3 py-1.5 font-mono text-slate-300">{String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
