import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, File, Folder, FolderOpen, Search, Unplug, ChevronsDownUp, ChevronsUpDown } from 'lucide-react'
import { MethodBadge, NewBadge, TestStatusBadge } from './ui'
import type { Endpoint, TestStatus } from './types'

type Node = {
  name: string; path: string; kind: 'folder' | 'file'
  children: Node[]; endpoints: Endpoint[]
  total: number; unrouted: number; fresh: number; untested: number
}

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

/** Mirror the OAS directory layout: folders -> spec files -> operations. */
function buildTree(endpoints: Endpoint[], testStatuses?: Record<string, TestStatus>): Node {
  const root: Node = { name: '', path: '', kind: 'folder', children: [], endpoints: [], total: 0, unrouted: 0, fresh: 0, untested: 0 }
  for (const e of endpoints) {
    const parts = e.spec_file.split('/')
    let cur = root
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1
      const path = parts.slice(0, i + 1).join('/')
      let next = cur.children.find((c) => c.path === path)
      if (!next) {
        next = { name: part, path, kind: isFile ? 'file' : 'folder', children: [], endpoints: [], total: 0, unrouted: 0, fresh: 0, untested: 0 }
        cur.children.push(next)
      }
      cur = next
    })
    cur.endpoints.push(e)
  }
  const finish = (n: Node): void => {
    n.children.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'folder' ? -1 : 1))
    n.children.forEach(finish)
    n.total = n.endpoints.length + n.children.reduce((s, c) => s + c.total, 0)
    n.unrouted = n.endpoints.filter((e) => e.drift === 'unrouted').length + n.children.reduce((s, c) => s + c.unrouted, 0)
    n.fresh = n.endpoints.filter((e) => e.is_new).length + n.children.reduce((s, c) => s + c.fresh, 0)
    n.untested = n.endpoints.filter((e) => {
      const st = testStatuses ? (testStatuses[e.id] ?? e.test_status ?? 'untested') : (e.test_status ?? 'untested')
      return st === 'untested'
    }).length + n.children.reduce((s, c) => s + c.untested, 0)
  }
  finish(root)
  return root
}

