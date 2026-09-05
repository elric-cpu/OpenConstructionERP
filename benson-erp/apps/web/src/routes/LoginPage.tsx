import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "../app/AuthContext";

const schema = z.object({
  organization: z.string().min(1, "Organization is required"),
  email: z.email("Enter a valid email"),
  password: z.string().min(12, "Password must contain at least 12 characters"),
});
type Fields = z.infer<typeof schema>;

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const form = useForm<Fields>({
    resolver: zodResolver(schema),
    defaultValues: { organization: "benson-enterprises", email: "", password: "" },
  });

  const submit = form.handleSubmit(async (fields) => {
    setError(null);
    try {
      const challenge = await auth.login({ ...fields, device_name: navigator.userAgent });
      if (challenge) {
        setMfaChallenge(challenge);
        return;
      }
      navigate("/sales/new");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign in failed");
    }
  });

  async function verifyMfa() {
    setError(null);
    try {
      await auth.verifyMfa(mfaChallenge!, mfaCode);
      navigate("/sales/new");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Verification failed");
    }
  }

  return (
    <main className="login-shell">
      <section className="brand-panel">
        <p className="eyebrow">Benson Enterprises</p>
        <h1>Construction work, connected.</h1>
        <p>Manage the job from the first call through a funded, scheduled project.</p>
      </section>
      <form className="login-card" onSubmit={submit} noValidate>
        <p className="eyebrow">Secure access</p>
        <h2>Sign in to the ERP</h2>
        {!mfaChallenge && <label>
          Organization
          <input autoComplete="organization" {...form.register("organization")} />
          <span className="field-error">{form.formState.errors.organization?.message}</span>
        </label>}
        {!mfaChallenge && <label>
          Work email
          <input autoComplete="username" type="email" {...form.register("email")} />
          <span className="field-error">{form.formState.errors.email?.message}</span>
        </label>}
        {!mfaChallenge && <label>
          Password
          <input autoComplete="current-password" type="password" {...form.register("password")} />
          <span className="field-error">{form.formState.errors.password?.message}</span>
        </label>}
        {mfaChallenge && <label>
          Authentication or recovery code
          <input autoComplete="one-time-code" inputMode="numeric" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} />
        </label>}
        {error && <div className="alert">{error}</div>}
        {!mfaChallenge ? <button className="primary" disabled={form.formState.isSubmitting} type="submit">
          {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
        </button> : <button className="primary" disabled={mfaCode.length < 6} onClick={verifyMfa} type="button">Verify code</button>}
      </form>
    </main>
  );
}
