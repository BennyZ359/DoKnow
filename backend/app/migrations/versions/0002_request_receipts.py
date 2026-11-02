"""Persist request ownership and successful responses alongside learning evidence."""

from alembic import op

from app.migrations.schema import current_metadata

revision = "0002_request_receipts"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    current_metadata().tables["request_receipts"].create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
