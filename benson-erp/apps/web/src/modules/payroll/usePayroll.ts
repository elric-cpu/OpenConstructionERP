import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type {
  PayRateInput,
  PayrollExport,
  PayrollMappingInput,
  PayrollReconciliation,
  PayrollPeriod,
  PayrollPeriodInput,
  PayrollPeriodStatus,
  PayrollPreview,
  PayrollResultImport,
  PayrollResultLineInput,
  ReconciliationException,
} from "./types";

const periodsKey = ["payroll-periods"];

export function usePayrollPeriods() {
  return useQuery({
    queryKey: periodsKey,
    queryFn: () => api.get<PayrollPeriod[]>("/payroll/periods"),
  });
}

export function usePayrollPreview(period: PayrollPeriod | null) {
  return useQuery({
    queryKey: ["payroll-preview", period?.id, period?.version],
    queryFn: () => api.get<PayrollPreview>(`/payroll/periods/${period!.id}/preview`),
    enabled: Boolean(period),
  });
}

export function usePayrollExports(period: PayrollPeriod | null) {
  return useQuery({
    queryKey: ["payroll-exports", period?.id, period?.version],
    queryFn: () => api.get<PayrollExport[]>(`/payroll/periods/${period!.id}/exports`),
    enabled: Boolean(period),
  });
}

export function usePayrollResultImports(period: PayrollPeriod | null) {
  return useQuery({
    queryKey: ["payroll-result-imports", period?.id, period?.version],
    queryFn: () =>
      api.get<PayrollResultImport[]>(
        `/payroll/periods/${period!.id}/result-imports`,
      ),
    enabled: Boolean(
      period && ["PROCESSED", "RECONCILED"].includes(period.status),
    ),
  });
}

export function usePayrollReconciliation(result: PayrollResultImport | null) {
  return useQuery({
    queryKey: ["payroll-reconciliation", result?.id, result?.version],
    queryFn: () =>
      api.get<PayrollReconciliation>(
        `/payroll/result-imports/${result!.id}/reconciliation`,
      ),
    enabled: Boolean(result),
  });
}

function usePayrollMutation<T, V>(
  mutationFn: (variables: V) => Promise<T>,
  extraKeys: string[][] = [],
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: periodsKey });
      extraKeys.forEach((key) => void client.invalidateQueries({ queryKey: key }));
    },
  });
}

export function useCreatePayrollPeriod() {
  return usePayrollMutation((input: PayrollPeriodInput) =>
    api.post<PayrollPeriod>("/payroll/periods", input),
  );
}

export function useCreatePayRate() {
  return usePayrollMutation(
    (input: PayRateInput) => api.post("/payroll/pay-rates", input),
    [["payroll-preview"]],
  );
}

export function useCreatePayrollMapping() {
  return usePayrollMutation(
    (input: PayrollMappingInput) => api.post("/payroll/mappings", input),
    [["payroll-preview"]],
  );
}

export function useAdvancePayrollPeriod() {
  return usePayrollMutation(
    ({
      period,
      target,
      reason,
    }: {
      period: PayrollPeriod;
      target: PayrollPeriodStatus;
      reason: string;
    }) =>
      api.post<PayrollPeriod>(
        `/payroll/periods/${period.id}/transitions`,
        { target_status: target, reason },
        { "If-Match": String(period.version) },
      ),
    [["payroll-preview"]],
  );
}

export function useGeneratePayrollExport() {
  return usePayrollMutation(
    ({
      period,
      format,
      sensitive,
    }: {
      period: PayrollPeriod;
      format: PayrollExport["format"];
      sensitive: boolean;
    }) =>
      api.post<PayrollExport>(
        `/payroll/periods/${period.id}/exports`,
        { format, include_sensitive_fields: sensitive },
        { "If-Match": String(period.version) },
      ),
    [["payroll-exports"]],
  );
}

export function useImportPayrollResults() {
  return usePayrollMutation(
    ({
      period,
      payrollExport,
      providerReference,
      lines,
    }: {
      period: PayrollPeriod;
      payrollExport: PayrollExport;
      providerReference: string;
      lines: PayrollResultLineInput[];
    }) =>
      api.post<PayrollResultImport>(
        `/payroll/periods/${period.id}/result-imports`,
        {
          payroll_export_id: payrollExport.id,
          provider_reference: providerReference,
          lines,
        },
        { "If-Match": String(period.version) },
      ),
    [["payroll-result-imports"], ["payroll-reconciliation"]],
  );
}

export function useResolvePayrollException() {
  return usePayrollMutation(
    ({
      exception,
      reason,
    }: {
      exception: ReconciliationException;
      reason: string;
    }) =>
      api.post<ReconciliationException>(
        `/payroll/reconciliation-exceptions/${exception.id}/resolve`,
        { reason },
        { "If-Match": String(exception.version) },
      ),
    [["payroll-reconciliation"]],
  );
}

export function useReconcilePayrollResults() {
  return usePayrollMutation(
    (result: PayrollResultImport) =>
      api.post<PayrollResultImport>(
        `/payroll/result-imports/${result.id}/reconcile`,
        undefined,
        { "If-Match": String(result.version) },
      ),
    [["payroll-result-imports"], ["payroll-reconciliation"]],
  );
}

export async function downloadPayrollExport(payrollExport: PayrollExport) {
  const blob = await api.blob(`/payroll/exports/${payrollExport.id}/download`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = payrollExport.filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