export function Explorer({ endpoints, selectedId, onSelect, orphaned, testStatuses }: {
  endpoints: Endpoint[]; selectedId?: string; onSelect: (id: string) => void
  orphaned: { name: string; paths: string[]; is_new?: boolean }[]
  testStatuses?: Record<string, TestStatus>
}) {
  const [query, setQuery] = useState('')
  const [methods, setMethods] = useState<Set<string>>(new Set())
  const [driftOnly, setDriftOnly] = useState(false)
  const [newOnly, setNewOnly] = useState(false)
  const [untestedOnly, setUntestedOnly] = useState(false)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    try { return new Set<string>(JSON.parse(localStorage.getItem('explorer.collapsed') ?? '[]')) } catch { return new Set<string>() }
  })
  useEffect(() => { localStorage.setItem('explorer.collapsed', JSON.stringify([...collapsed])) }, [collapsed])

  const filtering = query !== '' || methods.size > 0 || driftOnly || newOnly || untestedOnly
  const filtered = useMemo(() => endpoints.filter((e) => {
    const st = testStatuses ? (testStatuses[e.id] ?? e.test_status ?? 'untested') : (e.test_status ?? 'untested')
    return (
      (!methods.size || methods.has(e.method)) &&
      (!driftOnly || e.drift === 'unrouted') &&
      (!newOnly || e.is_new || (e.kong?.new_routes?.length ?? 0) > 0) &&
      (!untestedOnly || st === 'untested') &&
      `${e.method} ${e.full_path} ${e.summary} ${e.operation_id} ${e.tags.join(' ')} ${e.spec_file}`
        .toLowerCase().includes(query.toLowerCase())
    )
  }), [endpoints, query, methods, driftOnly, newOnly, untestedOnly, testStatuses])

  const tree = useMemo(() => buildTree(filtered, testStatuses), [filtered, testStatuses])

  const allFolders = useMemo(() => {
    const out: string[] = []
    const walk = (n: Node) => { if (n.path && n.kind === 'folder') out.push(n.path); n.children.forEach(walk) }
    walk(buildTree(endpoints, testStatuses))
    return out
  }, [endpoints, testStatuses])

  const toggle = (path: string) => setCollapsed((s) => { const n = new Set(s); n.has(path) ? n.delete(path) : n.add(path); return n })
  const toggleMethod = (m: string) => setMethods((s) => { const n = new Set(s); n.has(m) ? n.delete(m) : n.add(m); return n })

  const render = (n: Node, depth: number): React.ReactNode => (
    <li key={n.path || 'root'}>
      {n.path && (
        <button onClick={() => toggle(n.path)} style={{ paddingLeft: depth * 14 + 8 }}
          aria-expanded={filtering || !collapsed.has(n.path)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setCollapsed((s) => new Set(s).add(n.path))
            if (e.key === 'ArrowRight') setCollapsed((s) => { const x = new Set(s); x.delete(n.path); return x })
          }}
          className="group flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-xs text-slate-300 transition hover:bg-white/5">
          <ChevronRight size={12} className={`shrink-0 text-slate-500 transition-transform ${filtering || !collapsed.has(n.path) ? 'rotate-90' : ''}`} />
          {n.kind === 'folder'
            ? (filtering || !collapsed.has(n.path) ? <FolderOpen size={14} className="shrink-0 text-amber-300" /> : <Folder size={14} className="shrink-0 text-amber-300" />)
            : <File size={14} className="shrink-0 text-cyan-300" />}
          <span className="min-w-0 flex-1 truncate font-medium" title={n.path}>{n.name}</span>
          {n.untested > 0 && (
            <span className="rounded border border-dashed border-amber-400/40 bg-amber-500/10 px-1 py-0.5 text-[9px] font-semibold text-amber-300" title={`${n.untested} operation${n.untested > 1 ? 's' : ''} not yet tested`}>
              {n.untested} untested
            </span>
          )}
          {n.fresh > 0 && <NewBadge title={`${n.fresh} new operation${n.fresh > 1 ? 's' : ''}`}>{n.fresh} new</NewBadge>}
          {n.unrouted > 0 && <span className="rounded bg-rose-500/20 px-1 text-[9px] font-bold text-rose-300" title={`${n.unrouted} unrouted`}>{n.unrouted}!</span>}
          <span className="text-[10px] text-slate-600">{n.total}</span>
        </button>
      )}
      {(!n.path || filtering || !collapsed.has(n.path)) && (
        <ul>
          {n.children.map((c) => render(c, n.path ? depth + 1 : depth))}
          {n.endpoints.map((e) => {
            const st = testStatuses ? (testStatuses[e.id] ?? e.test_status ?? 'untested') : (e.test_status ?? 'untested')
            return (
              <li key={e.id}>
                <button onClick={() => onSelect(e.id)} style={{ paddingLeft: (n.path ? depth + 1 : depth) * 14 + 22 }}
                  className={`flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left text-xs transition hover:bg-white/5 ${selectedId === e.id ? 'bg-brand-500/20 ring-1 ring-inset ring-brand-500/50' : ''}`}>
                  <MethodBadge method={e.method} />
                  <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-200" title={e.summary}>{e.path}</span>
                  {e.is_new && <NewBadge title="New operation since the last baseline">NEW</NewBadge>}
                  {!e.is_new && (e.kong?.new_routes?.length ?? 0) > 0 && <NewBadge tone="cyan" title={`New Kong route: ${e.kong?.new_routes?.join(', ')}`}>ROUTE</NewBadge>}
                  <TestStatusBadge status={st} compact />
                  {e.drift === 'unrouted'
                    ? <span title="Not routed in Kong" className="shrink-0 text-rose-400"><Unplug size={12} /></span>
                    : <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" title={`Kong: ${e.kong?.routes.join(', ')}`} />}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </li>
  )

  return (
    <nav className="flex w-[22rem] shrink-0 flex-col border-r border-white/10 bg-ink-900/60" aria-label="OAS explorer">
      <div className="space-y-2 border-b border-white/5 p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-500">OAS Explorer</h2>
          <div className="flex gap-1">
            <button className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-semibold text-slate-400 hover:bg-white/10 hover:text-slate-200"
              title="Expand all folders" onClick={() => setCollapsed(new Set())}><ChevronsUpDown size={13} /> Expand</button>
            <button className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-semibold text-slate-400 hover:bg-white/10 hover:text-slate-200"
              title="Collapse all folders" onClick={() => setCollapsed(new Set(allFolders))}><ChevronsDownUp size={13} /> Collapse</button>
          </div>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" />
          <input id="search" className="input pl-8" placeholder="Filter by path, file, tag…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {METHODS.map((m) => (
            <button key={m} onClick={() => toggleMethod(m)}
              className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold transition ${methods.has(m) ? 'border-brand-500 bg-brand-500/25 text-white' : 'border-white/10 text-slate-500 hover:text-slate-300'}`}>{m}</button>
          ))}
          <button onClick={() => setDriftOnly(!driftOnly)}
            className={`rounded border px-1.5 py-0.5 text-[9px] font-bold transition ${driftOnly ? 'border-rose-400 bg-rose-500/25 text-rose-200' : 'border-white/10 text-slate-500 hover:text-slate-300'}`}>
            unrouted only
          </button>
          <button onClick={() => setNewOnly(!newOnly)}
            className={`rounded border px-1.5 py-0.5 text-[9px] font-bold transition ${newOnly ? 'border-emerald-400 bg-emerald-500/25 text-emerald-200' : 'border-white/10 text-slate-500 hover:text-slate-300'}`}>
            new only
          </button>
          <button onClick={() => setUntestedOnly(!untestedOnly)}
            className={`rounded border px-1.5 py-0.5 text-[9px] font-bold transition ${untestedOnly ? 'border-amber-400 bg-amber-500/25 text-amber-200' : 'border-white/10 text-slate-500 hover:text-slate-300'}`}>
            untested only
          </button>
        </div>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto px-1.5 py-2">
        {filtered.length === 0 ? <li className="p-4 text-center text-xs text-slate-500">No operations match.</li> : render(tree, 0)}
      </ul>

      {orphaned.length > 0 && (
        <div className="max-h-36 overflow-y-auto border-t border-amber-400/20 bg-amber-500/5 p-2">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-amber-300">Orphaned Kong routes ({orphaned.length})</div>
          {orphaned.map((r) => (
            <div key={r.name} className="flex items-center gap-1.5 truncate text-[11px] text-slate-400">
              <code className="text-amber-200">{r.name}</code>
              <span>{r.paths.join(', ')}</span>
              {r.is_new && <NewBadge>NEW</NewBadge>}
              <span className="rounded border border-dashed border-amber-400/40 bg-amber-500/10 px-1 py-0.2 text-[9px] font-semibold text-amber-300">UNTESTED</span>
            </div>
          ))}
        </div>
      )}
    </nav>
  )
}
