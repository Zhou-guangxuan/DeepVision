import { computed, ref, type Ref } from 'vue'

export const MIN_SCALE = 0.25
export const MAX_SCALE = 4

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/**
 * 画布视口：缩放（25%–400%）与平移。
 *
 * 世界坐标 → 屏幕坐标：screen = world * scale + translate
 */
export function useCanvasViewport(viewportRef: Ref<HTMLElement | null>) {
  const scale = ref(1)
  const tx = ref(0)
  const ty = ref(0)

  const transform = computed(
    () => `translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
  )

  const scalePercent = computed(() => Math.round(scale.value * 100))

  function screenToWorld(clientX: number, clientY: number) {
    const rect = viewportRef.value?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return {
      x: (clientX - rect.left - tx.value) / scale.value,
      y: (clientY - rect.top - ty.value) / scale.value,
    }
  }

  /** 以屏幕某点为锚点缩放，保证光标下的内容不漂移 */
  function zoomAt(clientX: number, clientY: number, factor: number): void {
    const rect = viewportRef.value?.getBoundingClientRect()
    if (!rect) return

    const nextScale = clamp(scale.value * factor, MIN_SCALE, MAX_SCALE)
    if (nextScale === scale.value) return

    const px = clientX - rect.left
    const py = clientY - rect.top
    const worldX = (px - tx.value) / scale.value
    const worldY = (py - ty.value) / scale.value

    scale.value = nextScale
    tx.value = px - worldX * nextScale
    ty.value = py - worldY * nextScale
  }

  function zoomAtCenter(factor: number): void {
    const rect = viewportRef.value?.getBoundingClientRect()
    if (!rect) return
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor)
  }

  function onWheel(event: WheelEvent): void {
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
    zoomAt(event.clientX, event.clientY, factor)
  }

  function panBy(dx: number, dy: number): void {
    tx.value += dx
    ty.value += dy
  }

  function reset(): void {
    scale.value = 1
    tx.value = 0
    ty.value = 0
  }

  /** 把指定世界坐标居中显示（小地图点击时使用） */
  function centerOn(worldX: number, worldY: number): void {
    const rect = viewportRef.value?.getBoundingClientRect()
    if (!rect) return
    tx.value = rect.width / 2 - worldX * scale.value
    ty.value = rect.height / 2 - worldY * scale.value
  }

  return {
    scale,
    tx,
    ty,
    transform,
    scalePercent,
    screenToWorld,
    zoomAt,
    zoomAtCenter,
    onWheel,
    panBy,
    reset,
    centerOn,
  }
}
