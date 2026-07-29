import { expect, test } from "vitest";

import {
  normalizeChargeCodeInput,
  normalizeInvoiceRequest,
  normalizeQualificationInput,
} from "./normalizeFederalInputs";

test("turns optional form blanks into API nulls", () => {
  const charge = normalizeChargeCodeInput({
    code: "CODE",
    name: "Authorized work",
    profile: "FEDERAL_FIXED_PRICE",
    agency_code: "USFS",
    contract_code: "CONTRACT",
    task_order: "",
    delivery_order: "",
    clin: "",
    slin: "",
    funding_line: "",
    project_id: "",
    cost_code: "",
    labor_category: "",
    active_from: "2026-07-01",
    active_to: "",
    required_qualification_code: "",
  });
  expect(charge.project_id).toBeNull();
  expect(charge.active_to).toBeNull();
  expect(charge.task_order).toBeNull();

  const qualification = normalizeQualificationInput({
    employee_id: "employee-id",
    qualification_code: "OSHA10",
    qualification_name: "OSHA 10",
    status: "ACTIVE",
    issuer: "",
    credential_number: "",
    evidence_document_id: "",
    effective_from: "2026-07-01",
    effective_to: "",
  });
  expect(qualification.evidence_document_id).toBeNull();
  expect(qualification.effective_to).toBeNull();
});

test("normalizes blank invoice filters without changing the required period", () => {
  expect(normalizeInvoiceRequest({
    contract_code: "CONTRACT",
    task_order: "",
    invoice_number: "",
    invoice_period_start: "2026-07-01",
    invoice_period_end: "2026-07-31",
  })).toEqual({
    contract_code: "CONTRACT",
    task_order: null,
    invoice_number: null,
    invoice_period_start: "2026-07-01",
    invoice_period_end: "2026-07-31",
  });
});
