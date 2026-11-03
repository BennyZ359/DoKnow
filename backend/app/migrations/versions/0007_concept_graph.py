"""Store semantic entities and assertions separately from course roadmaps."""

from alembic import op

from app.migrations.schema import concept_graph_metadata

revision = "0007_concept_graph"
down_revision = "0006_roadmaps"
branch_labels = None
depends_on = None


def upgrade():
    metadata = concept_graph_metadata()
    for table in ("concept_graphs", "knowledge_entities", "knowledge_relations"):
        metadata.tables[table].create(bind=op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrades are disabled. Restore a verified backup to a new database.")
