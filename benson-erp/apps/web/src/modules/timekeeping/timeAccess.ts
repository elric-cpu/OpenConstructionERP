export type TimeAccess = {
  canApproveTeam: boolean;
  canEnterTeam: boolean;
};

export function timeAccess(permissions: string[]): TimeAccess {
  return {
    canApproveTeam: permissions.includes("time.approve_team"),
    canEnterTeam: permissions.includes("time.enter_team"),
  };
}

export function canCertifyEntry(
  entry: { employee_id: string; status: string },
  ownEmployeeId: string | undefined,
) {
  return entry.status === "DRAFT" && entry.employee_id === ownEmployeeId;
}

export function canApproveEntry(
  entry: { status: string },
  access: TimeAccess,
) {
  return entry.status === "CERTIFIED" && access.canApproveTeam;
}
