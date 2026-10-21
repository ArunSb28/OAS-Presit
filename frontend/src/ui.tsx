import type { ReactNode } from 'react'

const METHOD_STYLE: Record<string, string> = {
  GET: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30',
  POST: 'bg-sky-500/15 text-sky-300 border-sky-400/30',
  PUT: 'bg-amber-500/15 text-amber-300 border-amber-400/30',
  PATCH: 'bg-orange-500/15 text-orange-300 border-orange-400/30',
  DELETE: 'bg-rose-500/15 text-rose-300 border-rose-400/30',
}

export function MethodBadge({ method }: { method: string }) {
  return (
    <span className={`inline-block w-[3.6rem] shrink-0 rounded-md border px-1.5 py-0.5 text-center font-mono text-[10px] font-bold ${METHOD_STYLE[method] ?? 'bg-slate-500/15 text-slate-300 border-slate-400/30'}`}>
      {method}
    </span>
  )
}

export function Pill({ children, tone = 'slate', title }: { children: ReactNode; tone?: 'slate' | 'green' | 'red' | 'amber' | 'violet' | 'cyan'; title?: string }) {
  const tones = {
    slate: 'bg-white/5 text-slate-300 border-white/10',
    green: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30',
    red: 'bg-rose-500/15 text-rose-300 border-rose-400/30',
    amber: 'bg-amber-500/15 text-amber-300 border-amber-400/30',
    violet: 'bg-violet-500/15 text-violet-300 border-violet-400/30',
    cyan: 'bg-cyan-500/15 text-cyan-300 border-cyan-400/30',
  }
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function NewBadge({ children, title, tone = 'green' }: { children: ReactNode; title?: string; tone?: 'green' | 'cyan' }) {
  const c = tone === 'green'
    ? 'bg-emerald-500 text-white shadow-emerald-500/40'
    : 'bg-cyan-500 text-white shadow-cyan-500/40'
  return (
    <span title={title} className={`shrink-0 rounded px-1.5 py-px text-[9px] font-extrabold uppercase tracking-wide shadow-sm ${c}`}>
      {children}
    </span>
  )
}

export function TestStatusBadge({ status, title, compact = false }: { status: 'untested' | 'passed' | 'failed'; title?: string; compact?: boolean }) {
  if (status === 'passed') {
    return (
      <span title={title ?? 'Tested: all executed cases passed'} className="inline-flex shrink-0 items-center gap-1 rounded border border-emerald-400/30 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        {compact ? 'PASS' : 'PASSED'}
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span title={title ?? 'Tested: failures detected'} className="inline-flex shrink-0 items-center gap-1 rounded border border-rose-400/30 bg-rose-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-rose-300">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
        {compact ? 'FAIL' : 'FAILED'}
      </span>
    )
  }
  return (
    <span title={title ?? 'Route & API not yet tested'} className="inline-flex shrink-0 items-center gap-1 rounded border border-dashed border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-300/80">
      <span className="h-1.5 w-1.5 rounded-full bg-amber-400/70" />
      {compact ? 'UNTESTED' : 'UNTESTED'}
    </span>
  )
}

export function statusTone(code?: number): 'green' | 'amber' | 'red' | 'slate' {
  if (!code) return 'slate'
  if (code < 300) return 'green'
  if (code < 500) return 'amber'
  return 'red'
}

export function Modal({ id, title, onClose, children, wide }: { id: string; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <dialog
      id={id}
      ref={(el) => { if (el && !el.open) el.showModal() }}
      onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      className={`glass m-auto w-full ${wide ? 'max-w-3xl' : 'max-w-xl'} rounded-2xl bg-ink-800/95 p-0 shadow-2xl`}
    >
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        <button className="btn btn-ghost" onClick={onClose} aria-label="Close dialog">✕</button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  )
}
