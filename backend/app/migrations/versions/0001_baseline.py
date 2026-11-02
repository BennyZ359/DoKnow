"""v0.1 learning evidence tables, preserved as an immutable baseline."""

from alembic import op

from app.migrations.schema import baseline_metadata

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    baseline_metadata().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
