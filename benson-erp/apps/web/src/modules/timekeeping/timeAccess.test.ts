import { expect, test } from "vitest";

import { canApproveEntry, canCertifyEntry, timeAccess } from "./timeAccess";

test("keeps employee self service separate from team authority", () => {
  expect(timeAccess(["time.enter_own", "time.certify_own"])).toEqual({
    canApproveTeam: false,
    canEnterTeam: false,
  });
  expect(timeAccess(["time.enter_team", "time.approve_team"])).toEqual({
    canApproveTeam: true,
    canEnterTeam: true,
  });
});

test("exposes certification only for self and approval only for supervisors", () => {
  const employee = timeAccess(["time.enter_own", "time.certify_own"]);
  const supervisor = timeAccess(["time.enter_team", "time.approve_team"]);
  const ownDraft = { employee_id: "employee-1", status: "DRAFT" };
  const otherDraft = { employee_id: "employee-2", status: "DRAFT" };
  const certified = { employee_id: "employee-1", status: "CERTIFIED" };

  expect(canCertifyEntry(ownDraft, "employee-1")).toBe(true);
  expect(canCertifyEntry(otherDraft, "employee-1")).toBe(false);
  expect(canApproveEntry(certified, employee)).toBe(false);
  expect(canApproveEntry(certified, supervisor)).toBe(true);
});
