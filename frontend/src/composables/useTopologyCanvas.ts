import { onBeforeUnmount, onMounted, type Ref } from 'vue'

interface TopologyNode {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  phase: number
}

/**
 * 登录页品牌区的网络拓扑装饰动画。
 *
 * - 节点缓慢漂移，间距足够近时用青→紫渐变现连线；
 * - `prefers-reduced-motion` 生效时只绘制静态画面，不做位移。
 */
export function useTopologyCanvas(
  canvasRef: Ref<HTMLCanvasElement | null>,
  nodeCount = 28,
): void {
  let ctx: CanvasRenderingContext2D | null = null
  let raf = 0
  let width = 0
  let height = 0
  let nodes: TopologyNode[] = []
  let observer: ResizeObserver | null = null

  const reduceMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  function seed(): void {
    nodes = Array.from({ length: nodeCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.28,
      vy: (Math.random() - 0.5) * 0.28,
      r: 1.2 + Math.random() * 1.6,
      phase: Math.random() * Math.PI * 2,
    }))
  }

  function resize(): void {
    const canvas = canvasRef.value
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    width = rect.width
    height = rect.height
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(height * dpr)
    ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    seed()
  }

  function draw(time: number): void {
    raf = window.requestAnimationFrame(draw)
    if (!ctx) return

    ctx.clearRect(0, 0, width, height)

    if (!reduceMotion) {
      for (const node of nodes) {
        node.x += node.vx
        node.y += node.vy
        if (node.x <= 0 || node.x >= width) node.vx *= -1
        if (node.y <= 0 || node.y >= height) node.vy *= -1
      }
    }

    const maxDistance = 190

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i]
        const b = nodes[j]
        const distance = Math.hypot(a.x - b.x, a.y - b.y)
        if (distance > maxDistance) continue

        const alpha = (1 - distance / maxDistance) * 0.32
        const gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y)
        gradient.addColorStop(0, `rgba(34, 211, 238, ${alpha})`)
        gradient.addColorStop(1, `rgba(139, 92, 246, ${alpha})`)

        ctx.strokeStyle = gradient
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
    }

    for (const node of nodes) {
      // 呼吸效果：半径随时间轻微起伏
      const breath = reduceMotion ? 1 : 0.85 + Math.sin(time / 900 + node.phase) * 0.15
      ctx.beginPath()
      ctx.fillStyle = 'rgba(34, 211, 238, 0.85)'
      ctx.shadowColor = 'rgba(34, 211, 238, 0.75)'
      ctx.shadowBlur = 10
      ctx.arc(node.x, node.y, node.r * breath, 0, Math.PI * 2)
      ctx.fill()
      ctx.shadowBlur = 0
    }
  }

  onMounted(() => {
    const canvas = canvasRef.value
    if (!canvas) return

    resize()
    raf = window.requestAnimationFrame(draw)

    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => resize())
      observer.observe(canvas)
    }
  })

  onBeforeUnmount(() => {
    window.cancelAnimationFrame(raf)
    observer?.disconnect()
    observer = null
    ctx = null
  })
}
