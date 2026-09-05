import type { FederalChargeCode } from "../federal-labor/types";
import type { TimeFormFields } from "./types";

export type CanonicalFederalAllocation = Pick<
  TimeFormFields,
  | "federal_charge_code_id"
  | "project_id"
  | "charge_code"
  | "contract_code"
  | "task_order"
  | "clin"
  | "funding_line"
  | "cost_code"
  | "labor_category"
>;

export function canonicalFederalAllocation(
  code: FederalChargeCode | undefined,
): CanonicalFederalAllocation {
  return {
    federal_charge_code_id: code?.id ?? "",
    project_id: code?.project_id ?? "",
    charge_code: code?.code ?? "DIRECT-PROJECT",
    contract_code: code?.contract_code ?? "",
    task_order: code?.task_order ?? "",
    clin: code?.clin ?? "",
    funding_line: code?.funding_line ?? "",
    cost_code: code?.cost_code ?? "",
    labor_category: code?.labor_category ?? "",
  };
}
