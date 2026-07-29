import { expect, test } from "vitest";

import type { FederalChargeCode } from "../federal-labor/types";
import { canonicalFederalAllocation } from "./federalAllocation";

const code: FederalChargeCode = {
  id: "code-id",
  code: "USFS-TO7-CLIN1",
  name: "Trailhead reconstruction",
  profile: "FEDERAL_TIME_AND_MATERIALS",
  agency_code: "USFS",
  contract_code: "1204H1-26-C-0042",
  task_order: "TO-0007",
  delivery_order: null,
  clin: "0001",
  slin: null,
  funding_line: "FL-02",
  project_id: "project-id",
  cost_code: "03-100",
  labor_category: "Carpenter II",
  active_from: "2026-07-01",
  active_to: null,
  required_qualification_code: "OSHA10",
  status: "OPEN",
  closed_at: null,
  closed_by: null,
  closed_reason: null,
  version: 1,
};

test("copies the authorized federal hierarchy into a time allocation", () => {
  expect(canonicalFederalAllocation(code)).toEqual({
    federal_charge_code_id: "code-id",
    project_id: "project-id",
    charge_code: "USFS-TO7-CLIN1",
    contract_code: "1204H1-26-C-0042",
    task_order: "TO-0007",
    clin: "0001",
    funding_line: "FL-02",
    cost_code: "03-100",
    labor_category: "Carpenter II",
  });
});

test("clearing federal authorization restores the commercial allocation", () => {
  expect(canonicalFederalAllocation(undefined)).toEqual({
    federal_charge_code_id: "",
    project_id: "",
    charge_code: "DIRECT-PROJECT",
    contract_code: "",
    task_order: "",
    clin: "",
    funding_line: "",
    cost_code: "",
    labor_category: "",
  });
});
