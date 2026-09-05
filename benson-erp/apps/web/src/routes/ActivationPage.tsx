import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import type { EmployeeActivationCompletion } from "../modules/auth/types";
import {
  useCompleteEmployeeActivation,
  useInspectEmployeeActivation,
} from "../modules/auth/useEmployeeActivation";

const genericError = "This activation link is invalid or no longer available.";
const schema = z
  .object({
    password: z.string().min(12, "Password must contain at least 12 characters"),
    confirmation: z.string().min(1, "Confirm your password"),
  })
  .refine((fields) => fields.password === fields.confirmation, {
    message: "Passwords do not match",
    path: ["confirmation"],
  });
type Fields = z.infer<typeof schema>;

function consumeActivationToken() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const token = fragment.get("token")?.trim() ?? "";
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  return token;
}

export function ActivationPage() {
  const [token] = useState(consumeActivationToken);
  const [result, setResult] = useState<EmployeeActivationCompletion | null>(null);
  const inspect = useInspectEmployeeActivation(token);
  const complete = useCompleteEmployeeActivation();
  const form = useForm<Fields>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirmation: "" },
  });

  const submit = form.handleSubmit(async ({ password }) => {
    try {
      setResult(await complete.mutateAsync({ token, password }));
      form.reset();
    } catch {
      // The generic message avoids exposing token state or whether an employee exists.
    }
  });

  const invalid = !token || inspect.isError || complete.isError;
  const loading = Boolean(token) && inspect.isPending;

  return (
    <main className="activation-shell">
      <section className="activation-brand" aria-labelledby="activation-title">
        <p className="eyebrow">Benson Enterprises</p>
        <h1 id="activation-title">Welcome to the crew.</h1>
        <p>Your company account is the secure front door to schedules, jobs, time, and training.</p>
        <div className="activation-mark" aria-hidden="true">BE</div>
      </section>
      <section className="activation-panel" aria-live="polite">
        {loading && <p className="activation-wait">Checking your secure invitation…</p>}
        {invalid && !loading && (
          <div className="activation-state">
            <p className="eyebrow">Account activation</p>
            <h2>We could not open this invitation</h2>
            <div className="alert" role="alert">{genericError}</div>
            <p>Ask your manager to send a new activation email.</p>
            <Link className="quiet activation-link" to="/login">Return to sign in</Link>
          </div>
        )}
        {inspect.data && !invalid && !result && (
          <form className="activation-form" onSubmit={submit} noValidate>
            <p className="eyebrow">Secure account setup</p>
            <h2>Set your ERP password</h2>
            <p className="activation-greeting">Hello, <strong>{inspect.data.employee_name}</strong>.</p>
            <dl className="activation-details">
              <div><dt>Company</dt><dd>{inspect.data.organization_name}</dd></div>
              <div><dt>Work email</dt><dd>{inspect.data.company_email}</dd></div>
              <div><dt>Invitation expires</dt><dd><time dateTime={inspect.data.expires_at}>{new Date(inspect.data.expires_at).toLocaleString()}</time></dd></div>
            </dl>
            <label>
              Create password
              <input autoComplete="new-password" type="password" {...form.register("password")} />
              <span className="field-error">{form.formState.errors.password?.message}</span>
            </label>
            <label>
              Confirm password
              <input autoComplete="new-password" type="password" {...form.register("confirmation")} />
              <span className="field-error">{form.formState.errors.confirmation?.message}</span>
            </label>
            <p className="field-note">Use at least 12 characters. A long, unique passphrase works well.</p>
            <button className="primary" disabled={complete.isPending} type="submit">
              {complete.isPending ? "Activating account…" : "Activate account"}
            </button>
          </form>
        )}
        {result && (
          <div className="activation-state activation-success">
            <p className="eyebrow">Account ready</p>
            <h2>You’re all set</h2>
            <p>Your Benson ERP account for <strong>{result.email}</strong> is active.</p>
            <Link className="primary activation-link" to="/login">Continue to sign in</Link>
          </div>
        )}
      </section>
    </main>
  );
}
