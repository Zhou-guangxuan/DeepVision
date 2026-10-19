<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

/**
 * 教学实验室的 3D 网络视图。
 *
 * 按「层」排布：层沿 X 轴展开，神经元沿 Y 轴排列，
 * 相邻层全连接，节点为发光球体，层名用 HTML 标签跟随投影位置。
 */

const props = defineProps<{
  /** 每层神经元数，例如 [2, 8, 8, 2] */
  layers: number[]
  activation: string
  /** 变化时重置相机 */
  resetToken: number
  /** 输入特征注意力，长度等于输入层神经元数；用于高亮输入层 */
  highlight?: number[]
}>()

const containerRef = ref<HTMLElement | null>(null)
const labelScreen = ref<{ x: number; y: number }[]>([])
const labelTexts = ref<string[]>([])

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let contentGroup: THREE.Group | null = null
let resizeObserver: ResizeObserver | null = null
let frameId = 0
const clock = new THREE.Clock()
const labelAnchors: THREE.Vector3[] = []

const FIRST_COLOR = 0x7dd3fc
const MIDDLE_COLOR = 0x22d3ee
const LAST_COLOR = 0xa78bfa
const SPACING_X = 140
const SPACING_Y = 34
const NODE_RADIUS = 7

function layerColor(index: number, total: number): number {
  if (index === 0) return FIRST_COLOR
  if (index === total - 1) return LAST_COLOR
  return MIDDLE_COLOR
}

function disposeGroup(group: THREE.Group | null): void {
  if (!group) return
  group.traverse((object) => {
    const mesh = object as THREE.Mesh
    mesh.geometry?.dispose()
    const material = mesh.material as
      THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(material)) material.forEach((item) => item.dispose())
    else material?.dispose()
  })
}

function rebuild(): void {
  if (!scene) return

  disposeGroup(contentGroup)
  if (contentGroup) scene.remove(contentGroup)
  contentGroup = new THREE.Group()
  labelAnchors.length = 0

  const layers = props.layers.length > 0 ? props.layers : [2, 2]
  const layerCount = layers.length
  const positions: THREE.Vector3[][] = []
  let maxSpread = 0

  layers.forEach((count, layerIndex) => {
    const x = (layerIndex - (layerCount - 1) / 2) * SPACING_X
    const nodes: THREE.Vector3[] = []

    for (let index = 0; index < count; index += 1) {
      const y = (index - (count - 1) / 2) * SPACING_Y
      nodes.push(new THREE.Vector3(x, y, 0))
    }

    positions.push(nodes)
    maxSpread = Math.max(maxSpread, count)

    const color = layerColor(layerIndex, layerCount)
    const geometry = new THREE.SphereGeometry(NODE_RADIUS, 20, 16)
    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.55,
      roughness: 0.3,
      metalness: 0.2,
    })

    const highlight = props.highlight ?? []
    const maxHighlight = Math.max(
      ...highlight.map((value) => Math.abs(value)),
      1e-9,
    )

    nodes.forEach((node, nodeIndex) => {
      const mesh = new THREE.Mesh(geometry.clone(), material.clone())
      mesh.position.copy(node)

      // 「注意力 3D」：输入层节点按特征贡献提升自发光
      if (layerIndex === 0 && highlight.length > nodeIndex) {
        const ratio = Math.min(Math.abs(highlight[nodeIndex]) / maxHighlight, 1)
        mesh.material.emissiveIntensity = 0.55 + ratio * 1.6
        mesh.scale.setScalar(1 + ratio * 0.35)
      }

      contentGroup?.add(mesh)
    })

    labelAnchors.push(new THREE.Vector3(x, (maxSpread / 2) * SPACING_Y + 46, 0))
  })

  // 相邻层全连接
  const linePositions: number[] = []
  for (let layerIndex = 0; layerIndex < positions.length - 1; layerIndex += 1) {
    for (const from of positions[layerIndex]) {
      for (const to of positions[layerIndex + 1]) {
        linePositions.push(from.x, from.y, from.z, to.x, to.y, to.z)
      }
    }
  }

  const lineGeometry = new THREE.BufferGeometry()
  lineGeometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(linePositions, 3),
  )
  const lineMaterial = new THREE.LineBasicMaterial({
    color: 0x64748b,
    transparent: true,
    opacity: 0.32,
  })
  contentGroup.add(new THREE.LineSegments(lineGeometry, lineMaterial))

  labelTexts.value = layers.map((count, index) => {
    if (index === 0) return `输入层 (${count})`
    if (index === layers.length - 1) return `输出层 (${count})`
    return `隐藏层 ${index} (${count}) · ${props.activation}`
  })

  scene.add(contentGroup)
  resetView()
}

