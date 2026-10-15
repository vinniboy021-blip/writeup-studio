"""Adopt pre-migration databases without dropping user documents or evidence metadata."""

from datetime import datetime, timezone
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen definitions of columns absent in the pre-Alembic prototype.
ADDITIONS = {
    "users": [
        ("is_active", sa.Boolean(), False, True),
    ],
    "sessions": [
        ("revoked_at", sa.DateTime(timezone=True), True, None),
        ("user_agent", sa.String(500), False, ""),
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "teams": [
        ("description", sa.String(), False, ""),
        ("updated_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "team_members": [
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "competitions": [
        ("mode", sa.String(40), False, "jeopardy"),
        ("tags", sa.JSON(), False, []),
        ("version", sa.Integer(), False, 1),
        ("deleted_at", sa.DateTime(timezone=True), True, None),
        ("updated_at", sa.DateTime(timezone=True), False, "NOW"),
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "challenges": [
        ("references", sa.JSON(), False, []),
        ("notes", sa.String(), False, ""),
        ("tags", sa.JSON(), False, []),
        ("version", sa.Integer(), False, 1),
        ("deleted_at", sa.DateTime(timezone=True), True, None),
        ("updated_at", sa.DateTime(timezone=True), False, "NOW"),
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "writeups": [
        ("approved_revision", sa.Integer(), True, None),
        ("published_at", sa.DateTime(timezone=True), True, None),
        ("tags", sa.JSON(), False, []),
        ("tools", sa.JSON(), False, []),
        ("languages", sa.JSON(), False, []),
        ("deleted_at", sa.DateTime(timezone=True), True, None),
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "writeup_revisions": [],
    "evidences": [
        ("challenge_id", sa.String(36), True, None),
        ("captured_at", sa.DateTime(timezone=True), True, None),
        ("received_at", sa.DateTime(timezone=True), False, "NOW"),
        ("extension", sa.String(20), False, ""),
        ("thumbnail_key", sa.String(500), True, None),
        ("version", sa.Integer(), False, 1),
        ("tags", sa.JSON(), False, []),
        ("metadata_json", sa.JSON(), False, {}),
        ("team_id", sa.String(36), True, None),
        ("deleted_at", sa.DateTime(timezone=True), True, None),
        ("updated_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "audit_logs": [
        ("correlation_id", sa.String(64), True, None),
    ],
    "writeup_templates": [
        ("team_id", sa.String(36), True, None),
        ("visibility", sa.String(20), False, "private"),
        ("deleted_at", sa.DateTime(timezone=True), True, None),
        ("updated_at", sa.DateTime(timezone=True), False, "NOW"),
        ("created_at", sa.DateTime(timezone=True), False, "NOW"),
    ],
    "comments": [
        ("resolved_at", sa.DateTime(timezone=True), True, None),
    ],
    "review_requests": [
        ("reviewer_id", sa.String(36), False, "REQUESTER"),
    ],
    "evidence_annotations": [],
    "evidence_events": [],
}

FOREIGN_KEYS = {
    "users": [],
    "sessions": [],
    "teams": [],
    "team_members": [],
    "competitions": [("team_id", "teams", "id", "RESTRICT")],
    "challenges": [("competition_id", "competitions", "id", "RESTRICT"), ("team_id", "teams", "id", "RESTRICT")],
    "writeups": [("challenge_id", "challenges", "id", "RESTRICT"), ("team_id", "teams", "id", "RESTRICT")],
    "writeup_revisions": [],
    "evidences": [("challenge_id", "challenges", "id", "RESTRICT"), ("team_id", "teams", "id", "RESTRICT")],
    "audit_logs": [("actor_id", "users", "id", "SET NULL")],
    "writeup_templates": [("owner_id", "users", "id", "RESTRICT"), ("team_id", "teams", "id", "RESTRICT")],
    "comments": [],
    "review_requests": [("reviewer_id", "users", "id", "RESTRICT")],
    "evidence_annotations": [],
    "evidence_events": [],
}

UNIQUE_KEYS = {
    "users": [],
    "sessions": [],
    "teams": [],
    "team_members": [("uq_team_member", ["team_id", "user_id"])],
    "competitions": [],
    "challenges": [],
    "writeups": [],
    "writeup_revisions": [("uq_writeup_revision", ["writeup_id", "version"])],
    "evidences": [("uq_evidences_storage_key", ["storage_key"])],
    "audit_logs": [],
    "writeup_templates": [],
    "comments": [],
    "review_requests": [],
    "evidence_annotations": [("uq_evidence_annotation", ["evidence_id", "version"])],
    "evidence_events": [],
}

CHECKS = {
    "users": [],
    "sessions": [],
    "teams": [],
    "team_members": [("ck_team_member_role", "role IN ('manager','editor','reviewer','viewer')")],
    "competitions": [
        ("ck_competition_dates", "end_at IS NULL OR start_at IS NULL OR end_at >= start_at"),
        ("ck_competition_team", "visibility != 'team' OR team_id IS NOT NULL"),
        ("ck_competition_visibility", "visibility IN ('private','team')"),
        ("ck_competition_version", "version >= 1"),
    ],
    "challenges": [
        ("ck_challenge_version", "version >= 1"),
        ("ck_challenge_visibility", "visibility IN ('private','team')"),
        ("ck_challenge_team", "visibility != 'team' OR team_id IS NOT NULL"),
        ("ck_challenge_points", "points >= 0"),
    ],
    "writeups": [
        ("ck_writeup_team", "visibility != 'team' OR team_id IS NOT NULL"),
        ("ck_writeup_version", "version >= 1"),
        ("ck_writeup_visibility", "visibility IN ('private','team')"),
    ],
    "writeup_revisions": [],
    "evidences": [
        ("ck_evidence_size", "size >= 0"),
        ("ck_evidence_team", "visibility != 'team' OR team_id IS NOT NULL"),
        ("ck_evidence_version", "version >= 1"),
        ("ck_evidence_visibility", "visibility IN ('private','team')"),
    ],
    "audit_logs": [],
    "writeup_templates": [],
    "comments": [],
    "review_requests": [],
    "evidence_annotations": [],
    "evidence_events": [],
}

INDEXES = {
    "users": [("ix_users_email", ["email"], True)],
    "sessions": [
        ("ix_sessions_revoked_at", ["revoked_at"], False),
        ("ix_sessions_token_hash", ["token_hash"], True),
        ("ix_sessions_user_id", ["user_id"], False),
        ("ix_sessions_expires_at", ["expires_at"], False),
    ],
    "teams": [("ix_teams_owner_id", ["owner_id"], False)],
    "team_members": [("ix_team_members_user_id", ["user_id"], False), ("ix_team_members_team_id", ["team_id"], False)],
    "competitions": [
        ("ix_competitions_name", ["name"], False),
        ("ix_competitions_owner_id", ["owner_id"], False),
        ("ix_competitions_status", ["status"], False),
        ("ix_competitions_team_id", ["team_id"], False),
        ("ix_competitions_deleted_at", ["deleted_at"], False),
        ("ix_competitions_visibility", ["visibility"], False),
    ],
    "challenges": [
        ("ix_challenges_visibility", ["visibility"], False),
        ("ix_challenges_category", ["category"], False),
        ("ix_challenge_category_status", ["category", "status"], False),
        ("ix_challenges_status", ["status"], False),
        ("ix_challenges_competition_id", ["competition_id"], False),
        ("ix_challenges_name", ["name"], False),
        ("ix_challenges_owner_id", ["owner_id"], False),
        ("ix_challenges_team_id", ["team_id"], False),
        ("ix_challenges_deleted_at", ["deleted_at"], False),
    ],
    "writeups": [
        ("ix_writeups_challenge_id", ["challenge_id"], False),
        ("ix_writeups_status", ["status"], False),
        ("ix_writeups_visibility", ["visibility"], False),
        ("ix_writeups_title", ["title"], False),
        ("ix_writeups_team_id", ["team_id"], False),
        ("ix_writeups_owner_id", ["owner_id"], False),
        ("ix_writeups_deleted_at", ["deleted_at"], False),
    ],
    "writeup_revisions": [("ix_writeup_revisions_writeup_id", ["writeup_id"], False)],
    "evidences": [
        ("ix_evidences_owner_id", ["owner_id"], False),
        ("ix_evidences_deleted_at", ["deleted_at"], False),
        ("ix_evidences_visibility", ["visibility"], False),
        ("ix_evidences_team_id", ["team_id"], False),
        ("ix_evidences_challenge_id", ["challenge_id"], False),
        ("ix_evidences_sha256", ["sha256"], False),
    ],
    "audit_logs": [
        ("ix_audit_logs_actor_id", ["actor_id"], False),
        ("ix_audit_logs_action", ["action"], False),
        ("ix_audit_logs_correlation_id", ["correlation_id"], False),
    ],
    "writeup_templates": [
        ("ix_writeup_templates_owner_id", ["owner_id"], False),
        ("ix_writeup_templates_team_id", ["team_id"], False),
    ],
    "comments": [("ix_comments_writeup_id", ["writeup_id"], False)],
    "review_requests": [
        ("ix_review_requests_reviewer_id", ["reviewer_id"], False),
        ("ix_review_requests_writeup_id", ["writeup_id"], False),
    ],
    "evidence_annotations": [("ix_evidence_annotations_evidence_id", ["evidence_id"], False)],
    "evidence_events": [("ix_evidence_events_evidence_id", ["evidence_id"], False)],
}


def upgrade():
    if op.get_context().as_sql:
        # Offline output supports clean deployments; adopting a legacy DB needs inspection.
        return
    connection = op.get_bind()
    op.create_table(
        "ctf_migration_changes",
        sa.Column("table_name", sa.String(100), primary_key=True),
        sa.Column("plan", sa.JSON(), nullable=False),
    )
    history = sa.table("ctf_migration_changes", sa.column("table_name", sa.String(100)), sa.column("plan", sa.JSON()))
    inspector = sa.inspect(connection)
    for table, definitions in ADDITIONS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        added = []
        previous = []
        if table in {"competitions", "challenges", "writeups", "evidences"}:
            previous = [
                dict(row) for row in connection.execute(sa.text(f"SELECT id, visibility FROM {table}")).mappings()
            ]
        if table in {"writeups", "review_requests"}:
            statuses = {
                row["id"]: row["status"]
                for row in connection.execute(sa.text(f"SELECT id, status FROM {table}")).mappings()
            }
            if table == "review_requests":
                previous = [{"id": identifier, "status": status} for identifier, status in statuses.items()]
            else:
                for row in previous:
                    row["status"] = statuses[row["id"]]
        for name, kind, nullable, default in definitions:
            if name in columns:
                continue
            op.add_column(table, sa.Column(name, kind, nullable=True))
            target = sa.table(table, sa.column(name, kind))
            if default == "NOW":
                value = datetime.now(timezone.utc)
            elif default == "REQUESTER":
                value = sa.literal_column("requester_id")
            else:
                value = default
            if value is not None:
                connection.execute(target.update().values({name: value}))
            added.append((name, kind, nullable))
        if table == "sessions" and "revoked" in columns:
            connection.execute(
                sa.text("UPDATE sessions SET revoked_at = :now WHERE revoked = :revoked AND revoked_at IS NULL"),
                {"now": datetime.now(timezone.utc), "revoked": True},
            )
        if table == "comments" and "resolved" in columns:
            connection.execute(
                sa.text("UPDATE comments SET resolved_at = :now WHERE resolved = :resolved AND resolved_at IS NULL"),
                {"now": datetime.now(timezone.utc), "resolved": True},
            )
        if table in {"competitions", "challenges", "writeups", "evidences"}:
            # Previous public visibility did not produce a reviewed snapshot. Keep text private.
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET visibility = 'private' WHERE visibility NOT IN ('private','team') OR (visibility = 'team' AND team_id IS NULL)"
                )
            )
        if table == "review_requests" and any(name == "reviewer_id" for name, _, _ in added):
            # Earlier requests had no independent reviewer. Retain them as cancelled history.
            connection.execute(sa.text("UPDATE review_requests SET status = 'cancelled'"))
        if table == "writeups" and any(name == "approved_revision" for name, _, _ in added):
            connection.execute(sa.text("UPDATE writeups SET status = 'draft' WHERE status = 'approved'"))
        existing_fks = {tuple(item["constrained_columns"]) for item in inspector.get_foreign_keys(table)}
        existing_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)}
        existing_checks = {item["name"] for item in inspector.get_check_constraints(table)}
        foreign_keys = [item for item in FOREIGN_KEYS[table] if (item[0],) not in existing_fks]
        unique_keys = [item for item in UNIQUE_KEYS[table] if tuple(item[1]) not in existing_unique]
        checks = [item for item in CHECKS[table] if item[0] not in existing_checks]
        integer_member_id = table == "team_members" and isinstance(columns["id"]["type"], sa.Integer)
        original_member_ids = []
        if integer_member_id:
            original_member_ids = [
                dict(row)
                for row in connection.execute(sa.text("SELECT id, team_id, user_id FROM team_members")).mappings()
            ]
        if integer_member_id and connection.dialect.name == "postgresql":
            op.alter_column(table, "id", type_=sa.String(36), postgresql_using="md5('legacy-team-member-' || id::text)")
        if (
            added
            or foreign_keys
            or unique_keys
            or checks
            or (integer_member_id and connection.dialect.name == "sqlite")
        ):
            with op.batch_alter_table(table) as batch:
                for name, kind, nullable in added:
                    if not nullable:
                        batch.alter_column(name, existing_type=kind, nullable=False)
                if integer_member_id and connection.dialect.name == "sqlite":
                    batch.alter_column("id", existing_type=sa.Integer(), type_=sa.String(36))
                for name, referent, field, deletion in foreign_keys:
                    batch.create_foreign_key(f"fk_{table}_{name}", referent, [name], [field], ondelete=deletion)
                for name, fields in unique_keys:
                    batch.create_unique_constraint(name, fields)
                for name, expression in checks:
                    batch.create_check_constraint(name, expression)
        if integer_member_id:
            target = sa.table(table, sa.column("id", sa.String(36)))
            for (identifier,) in connection.execute(sa.select(target.c.id)).all():
                replacement = str(uuid.uuid5(uuid.NAMESPACE_URL, "legacy-team-member-" + str(identifier)))
                connection.execute(target.update().where(target.c.id == identifier).values(id=replacement))
        existing_indexes = {item["name"] for item in sa.inspect(connection).get_indexes(table)}
        new_indexes = []
        for name, fields, unique in INDEXES[table]:
            if name not in existing_indexes:
                op.create_index(name, table, fields, unique=unique)
                new_indexes.append(name)
        if added or foreign_keys or unique_keys or checks or integer_member_id or new_indexes:
            connection.execute(
                history.insert().values(
                    table_name=table,
                    plan={
                        "added": [name for name, _, _ in added],
                        "foreign_keys": [f"fk_{table}_{item[0]}" for item in foreign_keys],
                        "unique_keys": [name for name, _ in unique_keys],
                        "checks": [name for name, _ in checks],
                        "indexes": new_indexes,
                        "previous": previous,
                        "member_ids": original_member_ids,
                    },
                )
            )
    if connection.dialect.name == "sqlite":
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("Dados legados contêm relações órfãs; corrigir antes de migrar")


def downgrade():
    if op.get_context().as_sql:
        return
    connection = op.get_bind()
    history = sa.table("ctf_migration_changes", sa.column("table_name", sa.String(100)), sa.column("plan", sa.JSON()))
    for table, plan in connection.execute(sa.select(history.c.table_name, history.c.plan)).all():
        for name in plan["indexes"]:
            op.drop_index(name, table_name=table)
        if plan["member_ids"]:
            for row in plan["member_ids"]:
                connection.execute(
                    sa.text("UPDATE team_members SET id = :id WHERE team_id = :team_id AND user_id = :user_id"), row
                )
        with op.batch_alter_table(table) as batch:
            for name in plan["foreign_keys"]:
                batch.drop_constraint(name, type_="foreignkey")
            for name in plan["unique_keys"]:
                batch.drop_constraint(name, type_="unique")
            for name in plan["checks"]:
                batch.drop_constraint(name, type_="check")
            for name in plan["added"]:
                batch.drop_column(name)
            if plan["member_ids"] and connection.dialect.name == "sqlite":
                batch.alter_column("id", existing_type=sa.String(36), type_=sa.Integer())
        if plan["member_ids"] and connection.dialect.name == "postgresql":
            op.alter_column(table, "id", type_=sa.Integer(), postgresql_using="id::integer")
        for row in plan["previous"]:
            fields = [name for name in row if name != "id"]
            statement = sa.text(
                f"UPDATE {table} SET " + ", ".join(f"{name} = :{name}" for name in fields) + " WHERE id = :id"
            )
            connection.execute(statement, row)
    op.drop_table("ctf_migration_changes")
