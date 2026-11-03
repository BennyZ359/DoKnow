"""Retain replaced materials and version explicit course confirmations."""

from alembic import op
from sqlalchemy import Column, Integer, text

from app.migrations.schema import course_metadata

revision = "0005_course_changes"
down_revision = "0004_editable_records"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("goals", Column("course_version", Integer, nullable=False, server_default=text("1")))
    op.add_column("units", Column("archived", Integer, nullable=False, server_default=text("0")))
    course_metadata().tables["course_changes"].create(bind=op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
