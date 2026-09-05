from dataclasses import dataclass
from enum import StrEnum

from .domain import Role


class ActionRisk(StrEnum):
    INTERNAL = "internal"
    EXTERNAL_SEND = "external_send"
    FINANCIAL = "financial"
    SIGNATURE = "signature"
    LEGAL = "legal"
    DESTRUCTIVE = "destructive"


CONFIRMATION_RISKS = {
    ActionRisk.EXTERNAL_SEND,
    ActionRisk.FINANCIAL,
    ActionRisk.SIGNATURE,
    ActionRisk.LEGAL,
    ActionRisk.DESTRUCTIVE,
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    confirmation_required: bool
    reason: str


def evaluate_agent_action(role: Role, risk: ActionRisk) -> PolicyDecision:
    if (
        role in {Role.CUSTOMER, Role.SUBCONTRACTOR, Role.FIELD}
        and risk != ActionRisk.INTERNAL
    ):
        return PolicyDecision(False, False, "Role cannot request this action class")
    if risk in CONFIRMATION_RISKS:
        return PolicyDecision(
            True, True, "Human confirmation required by Benson action policy"
        )
    return PolicyDecision(
        True, False, "Internal action allowed within role permissions"
    )
