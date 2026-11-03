export type EntityKind = 'domain' | 'concept' | 'method' | 'tool' | 'application'
export type RelationKind =
  'is_a' | 'part_of' | 'requires' | 'uses' | 'optimizes' | 'measures' | 'applied_to' | 'contrasts'
export interface GraphProvenance {
  kind: 'curated' | 'ai'
  label: string
  model?: string
}
export interface KnowledgeEntity {
  id: string
  key: string
  name: string
  kind: EntityKind
  description: string
  aliases: string[]
  properties: { example: string; learning_reason: string }
  provenance: GraphProvenance
}
export interface KnowledgeRelation {
  id: string
  source: string
  target: string
  kind: RelationKind
  label: string
  explanation: string
  provenance: GraphProvenance
}
export interface GraphSummary {
  id: string
  topic: string
  summary: string
  focus_id: string
  created_at: string
  entity_count: number
  relation_count: number
  provenance: GraphProvenance
}
export interface KnowledgeGraph extends GraphSummary {
  entities: KnowledgeEntity[]
  relations: KnowledgeRelation[]
  entity_types: Record<EntityKind, string>
  relation_types: Record<RelationKind, string>
}
export interface GraphNeighborhood {
  center: string
  entities: KnowledgeEntity[]
  relations: KnowledgeRelation[]
}
export interface GraphPath {
  found: boolean
  entity_ids: string[]
  relation_ids: string[]
  direction: string
}
export const entityLabels: Record<EntityKind, string> = {
  domain: '知识领域',
  concept: '概念',
  method: '方法 / 算法',
  tool: '工具',
  application: '应用',
}
export const entityColors: Record<EntityKind, string> = {
  domain: '#436e63',
  concept: '#819875',
  method: '#7397b1',
  tool: '#ba9a70',
  application: '#a18eb2',
}
export const relationLabels: Record<RelationKind, string> = {
  is_a: '是一种',
  part_of: '属于',
  requires: '依赖',
  uses: '使用',
  optimizes: '优化',
  measures: '衡量',
  applied_to: '应用于',
  contrasts: '区别于',
}
