import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";

type Session = {
  id: string;
  device_name: string | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};
type Enrollment = { secret: string; provisioning_uri: string; recovery_codes: string[] };

export function SecurityPage() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/auth/sessions") });
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [code, setCode] = useState("");
  const enroll = useMutation({
    mutationFn: () => api.post<Enrollment>("/auth/mfa/enroll"),
    onSuccess: setEnrollment,
  });
  const confirm = useMutation({
    mutationFn: () => api.post<void>("/auth/mfa/confirm", { code }),
    onSuccess: () => setEnrollment(null),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/auth/sessions/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  return <main className="workspace-shell">
    <header className="topbar"><div><p className="eyebrow">Account protection</p><h1>Security</h1></div><Link className="quiet" to="/sales/new">Back to sales</Link></header>
    <section className="form-card security-section"><h2>Multi-factor authentication</h2>
      {!enrollment ? <><p>Use an authenticator app for a second factor at every password sign-in.</p><button className="primary" disabled={enroll.isPending} onClick={() => enroll.mutate()} type="button">Set up authenticator</button></> : <div className="enrollment">
        <p>Scan this provisioning URI in your authenticator app, or enter the secret manually.</p>
        <code>{enrollment.provisioning_uri}</code><code>{enrollment.secret}</code>
        <h3>Recovery codes</h3><p>Store these once in a secure password manager. Each code works one time.</p>
        <ul className="recovery-codes">{enrollment.recovery_codes.map((item) => <li key={item}><code>{item}</code></li>)}</ul>
        <label>Authenticator code<input autoComplete="one-time-code" inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} /></label>
        <button className="primary" disabled={code.length < 6 || confirm.isPending} onClick={() => confirm.mutate()} type="button">Confirm and enable MFA</button>
      </div>}
    </section>
    <section className="form-card security-section"><h2>Signed-in devices</h2>
      {sessions.isLoading && <p>Loading sessions…</p>}
      {sessions.error && <div className="alert">Could not load sessions.</div>}
      <ul className="session-list">{sessions.data?.map((item) => <li key={item.id}><div><strong>{item.device_name || "Unknown device"}{item.current && " (current)"}</strong><span>{item.ip_address || "Unknown address"} · Last active {new Date(item.last_seen_at).toLocaleString()}</span></div><button className="quiet" disabled={revoke.isPending} onClick={() => revoke.mutate(item.id)} type="button">Revoke</button></li>)}</ul>
    </section>
  </main>;
}