function resetView(): void {
  if (!camera || !controls) return
  camera.position.set(
    0,
    70,
    SPACING_X * Math.max(props.layers.length, 2) * 1.05,
  )
  camera.lookAt(0, 0, 0)
  controls.target.set(0, 0, 0)
  controls.update()
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

function updateLabels(): void {
  const container = containerRef.value
  if (!container || !camera) return

  const width = container.clientWidth
  const height = container.clientHeight
  const results: { x: number; y: number }[] = []

  for (const anchor of labelAnchors) {
    const projected = anchor.clone().project(camera)
    results.push({
      x: (projected.x * 0.5 + 0.5) * width,
      y: (-projected.y * 0.5 + 0.5) * height,
    })
  }

  labelScreen.value = results
}

function animate(): void {
  frameId = requestAnimationFrame(animate)
  if (!renderer || !scene || !camera) return

  const elapsed = clock.getElapsedTime()
  if (contentGroup) {
    contentGroup.children.forEach((child) => {
      const mesh = child as THREE.Mesh
      if (mesh.isMesh && mesh.material instanceof THREE.MeshStandardMaterial) {
        mesh.material.emissiveIntensity =
          0.45 + 0.18 * Math.sin(elapsed * 1.6 + mesh.position.x * 0.02)
      }
    })
  }

  controls?.update()
  renderer.render(scene, camera)
  updateLabels()
}

onMounted(() => {
  const container = containerRef.value
  if (!container) return

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(
    45,
    Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
    1,
    8000,
  )

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(container.clientWidth, container.clientHeight)
  container.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.09

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const key = new THREE.DirectionalLight(0xffffff, 1.2)
  key.position.set(180, 260, 320)
  scene.add(key)
  const rim = new THREE.PointLight(0x22d3ee, 1.4, 2000)
  rim.position.set(-260, -160, 220)
  scene.add(rim)

  resizeObserver = new ResizeObserver(handleResize)
  resizeObserver.observe(container)

  rebuild()
  animate()
})

watch(
  () => [props.layers, props.activation, props.highlight],
  () => rebuild(),
  { deep: true },
)

watch(
  () => props.resetToken,
  () => resetView(),
)

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
  controls?.dispose()
  disposeGroup(contentGroup)
  if (renderer) {
    renderer.dispose()
    renderer.domElement.parentElement?.removeChild(renderer.domElement)
    renderer = null
  }
  scene = null
  camera = null
  controls = null
})
</script>

<template>
  <div class="relative h-full w-full">
    <div ref="containerRef" class="h-full w-full" />

    <div
      v-for="(text, index) in labelTexts"
      :key="text"
      class="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-md border px-2 py-1 text-[11px]"
      :style="{
        left: `${labelScreen[index]?.x ?? 0}px`,
        top: `${labelScreen[index]?.y ?? 0}px`,
        borderColor: 'var(--border-default)',
        background: 'rgba(17, 24, 39, 0.85)',
        color: 'var(--text-secondary)',
      }"
    >
      {{ text }}
    </div>

    <p
      class="pointer-events-none absolute bottom-2 left-3 text-[11px] text-muted"
    >
      左键拖拽旋转 · 滚轮缩放 · 右键拖拽平移
    </p>
  </div>
</template>
