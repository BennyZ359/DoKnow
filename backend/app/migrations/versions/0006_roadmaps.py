"""Persist prerequisite graphs independently of course learning evidence."""

from alembic import op

from app.migrations.schema import roadmap_metadata

revision = "0006_roadmaps"
down_revision = "0005_course_changes"
branch_labels = None
depends_on = None


def upgrade():
    roadmap_metadata().tables["roadmaps"].create(bind=op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
