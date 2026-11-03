<script setup lang="ts">
import cytoscape from 'cytoscape'
import type { Core, EventObject, StylesheetJson } from 'cytoscape'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { KnowledgeEntity, KnowledgeRelation } from '../knowledgeGraph'
import { entityColors } from '../knowledgeGraph'

const props = defineProps<{
  entities: KnowledgeEntity[]
  relations: KnowledgeRelation[]
  focusId: string
  selectedId: string
  selectedEdge?: string
  pathNodes: string[]
  pathEdges: string[]
  labels: boolean
}>()
const emit = defineEmits<{ select: [id: string]; relation: [id: string]; expand: [id: string] }>()
const container = ref<HTMLDivElement | null>(null)
const zoomLabel = ref(100)
const ready = ref(false)
let cy: Core | undefined
let observer: ResizeObserver | undefined
const styles: StylesheetJson = [
  {
    selector: 'node',
    style: {
      width: 'data(size)',
      height: 'data(size)',
      'background-color': 'data(color)',
      'border-width': 2,
      'border-color': '#ffffff',
      label: 'data(label)',
      color: '#44584b',
      'font-size': 20,
      'font-family': 'Microsoft YaHei, sans-serif',
      'text-valign': 'bottom',
      'text-margin-y': 9,
      'text-wrap': 'wrap',
      'text-max-width': '100px',
      'text-background-color': '#f8faf6',
      'text-background-opacity': 0.86,
      'text-background-padding': '3px',
      'overlay-opacity': 0,
    },
  },
  {
    selector: 'node.root',
    style: {
      width: 66,
      height: 66,
      'border-width': 7,
      'border-color': '#dce8dd',
      'font-size': 25,
      'font-weight': 'bold',
      color: '#284b3e',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 1.2,
      'line-color': '#c4cec2',
      'target-arrow-color': '#a8b6a6',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.65,
      'curve-style': 'bezier',
      label: 'data(label)',
      'font-size': 14,
      color: '#879582',
      'text-rotation': 'autorotate',
      'text-background-color': '#f8faf6',
      'text-background-opacity': 0.94,
      'text-background-padding': '3px',
      'overlay-opacity': 0,
    },
  },
  {
    selector: 'edge[kind="requires"]',
    style: {
      'line-style': 'dashed',
      'line-color': '#c6b38e',
      'target-arrow-color': '#b69e71',
      color: '#a48b62',
    },
  },
  { selector: '.faded', style: { opacity: 0.2 } },
  {
    selector: 'edge.relevant',
    style: {
      width: 2.4,
      'line-color': '#4b8873',
      'target-arrow-color': '#4b8873',
      color: '#426b57',
      'z-index': 10,
    },
  },
  {
    selector: 'node.active',
    style: {
      'border-width': 5,
      'border-color': '#b8cfaf',
      'font-weight': 'bold',
      color: '#244e3b',
      'z-index': 20,
    },
  },
  {
    selector: 'edge.active',
    style: {
      width: 3.5,
      'line-color': '#315f99',
      'target-arrow-color': '#315f99',
      color: '#315f99',
      'font-size': 12,
      'z-index': 30,
    },
  },
  {
    selector: 'edge.path',
    style: {
      width: 3.5,
      'line-color': '#cc9054',
      'target-arrow-color': '#cc9054',
      color: '#ad773d',
      'z-index': 20,
    },
  },
  { selector: 'node.path', style: { 'border-width': 5, 'border-color': '#e7c393', 'z-index': 20 } },
  { selector: '.hide-labels', style: { label: '' } },
]

function paintSelection() {
  if (!cy) return
  cy.batch(() => {
    cy!.elements().removeClass('active relevant faded path')
    if (
      props.selectedId &&
      cy!.$id(props.selectedId).length &&
      props.selectedId !== props.focusId &&
      !props.pathEdges.length &&
      !props.selectedEdge
    ) {
      const selected = cy!.$id(props.selectedId)
      cy!.elements().addClass('faded')
      selected.closedNeighborhood().removeClass('faded')
      selected.connectedEdges().addClass('relevant')
      selected.addClass('active')
    } else cy!.$id(props.selectedId).addClass('active')
    if (props.selectedEdge) {
      const edge = cy!.$id(props.selectedEdge)
      edge.addClass('active')
      edge.connectedNodes().addClass('active')
    }
    props.pathNodes.forEach((id) => cy!.$id(id).addClass('path'))
    props.pathEdges.forEach((id) => cy!.$id(id).addClass('path'))
    cy!.edges().toggleClass('hide-labels', !props.labels)
  })
}

function layout() {
  cy?.layout({
    name: 'cose',
    animate: false,
    randomize: true,
    padding: 60,
    nodeRepulsion: () => 85000,
    idealEdgeLength: () => 105,
    edgeElasticity: () => 95,
    gravity: 0.22,
    numIter: 650,
    nodeOverlap: 20,
    componentSpacing: 90,
  }).run()
}

function sync() {
  if (!cy) return
  const oldPositions = new Map(cy.nodes().map((node) => [node.id(), node.position()] as const))
  const degree = new Map<string, number>()
  for (const edge of props.relations) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
  }
  cy.batch(() => {
    cy!.elements().remove()
    cy!.add([
      ...props.entities.map((node) => ({
        group: 'nodes' as const,
        data: {
          id: node.id,
          label: node.name,
          color: entityColors[node.kind],
          size: 26 + Math.min(18, (degree.get(node.id) || 0) * 2),
          kind: node.kind,
        },
        position: oldPositions.get(node.id),
        classes: node.id === props.focusId ? 'root' : '',
      })),
      ...props.relations.map((edge) => ({
        group: 'edges' as const,
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          kind: edge.kind,
        },
      })),
    ])
  })
  layout()
  paintSelection()
  ready.value = true
}

