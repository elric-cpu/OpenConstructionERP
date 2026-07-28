import { useEffect, useState } from "react";
import { IdentityProvisioningPanel } from "./IdentityProvisioningPanel";
import { onboardingApi } from "./onboardingApi";
import type { OnboardingEmployee } from "./onboardingTypes";
import { useIdentityProvisioning } from "./useIdentityProvisioning";

export function EmployeeIdentitySection({
  credential,
  employee,
  onEmployeeChanged,
}: {
  credential: string;
  employee: OnboardingEmployee;
  onEmployeeChanged(): Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const identity = useIdentityProvisioning({
    credential,
    onEmployeeChanged,
    onError: setError,
    selected: employee,
    setSaving: setBusy,
  });

  useEffect(() => {
    identity.loadCommands(employee.id).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Identity status unavailable");
    });
  }, [employee.id, identity.loadCommands]);

  const inviteContractor = async (record: OnboardingEmployee) => {
    setBusy(true);
    setError("");
    try {
      await onboardingApi.inviteEmployee(credential, record);
      await onEmployeeChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invitation could not be queued");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <p className="form-error">{error}</p>}
      <IdentityProvisioningPanel
        busy={busy}
        commands={identity.commands}
        employee={employee}
        onApprove={identity.approveIdentity}
        onCredential={identity.submitCredential}
        onInvite={inviteContractor}
        onRefresh={(record) => identity.loadCommands(record.id).then(() => undefined)}
      />
    </>
  );
}
