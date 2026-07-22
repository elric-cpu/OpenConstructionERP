from typing import Any

from app.config import Settings
from app.auth import Principal
from app.directory_provider import DirectoryIdentity
from app.domain import Role
from app.identity_provisioning_store import IdentityProvisioningStore
from app.identity_provisioning_worker import IdentityProvisioningWorker
from app.notifications import _email_message
from app.onboarding_domain import EmployeeCreate
from app.onboarding_lifecycle_store import OnboardingLifecycleStore
from app.new_hire_routes import create_employee
from app.object_storage import read_employee_document, store_employee_document
from app.signing import employee_invite_token
from app.storage import operations_store


class VerifiedDirectory:
    def create_identity(self, **values: str) -> DirectoryIdentity:
        return DirectoryIdentity(
            "google-user-1",
            values["primary_email"],
            values["org_unit_path"],
            False,
            "verified",
            bootstrap_password="Temp-Password-123",
        )

    def verify_identity(self, **values: str) -> DirectoryIdentity:
        return DirectoryIdentity(
            "google-user-1",
            values["primary_email"],
            values["org_unit_path"],
            False,
            "verified",
        )

    def suspend_identity(self, **_values: str) -> DirectoryIdentity:
        raise AssertionError("Suspension is not part of this test")


def _provision_and_activate(settings: Settings, employee_id: str, email: str) -> None:
    operations = operations_store(settings.resolved_database_url())
    processed = IdentityProvisioningWorker(
        operations.engine,
        VerifiedDirectory(),
        settings.employee_document_key_bytes(),
    ).process_one(worker="identity-worker@example.com")
    assert processed and processed["status"] == "verified"
    row = OnboardingLifecycleStore(operations.engine).employee_row(employee_id)
    assert row
    operations.create_employee_invite(
        employee_id,
        actor="identity-worker@example.com",
        invite_base_url="https://erp.bensonhomesolutions.com",
        invite_signing_secret=settings.employee_invite_signing_secret,
        expires_in_hours=72,
        notification_max_attempts=10,
        expected_version=int(row["version"]),
        bootstrap_password=str(processed["bootstrap_password"]),
        encryption_key=settings.employee_document_key_bytes(),
    )
    queued = operations.claim_employee_notifications(limit=1)[0]
    token = employee_invite_token(
        settings.employee_invite_signing_secret,
        str(queued["payload"]["invite_id"]),
    )
    operations.activate_employee_invite(
        token, email=email, google_subject="google-test-new-hire"
    )


def _submit_document(
    settings: Settings,
    employee_id: str,
    task: Any,
    *,
    actor: str,
    actor_party: str,
) -> None:
    operations = operations_store(settings.resolved_database_url())
    task_id = str(task.id)
    context = operations.employee_document_upload_context(employee_id, task_id)
    assert context
    current = OnboardingLifecycleStore(operations.engine).task_row(employee_id, task_id)
    assert current
    content = f"%PDF-1.4\nCompleted synthetic {task.requirement_id}\n%%EOF".encode()
    storage_key, digest, nonce, key_version = store_employee_document(
        settings,
        employee_id=employee_id,
        task_id=task_id,
        version=context["version"],
        data_classification=context["data_classification"],
        original_name=f"{task.requirement_id}.pdf",
        content_type="application/pdf",
        content=content,
    )
    document = operations.add_employee_document(
        employee_id=employee_id,
        task_id=task_id,
        version=context["version"],
        original_name=f"{task.requirement_id}.pdf",
        storage_key=storage_key,
        content_type="application/pdf",
        size_bytes=len(content),
        sha256=digest,
        data_classification=context["data_classification"],
        nonce_base64=nonce,
        key_version=key_version,
        actor=actor,
        actor_party=actor_party,
        expected_version=int(current["version"]),
    )
    stored = operations.get_employee_document(str(document.id))
    assert stored
    assert (
        read_employee_document(
            settings,
            storage_key=stored["storage_key"],
            employee_id=employee_id,
            task_id=task_id,
            version=stored["version"],
            data_classification=stored["data_classification"],
            nonce_base64=stored["nonce_base64"],
            key_version=stored["key_version"],
        )
        == content
    )


def _complete_task(settings: Settings, employee_id: str, task: Any) -> None:
    operations = operations_store(settings.resolved_database_url())
    task_id = str(task.id)
    if task.completion_method in {"document_upload", "employer_evidence"}:
        employee_owned = task.completion_method == "document_upload"
        _submit_document(
            settings,
            employee_id,
            task,
            actor=(
                "jordan.hire@bensonhomesolutions.com"
                if employee_owned
                else "office@bensonhomesolutions.com"
            ),
            actor_party="employee" if employee_owned else "employer",
        )
    elif task.completion_method == "employee_signature":
        current = OnboardingLifecycleStore(operations.engine).task_row(
            employee_id, task_id
        )
        assert current
        operations.submit_employee_signature(
            employee_id,
            task_id,
            signer_email="jordan.hire@bensonhomesolutions.com",
            signer_subject="google-test-new-hire",
            typed_name="Jordan New Hire",
            expected_version=int(current["version"]),
        )
    submitted = OnboardingLifecycleStore(operations.engine).task_row(
        employee_id, task_id
    )
    assert submitted
    operations.review_employee_task(
        employee_id,
        task_id,
        decision="complete",
        comment="Synthetic end-to-end onboarding verification.",
        actor="office@bensonhomesolutions.com",
        expected_version=int(submitted["version"]),
    )


