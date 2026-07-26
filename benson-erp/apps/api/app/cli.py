import argparse
import asyncio
import getpass
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionFactory
from app.modules.platform.auth_service import password_hash
from app.modules.platform.models import Membership, Organization, User

ADMIN_PERMISSIONS = [
    "estimates.approve",
    "estimates.create",
    "estimates.write",
    "employees.approve",
    "employees.activate",
    "employees.manage",
    "federal_labor.charge_codes_manage",
    "federal_labor.charge_codes_read",
    "federal_labor.charge_codes_read",
    "federal_labor.floor_check_read",
    "federal_labor.invoice_support_generate",
    "federal_labor.invoice_support_read",
    "federal_labor.qualifications_manage",
    "federal_labor.rates_manage",
    "integrations.manage",
    "leads.convert",
    "leads.create",
    "leads.qualify",
    "payroll.export",
    "payroll.import",
    "payroll.mappings_manage",
    "payroll.periods_manage",
    "payroll.review",
    "payroll.reconcile",
    "payroll.view_wages",
    "projects.create",
    "projects.read",
    "proposals.accept",
    "proposals.create",
    "proposals.read",
    "schedules.manage",
    "schedules.read",
    "schedules.read_own",
    "time.approve_team",
    "time.certify_own",
    "time.correct_own",
    "time.correct_team",
    "time.enter_own",
    "time.enter_team",
    "time.read_team",
    "users.manage",
]


def read_admin_password(password_file: str | None) -> str:
    if password_file:
        password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
        confirmation = password
    else:
        password = getpass.getpass("Password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        raise SystemExit("Passwords must match and contain at least 12 characters")
    return password


async def create_admin(args: argparse.Namespace) -> None:
    password = read_admin_password(args.password_file)
    async with SessionFactory() as session:
        existing = await session.scalar(select(Organization).where(Organization.slug == args.slug))
        if existing:
            raise SystemExit(f"Organization slug already exists: {args.slug}")
        organization = Organization(
            name=args.organization,
            slug=args.slug,
            google_identity_domain=args.google_domain,
            google_customer_id=args.google_customer_id,
            google_default_org_unit_path=args.google_org_unit,
        )
        user = User(email=args.email.strip().lower(), password_hash=password_hash.hash(password))
        session.add_all((organization, user))
        await session.flush()
        session.add(
            Membership(
                tenant_id=organization.id,
                user_id=user.id,
                permissions=ADMIN_PERMISSIONS,
            )
        )
        await session.commit()
    print(f"Created administrator {user.email} for {organization.name}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="benson-erp")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-admin")
    create.add_argument("--organization", required=True)
    create.add_argument("--slug", required=True)
    create.add_argument("--email", required=True)
    create.add_argument("--google-domain")
    create.add_argument("--google-customer-id")
    create.add_argument("--google-org-unit", default="/")
    create.add_argument("--password-file")
    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(create_admin(args))
