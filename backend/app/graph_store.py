"""A persisted property-graph repository and bounded semantic traversal queries.

SQLite/PostgreSQL hold entities and directed assertions in indexed tables. Views
and paths are queried from those rows, never reconstructed from lesson order.
"""

from collections import defaultdict, deque
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ConceptGraph, KnowledgeEntity, KnowledgeRelation
from .serialization import timestamp
from .services.concept_graph import ConceptGraphPlan, KINDS, RELATIONS


def create_graph(db: Session, topic: str, result: dict) -> ConceptGraph:
    plan = ConceptGraphPlan.model_validate({key: result[key] for key in ("focus", "summary", "entities", "relations")})
    if result["source"] not in {"curated", "ai"}:
        raise ValueError("Unknown provenance")
    provenance = {"kind": result["source"], "label": "内置知识库 · 示例" if result["source"] == "curated" else "AI 生成 · 待核验"}
    if result.get("model"):
        provenance["model"] = result["model"]
    identities = {entity.key: str(uuid4()) for entity in plan.entities}
    item = ConceptGraph(id=str(uuid4()), topic=topic, summary=plan.summary,
                        focus_id=identities[plan.focus], provenance=provenance)
    db.add(item)
    db.flush()
    for entity in plan.entities:
        db.add(KnowledgeEntity(
            id=identities[entity.key], graph_id=item.id, key=entity.key, name=entity.name,
            kind=entity.kind, description=entity.description, aliases=entity.aliases,
            properties={"example": entity.example, "learning_reason": entity.learning_reason}, provenance=provenance,
        ))
    db.flush()
    for relation in plan.relations:
        db.add(KnowledgeRelation(
            graph_id=item.id, source_id=identities[relation.source], target_id=identities[relation.target],
            kind=relation.kind, explanation=relation.explanation, provenance=provenance,
        ))
    db.flush()
    return item


def require_graph(db, graph_id):
    graph = db.get(ConceptGraph, graph_id)
    if graph is None:
        raise HTTPException(404, "没有找到这张概念知识图谱。旧版课程路线需要重新构建为实体关系图谱。")
    return graph


def entity_data(entity):
    return {"id": entity.id, "key": entity.key, "name": entity.name, "kind": entity.kind,
            "description": entity.description, "aliases": entity.aliases,
            "properties": entity.properties, "provenance": entity.provenance}


def relation_data(relation):
    return {"id": relation.id, "source": relation.source_id, "target": relation.target_id,
            "kind": relation.kind, "label": RELATIONS[relation.kind],
            "explanation": relation.explanation, "provenance": relation.provenance}


def graph_summary(db, graph):
    from sqlalchemy import func
    return {"id": graph.id, "topic": graph.topic, "summary": graph.summary, "focus_id": graph.focus_id,
            "created_at": timestamp(graph.created_at), "provenance": graph.provenance,
            "entity_count": db.scalar(select(func.count()).select_from(KnowledgeEntity).where(KnowledgeEntity.graph_id == graph.id)),
            "relation_count": db.scalar(select(func.count()).select_from(KnowledgeRelation).where(KnowledgeRelation.graph_id == graph.id))}


def graph_data(db, graph_id):
    graph = require_graph(db, graph_id)
    entities = db.scalars(select(KnowledgeEntity).where(KnowledgeEntity.graph_id == graph_id).order_by(KnowledgeEntity.key)).all()
    relations = db.scalars(select(KnowledgeRelation).where(KnowledgeRelation.graph_id == graph_id).order_by(KnowledgeRelation.id)).all()
    return {**graph_summary(db, graph), "entities": [entity_data(entity) for entity in entities],
            "relations": [relation_data(relation) for relation in relations], "relation_types": RELATIONS, "entity_types": KINDS}


def search_entities(db, graph_id, query: str, kind: str | None):
    require_graph(db, graph_id)
    if kind and kind not in KINDS:
        raise HTTPException(422, "未知实体类型。")
    statement = select(KnowledgeEntity).where(KnowledgeEntity.graph_id == graph_id)
    if kind:
        statement = statement.where(KnowledgeEntity.kind == kind)
    # Case-folding handles both names and JSON aliases identically on SQLite and PostgreSQL.
    needle = query.strip().casefold()
    return [entity_data(item) for item in db.scalars(statement.order_by(KnowledgeEntity.name)).all()
            if not needle or any(needle in value.casefold() for value in [item.name, item.key, *item.aliases])]


def query_relations(db, graph_id, kinds: list[str] | None):
    if kinds and any(kind not in RELATIONS for kind in kinds):
        raise HTTPException(422, "未知关系类型。")
    statement = select(KnowledgeRelation).where(KnowledgeRelation.graph_id == graph_id)
    if kinds:
        statement = statement.where(KnowledgeRelation.kind.in_(kinds))
    return db.scalars(statement.order_by(KnowledgeRelation.id)).all()


def require_entity(db, graph_id, entity_id):
    require_graph(db, graph_id)
    entity = db.scalar(select(KnowledgeEntity).where(KnowledgeEntity.graph_id == graph_id, KnowledgeEntity.id == entity_id))
    if entity is None:
        raise HTTPException(404, "这个实体不属于当前图谱。")
    return entity


def adjacency(relations, direction="both"):
    neighbors = defaultdict(list)
    for relation in relations:
        if direction in {"both", "out"}:
            neighbors[relation.source_id].append((relation.target_id, relation.id))
        if direction in {"both", "in"}:
            neighbors[relation.target_id].append((relation.source_id, relation.id))
    return neighbors


def neighborhood(db, graph_id, entity_id, depth, kinds=None, direction="both"):
    require_entity(db, graph_id, entity_id)
    relations = query_relations(db, graph_id, kinds)
    neighbors = adjacency(relations, direction)
    reached, boundary = {entity_id}, {entity_id}
    for _ in range(depth):
        boundary = {target for node in boundary for target, _ in neighbors[node]} - reached
        reached |= boundary
    entities = db.scalars(select(KnowledgeEntity).where(KnowledgeEntity.graph_id == graph_id, KnowledgeEntity.id.in_(reached)).order_by(KnowledgeEntity.key)).all()
    return {"center": entity_id, "depth": depth, "direction": direction,
            "entities": [entity_data(item) for item in entities],
            "relations": [relation_data(edge) for edge in relations if edge.source_id in reached and edge.target_id in reached]}


def shortest_path(db, graph_id, source, target, kinds=None, direction="both"):
    require_entity(db, graph_id, source)
    require_entity(db, graph_id, target)
    relations = query_relations(db, graph_id, kinds)
    neighbors = adjacency(relations, direction)
    queue, previous = deque([source]), {source: None}
    while queue and target not in previous:
        current = queue.popleft()
        for node, edge_id in neighbors[current]:
            if node not in previous:
                previous[node] = (current, edge_id)
                queue.append(node)
    if target not in previous:
        return {"found": False, "entity_ids": [], "relation_ids": [], "direction": direction}
    nodes, edges = [target], []
    while nodes[-1] != source:
        node, edge_id = previous[nodes[-1]]
        nodes.append(node)
        edges.append(edge_id)
    return {"found": True, "entity_ids": nodes[::-1], "relation_ids": edges[::-1], "direction": direction}
