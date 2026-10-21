import { useMemo, useState } from 'react'
import { ChevronDown, Loader2, Play, ShieldCheck, ShieldOff } from 'lucide-react'
import { MethodBadge, Pill } from './ui'
import type { Endpoint, Result, TestCase } from './types'

const GROUP_ORDER = ['Positive', 'Discriminator Variants', 'Missing Required', 'Boundary & Mutation', 'Kong Security & ACL']

export function Workspace({ endpoint, tests, loading, results, running, selected, onSelect, onRun, onRunAll }: {
  endpoint: Endpoint; tests: TestCase[]; loading: boolean
  results: Record<string, Result>; running: Set<string>; selected?: string
  onSelect: (t: TestCase) => void; onRun: (t: TestCase) => void; onRunAll: () => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({ Positive: true })
  const [sub, setSub] = useState<Record<string, string>>({})

  const groups = useMemo(() => {
    const m = new Map<string, TestCase[]>()
    tests.forEach((t) => m.set(t.group, [...(m.get(t.group) ?? []), t]))
    return GROUP_ORDER.filter((g) => m.has(g)).map((g) => [g, m.get(g)!] as const)
  }, [tests])

  const done = tests.filter((t) => results[t.id]?.passed !== undefined && results[t.id]?.passed !== null)
  const pass = done.filter((t) => results[t.id].passed).length
  const k = endpoint.kong

  return (
    <div className="fade-up mx-auto max-w-5xl p-6">
      <header className="glass rounded-2xl p-5">
        <div className="flex flex-wrap items-center gap-3">
          <MethodBadge method={endpoint.method} />
          <h1 className="font-mono text-lg font-semibold">{endpoint.full_path}</h1>
          {endpoint.deprecated && <Pill tone="amber">deprecated</Pill>}
          <button id="run-all" className="btn btn-primary ml-auto" onClick={onRunAll} disabled={!tests.length}>
            <Play size={14} /> Run All for API
          </button>
        </div>
        <p className="mt-1 text-sm text-slate-400">{endpoint.summary} <span className="text-slate-600">· {endpoint.operation_id} · {endpoint.spec_file}</span></p>
        <div className="mt-4 grid gap-3 text-xs md:grid-cols-3">
          <Info label="Kong route">
            {k ? <><div className="font-mono text-slate-200">{k.routes.join(', ')}</div>
              <div className="text-slate-500">service {k.service} · public {k.public_path} · strip_path {String(k.strip_path)}</div></>
              : <Pill tone="red">Unrouted – not exposed in Kong</Pill>}
          </Info>
          <Info label="Active plugins">
            <div className="flex flex-wrap gap-1">{k?.plugins.length ? k.plugins.map((p) => <Pill key={p.name} tone="violet">{p.name}</Pill>) : <span className="text-slate-500">none</span>}</div>
          </Info>
          <Info label="ACL groups">
            <div className="flex flex-wrap gap-1">
              {k?.acl_allow.map((g) => <Pill key={g} tone="green"><ShieldCheck size={10} />{g}</Pill>)}
              {k?.acl_deny.map((g) => <Pill key={g} tone="red"><ShieldOff size={10} />{g}</Pill>)}
              {!k?.acl_allow.length && !k?.acl_deny.length && <span className="text-slate-500">no ACL</span>}
            </div>
          </Info>
        </div>
        {done.length > 0 && (
          <div className="mt-4 flex items-center gap-3 text-xs">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-gradient-to-r from-emerald-400 to-cyan-400 transition-all" style={{ width: `${(pass / tests.length) * 100}%` }} />
            </div>
            <span className="text-slate-300">{pass}/{done.length} passed · {tests.length} total</span>
          </div>
        )}
      </header>

      {loading && <div className="mt-8 flex justify-center text-slate-400"><Loader2 className="animate-spin" /></div>}

      <div className="mt-5 space-y-3">
        {groups.map(([g, items]) => {
          const isOpen = !!open[g]
          const subs = [...new Set(items.map((t) => t.subgroup).filter(Boolean))] as string[]
          const active = sub[g] && subs.includes(sub[g]) ? sub[g] : subs[0]
          const shown = subs.length ? items.filter((t) => t.subgroup === active) : items
          const gp = items.filter((t) => results[t.id]?.passed === true).length
          const gf = items.filter((t) => results[t.id]?.passed === false).length
          return (
            <section key={g} className="glass overflow-hidden rounded-2xl">
              <button className="flex w-full items-center gap-3 px-4 py-3 text-left" onClick={() => setOpen({ ...open, [g]: !isOpen })}>
                <ChevronDown size={16} className={`transition-transform ${isOpen ? '' : '-rotate-90'}`} />
                <span className="text-sm font-semibold">{g}</span>
                <Pill>{items.length}</Pill>
                {gp > 0 && <Pill tone="green">{gp} pass</Pill>}
                {gf > 0 && <Pill tone="red">{gf} fail</Pill>}
              </button>
              {isOpen && (
                <div className="border-t border-white/10">
                  {subs.length > 0 && (
                    <div className="flex flex-wrap gap-1 border-b border-white/5 px-3 py-2">
                      {subs.map((s) => (
                        <button key={s} onClick={() => setSub({ ...sub, [g]: s })}
                          className={`rounded-md px-3 py-1 text-xs font-semibold transition ${s === active ? 'bg-brand-500/25 text-brand-400' : 'text-slate-400 hover:bg-white/5'}`}>
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  {shown.map((t) => <Row key={t.id} t={t} r={results[t.id]} busy={running.has(t.id)} active={selected === t.id} onSelect={onSelect} onRun={onRun} />)}
                </div>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/5 bg-black/20 p-3">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      {children}
    </div>
  )
}

function Row({ t, r, busy, active, onSelect, onRun }: {
  t: TestCase; r?: Result; busy: boolean; active: boolean; onSelect: (t: TestCase) => void; onRun: (t: TestCase) => void
}) {
  return (
    <div onClick={() => onSelect(t)}
      className={`flex cursor-pointer items-center gap-3 border-b border-white/5 px-4 py-2 text-sm transition last:border-0 hover:bg-white/5 ${active ? 'bg-brand-500/10' : ''}`}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${r?.passed === true ? 'bg-emerald-400' : r?.passed === false ? 'bg-rose-400' : r?.skipped ? 'bg-amber-400' : 'bg-slate-600'}`} />
      <span className="min-w-0 flex-1 truncate">{t.name}</span>
      <Pill tone="violet">{t.expected.join('/')}</Pill>
      {r?.status !== undefined && <Pill tone={r.status < 300 ? 'green' : r.status < 500 ? 'amber' : 'red'}>{r.status}</Pill>}
      <button className="btn btn-ghost !px-2 !py-1" aria-label={`Run ${t.name}`} onClick={(e) => { e.stopPropagation(); onRun(t) }} disabled={busy}>
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
      </button>
    </div>
  )
}
