import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type {
  EmployeeQualification,
  EmployeeQualificationInput,
  FederalChargeCode,
  FederalChargeCodeInput,
  FederalInvoicePreview,
  FederalInvoiceRequest,
  FederalInvoiceSupport,
  FederalLaborRate,
  FederalLaborRateInput,
  FloorCheckReport,
} from "./types";
import {
  normalizeChargeCodeInput,
  normalizeInvoiceRequest,
  normalizeQualificationInput,
  normalizeRateInput,
} from "./normalizeFederalInputs";

const federalKey = ["federal-labor"];
const chargeCodesKey = [...federalKey, "charge-codes"];

export function useFederalChargeCodes() {
  return useQuery({
    queryKey: chargeCodesKey,
    queryFn: () => api.get<FederalChargeCode[]>("/federal-labor/charge-codes"),
  });
}

export function useFederalLaborRates() {
  return useQuery({
    queryKey: [...federalKey, "rates"],
    queryFn: () => api.get<FederalLaborRate[]>("/federal-labor/rates"),
  });
}

export function useEmployeeQualifications() {
  return useQuery({
    queryKey: [...federalKey, "qualifications"],
    queryFn: () =>
      api.get<EmployeeQualification[]>("/federal-labor/qualifications"),
  });
}

export function useFloorCheck(
  periodStart: string,
  periodEnd: string,
  contractCode: string,
) {
  const params = new URLSearchParams({
    period_start: periodStart,
    period_end: periodEnd,
  });
  if (contractCode) params.set("contract_code", contractCode);
  return useQuery({
    queryKey: [...federalKey, "floor-check", periodStart, periodEnd, contractCode],
    queryFn: () =>
      api.get<FloorCheckReport>(`/federal-labor/floor-check?${params.toString()}`),
    enabled: Boolean(periodStart && periodEnd),
  });
}

function useFederalMutation<T, V>(mutationFn: (input: V) => Promise<T>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => client.invalidateQueries({ queryKey: federalKey }),
  });
}

export function useCreateFederalChargeCode() {
  return useFederalMutation((input: FederalChargeCodeInput) =>
    api.post<FederalChargeCode>(
      "/federal-labor/charge-codes",
      normalizeChargeCodeInput(input),
    ),
  );
}

export function useCreateFederalLaborRate() {
  return useFederalMutation((input: FederalLaborRateInput) =>
    api.post<FederalLaborRate>("/federal-labor/rates", normalizeRateInput(input)),
  );
}

export function useCreateEmployeeQualification() {
  return useFederalMutation((input: EmployeeQualificationInput) =>
    api.post<EmployeeQualification>(
      "/federal-labor/qualifications",
      normalizeQualificationInput(input),
    ),
  );
}

export function usePreviewFederalInvoice() {
  return useMutation({
    mutationFn: (input: FederalInvoiceRequest) =>
      api.post<FederalInvoicePreview>(
        "/federal-labor/invoice-support/preview",
        normalizeInvoiceRequest(input),
      ),
  });
}

export function useGenerateFederalInvoice() {
  return useFederalMutation((input: FederalInvoiceRequest) =>
    api.post<FederalInvoiceSupport>(
      "/federal-labor/invoice-support",
      normalizeInvoiceRequest(input),
    ),
  );
}