def test_name_and_personal_email_launch_approved_identity_workflow(
    isolated_settings: Settings,
) -> None:
    created = create_employee(
        EmployeeCreate(
            name="Jordan New Hire",
            email="jordan.personal@example.com",
            start_date="2026-08-03",
            work_location="Burns, Oregon",
            classification="employee",
            role=Role.FIELD,
        ),
        principal=Principal(
            email="office@bensonhomesolutions.com",
            role=Role.OWNER,
            subject="owner-1",
        ),
        settings=isolated_settings,
    )
    assert str(created.email) == "jordan.hire@bensonhomesolutions.com"
    assert str(created.invite_delivery_email) == "jordan.personal@example.com"
    commands = IdentityProvisioningStore(
        operations_store(isolated_settings.resolved_database_url()).engine
    ).list_for_employee(str(created.id))
    assert commands[0]["status"] == "approved"
    requirement_ids = {
        task.requirement_id
        for task in operations_store(
            isolated_settings.resolved_database_url()
        ).list_employee_tasks(str(created.id))
    }
    required = {
        "form-i9",
        "federal-w4",
        "e-verify",
        "section-503-self-id",
        "vevraa-self-id",
    }
    assert required <= requirement_ids


def test_verified_identity_can_queue_usable_invitation(
    isolated_settings: Settings,
) -> None:
    operations = operations_store(isolated_settings.resolved_database_url())
    employee = operations.create_employee(
        EmployeeCreate(
            name="Jordan New Hire",
            email="jordan.newhire@bensonhomesolutions.com",
            invite_delivery_email="jordan@example.com",
            start_date="2026-08-03",
            work_location="Burns, Oregon",
            classification="employee",
            role=Role.FIELD,
        ),
        actor="office@bensonhomesolutions.com",
    )
    employee_id = str(employee.id)
    commands = IdentityProvisioningStore(operations.engine)
    command = commands.request_create(
        employee_id,
        expected_version=1,
        idempotency_key=f"new-hire:{employee_id}",
        target_org_unit="/Benson Onboarding Test",
        actor="office@bensonhomesolutions.com",
    )
    assert command
    commands.approve(
        str(command["id"]),
        expected_version=1,
        actor="office@bensonhomesolutions.com",
    )
    processed = IdentityProvisioningWorker(
        operations.engine,
        VerifiedDirectory(),
        isolated_settings.employee_document_key_bytes(),
    ).process_one(worker="identity-worker@example.com")
    assert processed and processed["status"] == "verified"
    row = OnboardingLifecycleStore(operations.engine).employee_row(employee_id)
    assert row
    operations.create_employee_invite(
        employee_id,
        actor="identity-worker@example.com",
        invite_base_url="https://erp.bensonhomesolutions.com",
        invite_signing_secret=isolated_settings.employee_invite_signing_secret,
        expires_in_hours=72,
        notification_max_attempts=10,
        expected_version=int(row["version"]),
        bootstrap_password=str(processed["bootstrap_password"]),
        encryption_key=isolated_settings.employee_document_key_bytes(),
    )
    queued = operations.claim_employee_notifications(limit=1)[0]
    _subject, message = _email_message(queued["payload"], isolated_settings)
    assert queued["destination"] == "jordan@example.com"
    assert "jordan.newhire@bensonhomesolutions.com" in message
    assert "Temp-Password-123" in message
    assert "#/activate?token=" in message
    assert len(operations.list_employee_tasks(employee_id)) >= 14


def test_full_federal_contractor_onboarding_can_be_submitted_and_completed(
    isolated_settings: Settings,
) -> None:
    created = create_employee(
        EmployeeCreate(
            name="Jordan New Hire",
            email="jordan.personal@example.com",
            start_date="2026-08-03",
            work_location="Burns, Oregon",
            classification="employee",
            role=Role.FIELD,
            federal_contract_applicability="applicable",
        ),
        principal=Principal(
            email="office@bensonhomesolutions.com",
            role=Role.OWNER,
            subject="owner-1",
        ),
        settings=isolated_settings,
    )
    employee_id = str(created.id)
    _provision_and_activate(isolated_settings, employee_id, str(created.email))
    operations = operations_store(isolated_settings.resolved_database_url())
    lifecycle = OnboardingLifecycleStore(operations.engine)
    for task in operations.list_employee_tasks(employee_id):
        if task.applicability_status == "pending_review":
            current = lifecycle.task_row(employee_id, str(task.id))
            assert current
            operations.decide_employee_task_applicability(
                employee_id,
                str(task.id),
                decision="applicable",
                comment="Synthetic covered federal-contract test scenario.",
                reviewer_name="Test Compliance Reviewer",
                reviewer_qualification="Synthetic test fixture only",
                actor="office@bensonhomesolutions.com",
                expected_version=int(current["version"]),
            )
    tasks = operations.list_employee_tasks(employee_id)
    for task in tasks:
        refreshed = lifecycle.task_row(employee_id, str(task.id))
        assert refreshed and refreshed["status"] == "pending"
        _complete_task(
            isolated_settings,
            employee_id,
            type(task).model_validate(refreshed),
        )
    completed = operations.list_employee_tasks(employee_id)
    assert all(task.status == "completed" for task in completed)
    completed_employee = operations.get_employee(employee_id)
    assert completed_employee
    assert completed_employee.status == "onboarding_complete"
    legally_required = {
        "form-i9",
        "form-i9-employer-review",
        "federal-w4",
        "oregon-w4",
        "oregon-new-hire-report",
        "e-verify",
        "davis-bacon",
        "section-503-self-id",
        "vevraa-self-id",
    }
    completed_ids = {task.requirement_id for task in completed}
    assert legally_required <= completed_ids
    assert all(
        task.official_source.startswith("https://")
        for task in completed
        if task.requirement_id in legally_required
    )
