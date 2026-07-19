import { useCallback, useState } from "react";
import { onboardingApi } from "./onboardingApi";
import type { IdentityProvisioningCommand, OnboardingEmployee } from "./onboardingTypes";

export function useIdentityProvisioning({
  credential,
  onEmployeeChanged,
  onError,
  selected,
  setSaving,
}: {
  credential: string;
  onEmployeeChanged(): Promise<unknown>;
  onError(message: string): void;
  selected: OnboardingEmployee | null;
  setSaving(saving: boolean): void;
}) {
  const [commands, setCommands] = useState<IdentityProvisioningCommand[]>([]);

  const loadCommands = useCallback(
    async (employeeId: string) => {
      const next = await onboardingApi.listIdentityCommands(credential, employeeId);
      setCommands(next);
      return next;
    },
    [credential],
  );

  const requestIdentity = useCallback(async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const key = `identity-${selected.id}-${crypto.randomUUID()}`;
      const command = await onboardingApi.requestIdentity(credential, selected, key);
      setCommands((current) => [command, ...current]);
      await onEmployeeChanged();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Identity provisioning could not be requested");
    } finally {
      setSaving(false);
    }
  }, [credential, onEmployeeChanged, onError, selected, setSaving]);

  const replaceCommand = useCallback((command: IdentityProvisioningCommand) => {
    setCommands((current) => current.map((item) => (item.id === command.id ? command : item)));
  }, []);

  const approveIdentity = useCallback(
    async (command: IdentityProvisioningCommand) => {
      setSaving(true);
      try {
        replaceCommand(await onboardingApi.approveIdentity(credential, command));
      } catch (reason) {
        onError(reason instanceof Error ? reason.message : "Identity provisioning approval failed");
      } finally {
        setSaving(false);
      }
    },
    [credential, onError, replaceCommand, setSaving],
  );

  const confirmIdentity = useCallback(
    async (command: IdentityProvisioningCommand, reason: string, evidenceReference: string) => {
      setSaving(true);
      try {
        replaceCommand(await onboardingApi.confirmIdentity(credential, command, reason, evidenceReference));
        await onEmployeeChanged();
      } catch (reasonCaught) {
        onError(reasonCaught instanceof Error ? reasonCaught.message : "Identity verification confirmation failed");
      } finally {
        setSaving(false);
      }
    },
    [credential, onEmployeeChanged, onError, replaceCommand, setSaving],
  );

  const clearCommands = useCallback(() => setCommands([]), []);
  return { approveIdentity, clearCommands, commands, confirmIdentity, loadCommands, requestIdentity };
}