function fit() {
  cy?.fit(undefined, 45)
}
function zoomBy(amount: number) {
  if (cy)
    cy.zoom({
      level: cy.zoom() * amount,
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    })
}
function locate(id: string) {
  if (!cy || !cy.$id(id).length) return
  cy.animate({
    center: { eles: cy.$id(id) },
    duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 250,
  })
}
defineExpose({ fit, layout, zoomBy, locate })
watch(() => [props.entities, props.relations], sync)
watch(
  () => [props.selectedId, props.selectedEdge, props.pathNodes, props.pathEdges, props.labels],
  paintSelection
)
onMounted(() => {
  cy = cytoscape({
    container: container.value!,
    style: styles,
    elements: [],
    minZoom: 0.15,
    maxZoom: 3,
    wheelSensitivity: 0.25,
    boxSelectionEnabled: false,
    autounselectify: true,
  })
  cy.on('tap', 'node', (event: EventObject) => emit('select', event.target.id()))
  cy.on('dbltap', 'node', (event: EventObject) => emit('expand', event.target.id()))
  cy.on('tap', 'edge', (event: EventObject) => emit('relation', event.target.id()))
  cy.on('zoom', () => {
    zoomLabel.value = Math.round(cy!.zoom() * 100)
  })
  observer = new ResizeObserver(() => {
    cy?.resize()
  })
  observer.observe(container.value!)
  sync()
})
onUnmounted(() => {
  observer?.disconnect()
  cy?.destroy()
  cy = undefined
})
function keyboard(event: KeyboardEvent) {
  if (!cy) return
  const movement: Record<string, { x: number; y: number }> = {
    ArrowLeft: { x: 40, y: 0 },
    ArrowRight: { x: -40, y: 0 },
    ArrowUp: { x: 0, y: 40 },
    ArrowDown: { x: 0, y: -40 },
  }
  if (movement[event.key]) {
    event.preventDefault()
    cy.panBy(movement[event.key])
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomBy(1.2)
  } else if (event.key === '-') {
    event.preventDefault()
    zoomBy(0.8)
  }
}
</script>

<template>
  <div class="concept-network-shell">
    <div
      ref="container"
      class="concept-network"
      tabindex="0"
      role="region"
      aria-label="可拖拽的知识关系网络。方向键平移，加减键缩放；实体列表可用键盘选择概念。"
      :data-ready="ready"
      :data-entity-count="entities.length"
      :data-relation-count="relations.length"
      @keydown="keyboard"
    ></div>
    <div class="network-hint"><span></span>拖拽节点 · 滚轮缩放 · 点击关系查看含义</div>
    <div class="network-controls">
      <button aria-label="缩小关系网络" @click="zoomBy(0.8)">−</button><span>{{ zoomLabel }}%</span
      ><button aria-label="放大关系网络" @click="zoomBy(1.2)">+</button><i></i
      ><button @click="fit">适应全图</button><button @click="layout">重新布局</button>
    </div>
    <div v-if="!entities.length" class="network-empty">没有符合当前筛选条件的实体。</div>
  </div>
</template>

<style scoped>
.concept-network-shell {
  position: relative;
  height: 650px;
  min-width: 0;
  background: #f8faf6;
  background-image: radial-gradient(#d9e1d1 0.75px, transparent 0.75px);
  background-size: 22px 22px;
}
.concept-network {
  position: absolute;
  inset: 0;
  touch-action: none;
}
.concept-network:focus-visible {
  outline: 2px solid #7c9e70;
  outline-offset: -3px;
}
.network-hint {
  position: absolute;
  top: 18px;
  left: 19px;
  pointer-events: none;
  font-size: 10px;
  color: #89977e;
  display: flex;
  align-items: center;
  gap: 6px;
}
.network-hint span {
  height: 5px;
  width: 5px;
  background: #9bae8b;
  border-radius: 50%;
}
.network-controls {
  position: absolute;
  right: 16px;
  bottom: 17px;
  display: flex;
  align-items: center;
  padding: 4px;
  gap: 3px;
  border: 1px solid #e1e7d7;
  border-radius: 8px;
  background: #fffffff2;
  box-shadow: 0 3px 15px #354b2210;
  color: #879578;
  font-size: 10px;
}
.network-controls button {
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #6d8561;
  padding: 8px;
  font-size: 10px;
}
.network-controls button:first-child,
.network-controls button:nth-child(3) {
  font-size: 18px;
  padding: 2px 10px;
}
.network-controls button:hover {
  background: #edf3e5;
}
.network-controls i {
  height: 14px;
  border-left: 1px solid #e2e8da;
  margin: 0 5px;
}
.network-empty {
  position: absolute;
  inset: 45% 20px auto;
  text-align: center;
  color: #8f9d83;
  font-size: 12px;
  pointer-events: none;
}
@media (max-width: 760px) {
  .concept-network-shell {
    height: 470px;
  }
  .network-hint {
    font-size: 8px;
    left: 12px;
  }
  .network-controls {
    right: 10px;
    bottom: 10px;
  }
}
</style>
