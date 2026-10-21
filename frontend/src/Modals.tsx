import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Modal } from './ui'
import type { Config, Credential } from './types'

export function SettingsModal({ config, onSave, onClose }: {
  config: Config; onSave: (p: { oas_dir: string; kong_dir: string; verify_tls: boolean }) => Promise<void>; onClose: () => void
}) {
  const [oas, setOas] = useState(config.oas_dir)
  const [kong, setKong] = useState(config.kong_dir)
  const [tls, setTls] = useState(config.verify_tls)
  const [busy, setBusy] = useState(false)
  return (
    <Modal id="settings-modal" title="Local Directory Settings" onClose={onClose}>
      <div className="space-y-4">
        <label className="block text-xs font-medium text-slate-400">OAS_DIR (OpenAPI 3.x YAML/JSON)
          <input id="oas-dir-input" className="input mt-1 font-mono" value={oas} onChange={(e) => setOas(e.target.value)} />
        </label>
        <label className="block text-xs font-medium text-slate-400">KONG_DIR (decK / kong.yml)
          <input id="kong-dir-input" className="input mt-1 font-mono" value={kong} onChange={(e) => setKong(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={tls} onChange={(e) => setTls(e.target.checked)} /> Verify TLS certificates on execution
        </label>
        <p className="text-[11px] text-slate-500">Paths are read by the backend. Changes to files on disk are detected automatically.</p>
        <div className="flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button id="save-settings" className="btn btn-primary" disabled={busy}
            onClick={async () => { setBusy(true); await onSave({ oas_dir: oas, kong_dir: kong, verify_tls: tls }); setBusy(false); onClose() }}>
            Save &amp; Re-scan
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function CredentialsModal({ config, groups, onSave, onClose }: {
  config: Config; groups: string[]; onSave: (c: Credential[]) => Promise<void>; onClose: () => void
}) {
  const known = new Map(config.credentials.map((c) => [c.group, c]))
  const blank = (group: string): Credential => ({ group, username: '', password: '', token: '' })
  const initial: Credential[] = [
    ...groups.map((g) => known.get(g) ?? blank(g)),
    ...config.credentials.filter((c) => !groups.includes(c.group)),
  ]
  const [rows, setRows] = useState<Credential[]>(initial)
  const upd = (i: number, p: Partial<Credential>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...p } : r)))
  return (
    <Modal id="credentials-modal" title="Credential / ACL Manager" onClose={onClose} wide>
      <p className="mb-3 text-xs text-slate-400">
        Map Kong ACL consumer groups to test credentials (stored as JSON in the backend, <code>data/credentials.json</code>).
        key-auth → API key, jwt/oauth2 → bearer token, basic-auth → username &amp; password.
      </p>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <input className="input w-28 font-mono" placeholder="group" value={r.group} onChange={(e) => upd(i, { group: e.target.value })} />
            <input className="input w-28 font-mono" placeholder="username" value={r.username} onChange={(e) => upd(i, { username: e.target.value })} />
            <input className="input w-28 font-mono" type="password" placeholder="password" autoComplete="new-password" value={r.password} onChange={(e) => upd(i, { password: e.target.value })} />
            <input className="input flex-1 font-mono" placeholder="api key / bearer token" value={r.token} onChange={(e) => upd(i, { token: e.target.value })} />
            <button className="btn btn-ghost" aria-label="Remove" onClick={() => setRows(rows.filter((_, k) => k !== i))}><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-between">
        <button className="btn btn-ghost" onClick={() => setRows([...rows, blank('')])}><Plus size={14} /> Add group</button>
        <div className="flex gap-2">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button id="save-credentials" className="btn btn-primary"
            onClick={async () => { await onSave(rows.filter((r) => r.group.trim())); onClose() }}>Save</button>
        </div>
      </div>
    </Modal>
  )
}
