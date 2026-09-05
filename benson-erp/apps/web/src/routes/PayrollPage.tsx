import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../app/AuthContext";
import { PayrollPeriodPanel } from "../modules/payroll/PayrollPeriodPanel";
import { PayrollReviewPanel } from "../modules/payroll/PayrollReviewPanel";
import {
  PayrollReconciliationPanel,
  PayrollResultImportPanel,
} from "../modules/payroll/PayrollReconciliationPanel";
import { PayrollSetupPanel } from "../modules/payroll/PayrollSetupPanel";
import type { PayrollExport, PayrollPeriod, PayrollPeriodStatus } from "../modules/payroll/types";
import {
  downloadPayrollExport,
  useAdvancePayrollPeriod,
  useCreatePayrollMapping,
  useCreatePayrollPeriod,
  useCreatePayRate,
  useGeneratePayrollExport,
  useImportPayrollResults,
  usePayrollReconciliation,
  usePayrollResultImports,
  usePayrollExports,
  usePayrollPeriods,
  usePayrollPreview,
  useReconcilePayrollResults,
  useResolvePayrollException,
} from "../modules/payroll/usePayroll";
import { useScheduleResources } from "../modules/scheduling/useScheduling";

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "The payroll request could not be completed.";
}

export function PayrollPage() {
  const auth = useAuth();
  const periods = usePayrollPeriods();
  const resources = useScheduleResources();
  const createPeriod = useCreatePayrollPeriod();
  const createRate = useCreatePayRate();
  const createMapping = useCreatePayrollMapping();
  const advance = useAdvancePayrollPeriod();
  const generate = useGeneratePayrollExport();
  const importResults = useImportPayrollResults();
  const resolveException = useResolvePayrollException();
  const reconcileResults = useReconcilePayrollResults();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sensitive, setSensitive] = useState(false);
  const selected = periods.data?.find((item) => item.id === selectedId) ?? periods.data?.[0] ?? null;
  const preview = usePayrollPreview(selected);
  const exportsQuery = usePayrollExports(selected);
  const resultImports = usePayrollResultImports(selected);
  const currentResult = resultImports.data?.[0] ?? null;
  const reconciliation = usePayrollReconciliation(currentResult);
  const mutations = [createPeriod, createRate, createMapping, advance, generate, importResults, resolveException, reconcileResults];
  const error = periods.error ?? resources.employees.error ?? resources.projects.error ?? preview.error ?? exportsQuery.error ?? resultImports.error ?? reconciliation.error ?? mutations.find((item) => item.error)?.error;
  const pending = mutations.some((item) => item.isPending);

  async function advanceTo(target: PayrollPeriodStatus) {
    if (!selected) return;
    await advance.mutateAsync({
      period: selected,
      target,
      reason: target === "LOCKED" ? "Payroll validation reviewed and period locked." : "Payroll review stage completed.",
    });
  }

  async function generateFormat(format: PayrollExport["format"]) {
    if (!selected) return;
    await generate.mutateAsync({ period: selected, format, sensitive });
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div><p className="eyebrow">Benson Construction ERP</p><h1>Payroll review</h1></div>
        <div className="header-actions">
          <Link className="quiet" to="/federal-labor">Federal labor</Link>
          <Link className="quiet" to="/time">Time</Link>
          <Link className="quiet" to="/schedule">Schedule</Link>
          <Link className="quiet" to="/employees">Employees</Link>
          <button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button>
        </div>
      </header>
      <p className="page-intro">Validate approved time, resolve provider mappings, lock the period, and generate checksum-protected payroll files with source drill-down.</p>
      {error && <div className="alert" role="alert">{errorMessage(error)}</div>}
      <div className="payroll-layout">
        <PayrollPeriodPanel
          onCreate={(input) => createPeriod.mutateAsync(input)}
          onSelect={(period: PayrollPeriod) => setSelectedId(period.id)}
          pending={createPeriod.isPending}
          periods={periods.data ?? []}
          selected={selected}
        />
        <div className="payroll-main">
          {periods.isLoading && <section className="form-card">Loading payroll periods…</section>}
          {!periods.isLoading && !selected && <section className="form-card"><h2>Create the first payroll period</h2><p>Time must be employee-certified and supervisor-approved before the period can lock.</p></section>}
          {selected && (
            <>
              <PayrollReviewPanel
                exports={exportsQuery.data ?? []}
                onAdvance={advanceTo}
                onDownload={downloadPayrollExport}
                onGenerate={generateFormat}
                onSensitive={setSensitive}
                pending={pending}
                period={selected}
                preview={preview.data}
                sensitive={sensitive}
              />
              {selected.status === "EXPORTED" && !currentResult && (
                <PayrollResultImportPanel
                  exports={exportsQuery.data ?? []}
                  onImport={(payrollExport, providerReference, lines) =>
                    importResults.mutateAsync({
                      period: selected,
                      payrollExport,
                      providerReference,
                      lines,
                    })
                  }
                  pending={pending}
                  period={selected}
                />
              )}
              {currentResult && (
                <PayrollReconciliationPanel
                  onReconcile={() => reconcileResults.mutateAsync(currentResult)}
                  onResolve={(exception, reason) =>
                    resolveException.mutateAsync({ exception, reason })
                  }
                  pending={pending}
                  reconciliation={reconciliation.data}
                  result={currentResult}
                />
              )}
              {!["LOCKED", "EXPORTED", "PROCESSED", "RECONCILED"].includes(selected.status) && (
                <PayrollSetupPanel
                  employees={resources.employees.data ?? []}
                  onMapping={(input) => createMapping.mutateAsync(input)}
                  onPayRate={(input) => createRate.mutateAsync(input)}
                  pending={pending}
                  period={selected}
                  projects={resources.projects.data ?? []}
                />
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
