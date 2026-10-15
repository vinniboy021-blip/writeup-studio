"""Seed versioned templates, initial categories and RBAC catalogs."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATEGORIES = [
    "Web",
    "Pwn",
    "Reverse Engineering",
    "Cryptography",
    "Forensics",
    "OSINT",
    "Misc",
    "Mobile",
    "Cloud",
    "Active Directory",
]
TEMPLATES = [
    "CTF Writeup",
    "Hack The Box",
    "TryHackMe",
    "PicoCTF",
    "Pentest Report",
    "Vulnerability Report",
    "CVE Research Report",
    "Bug Bounty Report",
    "Forensic Analysis",
    "Reverse Engineering Report",
]
SECTIONS = [
    "Informações do desafio",
    "Objetivo",
    "Contexto",
    "Ambiente",
    "Reconhecimento e análise",
    "Hipóteses",
    "Metodologia utilizada",
    "Etapas técnicas",
    "Comandos executados",
    "Resultados observados",
    "Evidências",
    "Exploração ou resolução do desafio",
    "Validação",
    "Flag",
    "Conclusão",
    "Lições aprendidas",
    "Referências",
]
REPORT_SECTIONS = [
    "Resumo executivo",
    "Escopo",
    "Ambiente",
    "Metodologia",
    "Observações confirmadas",
    "Hipóteses",
    "Evidências",
    "Análise técnica",
    "Impacto",
    "Recomendações",
    "Validação",
    "Conclusão",
    "Referências",
]
ROLES = {
    "admin": ["read", "write", "comment", "review", "publish", "manage"],
    "manager": ["read", "write", "comment", "review", "publish", "manage"],
    "editor": ["read", "write", "comment", "publish"],
    "reviewer": ["read", "comment", "review"],
    "viewer": ["read"],
}


def identifier(kind, name):
    return str(uuid5(NAMESPACE_URL, f"ctf-studio/{kind}/{name}"))


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    now = datetime.now(timezone.utc)
    if op.get_context().as_sql:
        # Offline mode emits only schema; idempotent seeds run during online upgrade.
        return
    categories = sa.Table("categories", metadata, autoload_with=connection)
    templates = sa.Table("writeup_templates", metadata, autoload_with=connection)
    revisions = sa.Table("template_revisions", metadata, autoload_with=connection)
    roles = sa.Table("roles", metadata, autoload_with=connection)
    permissions = sa.Table("permissions", metadata, autoload_with=connection)
    mapping = sa.Table("role_permissions", metadata, autoload_with=connection)
    for name in CATEGORIES:
        record_id = identifier("category", name)
        if connection.scalar(sa.select(categories.c.id).where(categories.c.id == record_id)) is None:
            connection.execute(
                categories.insert().values(
                    id=record_id, name=name, description="", owner_id=None, team_id=None, created_at=now
                )
            )
    for name in TEMPLATES:
        record_id = identifier("template", name)
        if connection.scalar(sa.select(templates.c.id).where(templates.c.id == record_id)) is None:
            titles = SECTIONS if name in TEMPLATES[:4] else REPORT_SECTIONS
            document = {
                "schema_version": 1,
                "sections": [
                    {"id": f"section-{i + 1}", "title": title, "markdown": ""} for i, title in enumerate(titles)
                ],
            }
            connection.execute(
                templates.insert().values(
                    id=record_id,
                    name=name,
                    description="Modelo editável; registre observações e evidências reais.",
                    document=document,
                    version=1,
                    visibility="private",
                    owner_id=None,
                    team_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                revisions.insert().values(
                    id=identifier("template-revision", name),
                    template_id=record_id,
                    version=1,
                    name=name,
                    description="Modelo padrão",
                    document=document,
                    author_id=None,
                    created_at=now,
                )
            )
    for permission in sorted({item for values in ROLES.values() for item in values}):
        connection.execute(permissions.insert().values(id=identifier("permission", permission), name=permission))
    for role, names in ROLES.items():
        role_id = identifier("role", role)
        connection.execute(roles.insert().values(id=role_id, name=role, description=role))
        for name in names:
            connection.execute(
                mapping.insert().values(
                    id=identifier("role-permission", role + "/" + name),
                    role_id=role_id,
                    permission_id=identifier("permission", name),
                )
            )


def downgrade():
    connection = op.get_bind()
    if op.get_context().as_sql:
        return
    metadata = sa.MetaData()
    for table, kind, names in [
        (
            "role_permissions",
            "role-permission",
            [role + "/" + name for role, values in ROLES.items() for name in values],
        ),
        ("roles", "role", list(ROLES)),
        ("permissions", "permission", sorted({item for values in ROLES.values() for item in values})),
        ("template_revisions", "template-revision", TEMPLATES),
        ("writeup_templates", "template", TEMPLATES),
        ("categories", "category", CATEGORIES),
    ]:
        target = sa.Table(table, metadata, autoload_with=connection)
        connection.execute(target.delete().where(target.c.id.in_([identifier(kind, name) for name in names])))
