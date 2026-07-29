import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../app/AuthContext";
import {
  FederalChargeCodePanel,
  FederalRateQualificationPanel,
} from "../modules/federal-labor/FederalSetupPanels";
import {
  FederalInvoicePanel,
  FloorCheckPanel,
  type FloorCheckFilters,
} from "../modules/federal-labor/FederalReports";
import {
  useCreateEmployeeQualification,
  useCreateFederalChargeCode,
  useCreateFederalLaborRate,
  useEmployeeQualifications,
  useFederalChargeCodes,
  useFederalLaborRates,
  useFloorCheck,
  useGenerateFederalInvoice,
  usePreviewFederalInvoice,
} from "../modules/federal-labor/useFederalLabor";
import { useScheduleResources } from "../modules/scheduling/useScheduling";

type View = "codes" | "eligibility" | "reports";

function initialFloorCheckFilters(): FloorCheckFilters {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), 1);
  return {
    period_start: start.toISOString().slice(0, 10),
    period_end: end.toISOString().slice(0, 10),
    contract_code: "",
  };
}

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "The federal labor request failed.";
}

export function FederalLaborPage() {
  const auth = useAuth();
  const [view, setView] = useState<View>("codes");
  const [filters, setFilters] = useState<FloorCheckFilters>(initialFloorCheckFilters);
  const codes = useFederalChargeCodes();
  const rates = useFederalLaborRates();
  const qualifications = useEmployeeQualifications();
  const resources = useScheduleResources();
  const floorCheck = useFloorCheck(
    filters.period_start,
    filters.period_end,
    filters.contract_code,
  );
  const createCode = useCreateFederalChargeCode();
  const createRate = useCreateFederalLaborRate();
  const createQualification = useCreateEmployeeQualification();
  const preview = usePreviewFederalInvoice();
  const generate = useGenerateFederalInvoice();
  const mutations = [createCode, createRate, createQualification, preview, generate];
  const error =
    codes.error ??
    rates.error ??
    qualifications.error ??
    resources.employees.error ??
    resources.projects.error ??
    floorCheck.error ??
    mutations.find((item) => item.error)?.error;
  const pending = mutations.some((item) => item.isPending);

  return (
    <main className="workspace-shell federal-shell">
      <header className="topbar">
        <div><p className="eyebrow">Benson Construction ERP</p><h1>Federal labor control</h1></div>
        <div className="header-actions">
          <Link className="quiet" to="/time">Time</Link>
          <Link className="quiet" to="/payroll">Payroll</Link>
          <Link className="quiet" to="/schedule">Schedule</Link>
          <button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button>
        </div>
      </header>
      <section className="federal-command">
        <div>
          <p className="eyebrow">Labor accounting chain</p>
          <p>Authorize work, prove employee eligibility, reconcile approved labor, and preserve invoice support without mixing pay rates and contract bill rates.</p>
        </div>
        <nav aria-label="Federal labor workspace">
          <button className={view === "codes" ? "active" : ""} onClick={() => setView("codes")} type="button">Charge codes</button>
          <button className={view === "eligibility" ? "active" : ""} onClick={() => setView("eligibility")} type="button">Rates & eligibility</button>
          <button className={view === "reports" ? "active" : ""} onClick={() => setView("reports")} type="button">Floor check & invoices</button>
        </nav>
      </section>
      {error && <div className="alert" role="alert">{message(error)}</div>}
      {view === "codes" && (
        <FederalChargeCodePanel
          codes={codes.data ?? []}
          onCreate={createCode.mutateAsync}
          pending={pending}
          projects={resources.projects.data ?? []}
        />
      )}
      {view === "eligibility" && (
        <FederalRateQualificationPanel
          codes={codes.data ?? []}
          employees={resources.employees.data ?? []}
          qualifications={qualifications.data ?? []}
          onQualification={createQualification.mutateAsync}
          onRate={createRate.mutateAsync}
          pending={pending}
          rates={rates.data ?? []}
        />
      )}
      {view === "reports" && (
        <div className="federal-report-stack">
          <FloorCheckPanel
            filters={filters}
            loading={floorCheck.isFetching}
            onFilters={setFilters}
            report={floorCheck.data}
          />
          <FederalInvoicePanel
            artifact={generate.data}
            codes={codes.data ?? []}
            onGenerate={generate.mutateAsync}
            onPreview={preview.mutateAsync}
            pending={preview.isPending || generate.isPending}
            preview={preview.data}
            previewRequest={preview.variables}
          />
        </div>
      )}
    </main>
  );
}
