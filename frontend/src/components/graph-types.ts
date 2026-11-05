/** Shared node/link shapes for the knowledge graph (owned by the parent view). */
export interface KgNode {
  id: string
  name: string
  label: string
  color: string
  size: number
  highlighted?: boolean
}

export interface KgLink {
  source: string
  target: string
}
