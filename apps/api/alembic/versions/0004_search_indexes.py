"""PostgreSQL full text and tag indices; SQLite remains a local test fallback."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

EXPRESSIONS = {
    "competitions": "coalesce(name, '') || ' ' || coalesce(description, '')",
    "challenges": "coalesce(name, '') || ' ' || coalesce(description, '') || ' ' || coalesce(notes, '')",
    "writeups": "coalesce(title, '') || ' ' || coalesce(CAST(document AS VARCHAR), '')",
    "evidences": "coalesce(name, '') || ' ' || coalesce(description, '')",
}


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, expression in EXPRESSIONS.items():
        op.execute(f"CREATE INDEX ix_{table}_fts ON {table} USING gin (to_tsvector('simple', {expression}))")
        op.execute(f"CREATE INDEX ix_{table}_tags_gin ON {table} USING gin ((CAST(tags AS JSONB)))")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in EXPRESSIONS:
        op.drop_index(f"ix_{table}_tags_gin", table_name=table)
        op.drop_index(f"ix_{table}_fts", table_name=table)
