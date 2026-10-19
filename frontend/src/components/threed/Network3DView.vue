<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

import { useGraphStore } from '@/stores/graph'
import {
  NODE_TYPE_LABEL,
  nodeSummary,
  type GraphEdge,
  type GraphNode,
} from '@/types/graph'

/**
 * 第二大阶段模块一：3D 神经网络拓扑可视化（只读）。
 *
 * - 节点渲染为发光球体，按层类型着色；
 * - 连线用 TubeGeometry，粗细与不透明度由当前视图模式对应的逐层指标决定；
 * - 激活模式下节点光晕做呼吸动画；
 * - 左键旋转、滚轮缩放、右键平移（OrbitControls 默认行为）。
 */

const NODE_COLOR: Record<string, number> = {
  input: 0x7dd3fc,
  hidden: 0x22d3ee,
  output: 0xa78bfa,
}

const store = useGraphStore()

const containerRef = ref<HTMLElement | null>(null)
const hoverInfo = ref<{ title: string; detail: string } | null>(null)
const hoverPos = ref({ x: 0, y: 0 })
const webglFailed = ref(false)
const fps = ref(0)
/** 全局亮度（toneMappingExposure），便于按显示器自行调节 */
const brightness = ref(1)

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let raycaster: THREE.Raycaster | null = null
let resizeObserver: ResizeObserver | null = null
let frameId = 0
let frameCount = 0
let fpsWindowStart = performance.now()
let glowTextureCache: THREE.Texture | null = null
const clock = new THREE.Clock()

let nodeGroup: THREE.Group | null = null
let edgeGroup: THREE.Group | null = null
const halos: {
  sprite: THREE.Sprite
  phase: number
  base: number
}[] = []
const nodeMeshes: THREE.Mesh[] = []
const edgeMeshes: THREE.Mesh[] = []
const nodeLookup = new Map<THREE.Object3D, string>()
const edgeLookup = new Map<THREE.Object3D, GraphEdge>()

const metricKey = computed(() =>
  store.viewMode === 'weight'
    ? 'weight_norm'
    : store.viewMode === 'gradient'
      ? 'grad_norm'
      : 'activation_mean',
)

const metricByNode = computed(() => {
  const key = metricKey.value
  const result: Record<string, number> = {}
  for (const [id, stat] of Object.entries(store.layerStats)) {
    result[id] = Number(stat[key] ?? 0)
  }
  return result
})

const maxMetric = computed(() => {
  const values = Object.values(metricByNode.value)
  return values.length > 0 ? Math.max(...values, 1e-9) : 0
})

function nodeIntensity(nodeId: string): number {
  if (!store.layerStatsLoaded || maxMetric.value <= 0) return 0
  return Math.min(1, (metricByNode.value[nodeId] ?? 0) / maxMetric.value)
}

function edgeIntensity(edge: GraphEdge): number {
  if (!store.layerStatsLoaded || maxMetric.value <= 0) return 0
  const id = store.viewMode === 'activation' ? edge.source : edge.target
  return Math.min(1, (metricByNode.value[id] ?? 0) / maxMetric.value)
}

function formatMetric(value: number | undefined): string {
  if (value === undefined) return '—'
  if (value >= 1000) return value.toFixed(0)
  if (value >= 1) return value.toFixed(2)
  return value.toFixed(4)
}

function nodeRadius(node: GraphNode): number {
  const raw =
    node.type === 'input'
      ? Number(node.params.features ?? 8)
      : Number(node.params.units ?? 16)
  return 9 + Math.min(Math.max(raw, 1), 64) * 0.45
}

function glowTexture(): THREE.Texture {
  if (glowTextureCache) return glowTextureCache

  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  if (context) {
    const gradient = context.createRadialGradient(
      size / 2,
      size / 2,
      0,
      size / 2,
      size / 2,
      size / 2,
    )
    gradient.addColorStop(0, 'rgba(255, 255, 255, 0.9)')
    gradient.addColorStop(0.35, 'rgba(255, 255, 255, 0.35)')
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
    context.fillStyle = gradient
    context.fillRect(0, 0, size, size)
  }

  glowTextureCache = new THREE.CanvasTexture(canvas)
  return glowTextureCache
}

