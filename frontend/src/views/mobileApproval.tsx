import { useEffect, useState } from 'react'
import qrcode from 'qrcode-generator'
import { api } from '../services/api'

export function qrDataUrl(text: string): string {
  const qr = qrcode(0, 'M')
  qr.addData(text)
  qr.make()
  return qr.createDataURL(4, 2)
}

/** QR code for approving the pending defense from a phone on the same network (one-time token). */
export function MobileApprovalQR({ runId }: { runId: string }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    const tick = () => api.approvalStatus(runId).then((a) => { if (alive) setUrl(a.pending ? a.mobile_url ?? null : null) }).catch(() => undefined)
    void tick()
    const iv = setInterval(() => void tick(), 2000)
    return () => { alive = false; clearInterval(iv) }
  }, [runId])
  if (!url) return null
  return (
    <div className="mt-3 flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-900/70 p-2">
      <img src={qrDataUrl(url)} alt="QR code to approve from a phone" className="h-24 w-24 rounded bg-white p-1" />
      <p className="text-[11px] text-slate-300">
        <b className="text-amber-200">Approve from your phone.</b> Scan on the same Wi-Fi. The link holds a one-time token that
        dies when this decision is made or times out. Same policy gate, same audit trail (logged as “via mobile”).
      </p>
    </div>
  )
}
