import { useCallback, useEffect, useState } from 'react';
import { Globe } from 'lucide-react';
import { api } from '../services/api';
type Network = { ip: string | null; country: string | null; city: string | null; isp: string | null; checked_at: string | null; stale: boolean; error: string | null };
export default function NetworkStatus() {
  const [data, setData] = useState<Network | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const load = useCallback(async () => {
    setBusy(true);
    try { setData(await api<Network>('/network')); setFailed(false); }
    catch { setFailed(true); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const stale = failed || data?.stale;
  return <section className="network-status" aria-label="Server connection">
    <div className="network-status-heading"><Globe size={14}/><span>Server connection</span>

    </div>
    <div title="Public outbound IP of Magpie’s server/container, not your browser. Location is approximate. Split routing and IPv4/IPv6 can produce different IPs for other destinations. This does not verify whether a VPN is enabled.">
      <code>{data?.ip || (busy ? 'Checking…' : 'IP unavailable')}</code>
      {data?.ip && <><p>{[data.city, data.country].filter(Boolean).join(', ')}</p>{data.isp && <p>{data.isp}</p>}</>}
      {stale && <p className="network-stale" role="status">{data?.ip ? 'Last known connection · refresh unavailable' : 'Network lookup unavailable'}</p>}
    </div>
  </section>;
}