/** 按拓扑层级把节点分层排列：层级越大，沿 Z 轴越靠后 */
function computeLevels(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<string, number> {
  const indegree = new Map<string, number>()
  const adjacency = new Map<string, string[]>()

  for (const node of nodes) {
    indegree.set(node.id, 0)
    adjacency.set(node.id, [])
  }
  for (const edge of edges) {
    if (!adjacency.has(edge.source) || !indegree.has(edge.target)) continue
    adjacency.get(edge.source)?.push(edge.target)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  }

  const levels = new Map<string, number>()
  const queue: string[] = []
  for (const [id, degree] of indegree) {
    if (degree === 0) {
      levels.set(id, 0)
      queue.push(id)
    }
  }

  while (queue.length > 0) {
    const current = queue.shift() as string
    const currentLevel = levels.get(current) ?? 0
    for (const next of adjacency.get(current) ?? []) {
      levels.set(next, Math.max(levels.get(next) ?? 0, currentLevel + 1))
      const remaining = (indegree.get(next) ?? 1) - 1
      indegree.set(next, remaining)
      if (remaining === 0) queue.push(next)
    }
  }

  for (const node of nodes) {
    if (!levels.has(node.id)) levels.set(node.id, 0)
  }
  return levels
}

function buildPositions(): Map<string, THREE.Vector3> {
  const levels = computeLevels(store.nodes, store.edges)
  const maxLevel = Math.max(0, ...levels.values())
  const positions = new Map<string, THREE.Vector3>()

  // 优先沿用 2D 画布的手工坐标，保留用户的布局意图；只有所有节点都挤在一起时才回退到自动布局
  const xs = store.nodes.map((node) => Number(node.x ?? 0))
  const ys = store.nodes.map((node) => Number(node.y ?? 0))
  const spreadX = xs.length > 0 ? Math.max(...xs) - Math.min(...xs) : 0
  const spreadY = ys.length > 0 ? Math.max(...ys) - Math.min(...ys) : 0
  const useManualLayout =
    store.nodes.length > 1 && (spreadX > 150 || spreadY > 150)

  if (useManualLayout) {
    for (const node of store.nodes) {
      const level = levels.get(node.id) ?? 0
      positions.set(
        node.id,
        new THREE.Vector3(
          Number(node.x ?? 0) * 0.9,
          -Number(node.y ?? 0) * 0.9,
          (level - maxLevel / 2) * 120,
        ),
      )
    }
    return positions
  }

  const grouped = new Map<number, GraphNode[]>()

  for (const node of store.nodes) {
    const level = levels.get(node.id) ?? 0
    if (!grouped.has(level)) grouped.set(level, [])
    grouped.get(level)?.push(node)
  }

  const spacing = 150

  for (const [level, list] of grouped) {
    const z = (level - maxLevel / 2) * spacing
    const radius = Math.max(70, list.length * 20)
    list.forEach((node, index) => {
      const angle = (index / Math.max(list.length, 1)) * Math.PI * 2
      positions.set(
        node.id,
        new THREE.Vector3(
          Math.cos(angle) * radius,
          Math.sin(angle) * radius * 0.6,
          z,
        ),
      )
    })
  }

  return positions
}

function disposeGroup(group: THREE.Group | null): void {
  if (!group) return
  group.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (mesh.geometry) mesh.geometry.dispose()
    const material = mesh.material as
      THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(material)) {
      material.forEach((item) => item.dispose())
    } else {
      material?.dispose()
    }
  })
}

function frameCamera(positions: Map<string, THREE.Vector3>): void {
  if (!camera || !controls) return

  const box = new THREE.Box3()
  for (const point of positions.values()) box.expandByPoint(point)
  if (box.isEmpty()) {
    box.setFromCenterAndSize(
      new THREE.Vector3(),
      new THREE.Vector3(240, 240, 240),
    )
  }

  const sphere = box.getBoundingSphere(new THREE.Sphere())
  // 相机稍微拉近，节点在画面里更饱满
  const distance = sphere.radius * 2.1 + 140

  camera.position.set(0, distance * 0.42, distance)
  camera.lookAt(sphere.center)
  controls.target.copy(sphere.center)
  controls.update()
}

