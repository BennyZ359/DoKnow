<script setup lang="ts">
/**
 * 3D force-directed knowledge graph (miroFish-style canvas).
 *
 * Renders pre-computed nodes/links with Three.js via `3d-force-graph`:
 * - colored spheres sized by importance, always-visible text labels;
 * - auto-rotating camera until the user focuses a node;
 * - click a node → emits `select`, focuses the camera, pauses rotation;
 * - click empty space → emits `select(null)`, resumes rotation.
 *
 * Node/link objects are owned by the parent (stable references) so the force
 * simulation keeps node positions across re-renders; this component only
 * toggles the transient `highlighted` flag to emphasise the selection.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance, LinkObject, NodeObject } from '3d-force-graph'
import * as THREE from 'three'
import type { KgLink, KgNode } from '@/components/graph-types'

const props = defineProps<{
  nodes: KgNode[]
  links: KgLink[]
  selectedId: string | null
}>()

const emit = defineEmits<{
  (e: 'select', id: string | null): void
}>()

const container = ref<HTMLDivElement | null>(null)
let graph: ForceGraph3DInstance | null = null
let resizeObserver: ResizeObserver | null = null
const labelTextures = new Map<string, THREE.CanvasTexture>()

const FONT = `600 34px -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif`

function labelTexture(text: string): THREE.CanvasTexture {
  const cached = labelTextures.get(text)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const pad = 14
  ctx.font = FONT
  const textWidth = Math.ceil(ctx.measureText(text).width)
  canvas.width = textWidth + pad * 2
  canvas.height = 34 + pad * 2
  ctx.font = FONT
  ctx.textBaseline = 'middle'
  ctx.fillStyle = 'rgba(35, 41, 54, 0.94)'
  ctx.fillText(text, pad, canvas.height / 2)
  const tex = new THREE.CanvasTexture(canvas)
  tex.userData.aspect = canvas.width / canvas.height
  tex.anisotropy = 4
  labelTextures.set(text, tex)
  return tex
}

function buildNodeObject(node: KgNode): THREE.Object3D {
  const group = new THREE.Group()
  const radius = node.size * (node.highlighted ? 1.55 : 1)
  const color = new THREE.Color(node.color)

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 18, 14),
    new THREE.MeshPhongMaterial({
      color,
      emissive: color.clone().multiplyScalar(0.28),
      shininess: 16,
      transparent: true,
      opacity: node.highlighted ? 1 : 0.92,
    }),
  )
  group.add(sphere)

  if (node.highlighted) {
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(radius * 1.5, 18, 14),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.14 }),
    )
    group.add(halo)
  }

  const tex = labelTexture(node.name)
  const aspect = (tex.userData.aspect as number) ?? 3
  const labelHeight = Math.max(radius * 1.1, 2.4)
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }),
  )
  sprite.scale.set(labelHeight * aspect, labelHeight, 1)
  sprite.position.set(0, radius + labelHeight * 0.75, 0)
  group.add(sprite)

  return group
}

function applyData(): void {
  if (!graph) return
  graph.graphData({
    nodes: props.nodes as unknown as NodeObject[],
    links: props.links as unknown as LinkObject<NodeObject>[],
  })
}

function focusNode(id: string | null): void {
  if (!graph) return
  const controls = graph.controls() as { autoRotate?: boolean; autoRotateSpeed?: number }
  if (!id) {
    if (controls) controls.autoRotate = true
    return
  }
  if (controls) controls.autoRotate = false
  const node = (graph.graphData().nodes as unknown as (KgNode & { x: number; y: number; z: number })[]).find(
    (n) => n.id === id,
  )
  if (node && Number.isFinite(node.x)) {
    // Move the camera to keep its current viewing direction but re-aim at the node.
    const camera = graph.camera() as THREE.PerspectiveCamera
    const nodePos = new THREE.Vector3(node.x, node.y, node.z)
    const dir = new THREE.Vector3().subVectors(camera.position, nodePos)
    if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1)
    dir.normalize().multiplyScalar(150)
    const target = nodePos.clone().add(dir)
    graph.cameraPosition(
      { x: target.x, y: target.y, z: target.z },
      { x: node.x, y: node.y, z: node.z },
      800,
    )
  }
}

onMounted(() => {
  const el = container.value
  if (!el) return

  graph = new ForceGraph3D(el, { controlType: 'orbit' })
    .width(el.clientWidth)
    .height(el.clientHeight)
    .backgroundColor('rgba(0,0,0,0)')
    .showNavInfo(false)
    .nodeLabel((node: unknown) => (node as KgNode).label)
    .nodeThreeObject((node: unknown) => buildNodeObject(node as KgNode))
    .linkColor(() => '#c4cfdf')
    .linkOpacity(0.45)
    .linkWidth(0.7)
    .linkCurvature(0.08)
    .onNodeClick((node: unknown) => emit('select', (node as KgNode).id))
    .onBackgroundClick(() => emit('select', null))
    .enableNodeDrag(true)
    .warmupTicks(120)
    .cooldownTime(4000)

  // Keep the force graph centred when the container resizes.
  resizeObserver = new ResizeObserver(() => {
    if (!graph || !container.value) return
    graph.width(container.value.clientWidth).height(container.value.clientHeight)
  })
  resizeObserver.observe(el)

  const controls = graph.controls() as { autoRotate?: boolean; autoRotateSpeed?: number }
  if (controls) {
    controls.autoRotate = true
    controls.autoRotateSpeed = 0.55
  }

  applyData()
})

watch(
  () => [props.nodes, props.links],
  () => applyData(),
)

watch(
  () => props.selectedId,
  (id) => {
    for (const n of props.nodes) n.highlighted = n.id === id
    applyData()
    focusNode(id)
  },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (graph) {
    graph.pauseAnimation()
    graph._destructor()
    graph = null
  }
  labelTextures.clear()
})
</script>

<template>
  <div ref="container" class="kg-canvas-inner" />
</template>