function rebuild(): void {
  if (!scene) return

  disposeGroup(nodeGroup)
  disposeGroup(edgeGroup)
  if (nodeGroup) scene.remove(nodeGroup)
  if (edgeGroup) scene.remove(edgeGroup)

  nodeGroup = new THREE.Group()
  edgeGroup = new THREE.Group()

  halos.length = 0
  nodeMeshes.length = 0
  edgeMeshes.length = 0
  nodeLookup.clear()
  edgeLookup.clear()

  const positions = buildPositions()

  for (const node of store.nodes) {
    const position = positions.get(node.id)
    if (!position) continue

    const color = NODE_COLOR[node.type] ?? 0x94a3b8
    const radius = nodeRadius(node)
    const intensity = nodeIntensity(node.id)

    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.85 + intensity * 0.6,
      roughness: 0.25,
      metalness: 0.1,
    })
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 28, 20),
      material,
    )
    mesh.position.copy(position)
    nodeGroup.add(mesh)
    nodeMeshes.push(mesh)
    nodeLookup.set(mesh, node.id)

    const halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glowTexture(),
        color,
        transparent: true,
        opacity: 0.32 + intensity * 0.4,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    halo.scale.setScalar(radius * 4.2)
    halo.position.copy(position)
    nodeGroup.add(halo)
    halos.push({
      sprite: halo,
      phase: Math.random() * Math.PI * 2,
      base: 0.32 + intensity * 0.4,
    })
  }

  for (const edge of store.edges) {
    const from = positions.get(edge.source)
    const to = positions.get(edge.target)
    if (!from || !to) continue

    const intensity = edgeIntensity(edge)
    const curve = new THREE.LineCurve3(from, to)
    const geometry = new THREE.TubeGeometry(
      curve,
      1,
      0.9 + intensity * 3,
      8,
      false,
    )
    const material = new THREE.MeshBasicMaterial({
      color: 0x94a3b8,
      transparent: true,
      opacity: 0.5 + intensity * 0.45,
    })
    const mesh = new THREE.Mesh(geometry, material)
    edgeGroup.add(mesh)
    edgeMeshes.push(mesh)
    edgeLookup.set(mesh, edge)
  }

  scene.add(nodeGroup)
  scene.add(edgeGroup)
  frameCamera(positions)
}

function onPointerMove(event: PointerEvent): void {
  if (!containerRef.value || !camera || !raycaster) return

  const rect = containerRef.value.getBoundingClientRect()
  const ndc = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  )

  raycaster.setFromCamera(ndc, camera)
  const hits = raycaster.intersectObjects([...nodeMeshes, ...edgeMeshes], false)

  if (hits.length === 0) {
    hoverInfo.value = null
    return
  }

  const target = hits[0].object
  hoverPos.value = {
    x: event.clientX - rect.left + 14,
    y: event.clientY - rect.top + 14,
  }

  const nodeId = nodeLookup.get(target)
  if (nodeId) {
    const node = store.nodes.find((item) => item.id === nodeId)
    if (!node) {
      hoverInfo.value = null
      return
    }
    const stat = store.layerStats[nodeId]
    hoverInfo.value = {
      title: `${NODE_TYPE_LABEL[node.type]} · ${nodeSummary(node)}`,
      detail: `权重 ${formatMetric(stat?.weight_norm)} · 梯度 ${formatMetric(
        stat?.grad_norm,
      )} · 激活 ${formatMetric(stat?.activation_mean)}`,
    }
    return
  }

  const edge = edgeLookup.get(target)
  if (edge) {
    hoverInfo.value = {
      title: `连线 ${edge.source} → ${edge.target}`,
      detail: store.layerStatsLoaded
        ? `当前视图指标 ${formatMetric(
            metricByNode.value[
              store.viewMode === 'activation' ? edge.source : edge.target
            ],
          )}`
        : '训练后可查看逐层指标',
    }
    return
  }

  hoverInfo.value = null
}

function handleResize(): void {
  const container = containerRef.value
  if (!container || !renderer || !camera) return

  const width = container.clientWidth
  const height = container.clientHeight
  if (width === 0 || height === 0) return

  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
}

function animate(): void {
  frameId = requestAnimationFrame(animate)
  if (!renderer || !scene || !camera) return

  const elapsed = clock.getElapsedTime()
  if (store.viewMode === 'activation') {
    for (const halo of halos) {
      halo.sprite.material.opacity =
        halo.base * (0.55 + 0.45 * Math.sin(elapsed * 2.2 + halo.phase))
    }
  }

  controls?.update()
  renderer.render(scene, camera)

  frameCount += 1
  const now = performance.now()
  if (now - fpsWindowStart >= 500) {
    fps.value = Math.round((frameCount * 1000) / (now - fpsWindowStart))
    frameCount = 0
    fpsWindowStart = now
  }
}

/** 把当前画面导出为 PNG（需 renderer 开启 preserveDrawingBuffer） */
function exportImage(): void {
  if (!renderer || !scene || !camera) return
  renderer.render(scene, camera)
  const link = document.createElement('a')
  link.href = renderer.domElement.toDataURL('image/png')
  link.download = `deepvision-3d-${Date.now()}.png`
  link.click()
}

onMounted(() => {
  const container = containerRef.value
  if (!container) return

  try {
    scene = new THREE.Scene()
    // 雾只用极淡的一层做景深，密度过高会把远处节点压成黑块
    scene.fog = new THREE.FogExp2(0x0a0e1a, 0.00015)

    camera = new THREE.PerspectiveCamera(
      45,
      Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
      1,
      8000,
    )

    renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    })
    renderer.toneMapping = THREE.LinearToneMapping
    renderer.toneMappingExposure = brightness.value
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(container.clientWidth, container.clientHeight)
    container.appendChild(renderer.domElement)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = 120
    controls.maxDistance = 4000

    raycaster = new THREE.Raycaster()

    scene.add(new THREE.AmbientLight(0xffffff, 0.95))
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.6)
    keyLight.position.set(240, 320, 420)
    scene.add(keyLight)
    const fillLight = new THREE.DirectionalLight(0x7dd3fc, 0.7)
    fillLight.position.set(-320, -200, 260)
    scene.add(fillLight)
    const rimLight = new THREE.PointLight(0x22d3ee, 1.6, 2400)
    rimLight.position.set(-320, -220, 260)
    scene.add(rimLight)

    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(container)

    rebuild()
    animate()
  } catch {
    webglFailed.value = true
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
  resizeObserver = null

  controls?.dispose()
  controls = null

  disposeGroup(nodeGroup)
  disposeGroup(edgeGroup)
  nodeGroup = null
  edgeGroup = null

  if (renderer) {
    renderer.dispose()
    renderer.domElement.parentElement?.removeChild(renderer.domElement)
    renderer = null
  }

  scene = null
  camera = null
  raycaster = null
})

watch(
  () => [store.nodes, store.edges, store.viewMode, store.layerStats],
  () => rebuild(),
  { deep: true },
)

watch(brightness, (value) => {
  if (renderer) renderer.toneMappingExposure = value
})
</script>

<template>
  <div
    class="relative h-full w-full"
    style="
      background: radial-gradient(
        circle at 50% 42%,
        #0e1729 0%,
        #070c16 62%,
        #04070f 100%
      );
    "
  >
    <div
      ref="containerRef"
      class="h-full w-full"
      @pointermove="onPointerMove"
      @pointerleave="hoverInfo = null"
    />

    <div
      class="pointer-events-none absolute left-3 top-3 rounded-md border px-3 py-1.5 text-[11px]"
      :style="{
        borderColor: 'var(--border-subtle)',
        background: 'rgba(17, 24, 39, 0.85)',
        color: 'var(--text-secondary)',
      }"
    >
      3D 只读视图 · 左键旋转 · 滚轮缩放 · 右键平移
    </div>

    <div class="absolute right-3 top-3 flex items-center gap-2">
      <span
        class="rounded-md border px-2 py-1 font-mono text-[10px] text-secondary"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'rgba(17, 24, 39, 0.85)',
        }"
        title="实时帧率，用于确认 100 节点内是否达到 30fps"
      >
        {{ fps }} fps
      </span>
      <label
        class="flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] text-secondary"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'rgba(17, 24, 39, 0.85)',
        }"
        title="整体亮度"
      >
        亮度
        <input
          v-model.number="brightness"
          type="range"
          min="0.6"
          max="2.5"
          step="0.1"
          class="h-1 w-16 cursor-pointer accent-[var(--brand-cyan)]"
        />
      </label>
      <button
        type="button"
        class="rounded-md border px-2 py-1 text-[10px] text-secondary transition-colors duration-fast hover:text-primary"
        :style="{
          borderColor: 'var(--border-subtle)',
          background: 'rgba(17, 24, 39, 0.85)',
        }"
        @click="exportImage"
      >
        导出图片
      </button>
    </div>

    <div
      v-if="store.nodes.length === 0"
      class="pointer-events-none absolute inset-0 grid place-items-center"
    >
      <p class="text-sm text-muted">
        画布为空，切回 2D 搭建网络后再查看 3D 视图
      </p>
    </div>

    <div
      v-if="webglFailed"
      class="pointer-events-none absolute inset-0 grid place-items-center"
    >
      <p class="text-sm text-danger">
        当前环境无法初始化 WebGL，3D 视图不可用（2D 画布不受影响）
      </p>
    </div>

    <div
      v-if="hoverInfo"
      class="pointer-events-none absolute z-10 max-w-[240px] rounded-md border px-2.5 py-1.5 text-[11px] leading-relaxed"
      :style="{
        left: `${hoverPos.x}px`,
        top: `${hoverPos.y}px`,
        borderColor: 'var(--border-default)',
        background: 'rgba(26, 34, 52, 0.95)',
        color: 'var(--text-primary)',
      }"
    >
      <p class="font-medium">{{ hoverInfo.title }}</p>
      <p class="mt-0.5 text-secondary">{{ hoverInfo.detail }}</p>
    </div>
  </div>
</template>
