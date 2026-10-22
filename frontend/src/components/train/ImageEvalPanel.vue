<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'

import type { ImageEvalData, ImageEvalSample } from '@/api/records'

/**
 * 图像训练评估：混淆矩阵 + 样本预测网格。
 * 像素矩阵直接画到 canvas，避免 256 个 DOM 节点。
 */
const props = defineProps<ImageEvalData>()

function labelOf(index: number): string {
  return props.classes[index] ?? `类别 ${index}`
}

function hotness(value: number): string {
  const max = Math.max(1, ...props.confusion.flat())
  const ratio = value / max
  return `rgba(34, 211, 238, ${(0.06 + 0.55 * ratio).toFixed(3)})`
}

function drawSample(
  element: Element | ComponentPublicInstance | null,
  sample: ImageEvalSample,
): void {
  if (!(element instanceof HTMLCanvasElement)) return
  const side = sample.pixels.length
  element.width = side
  element.height = side

  const context = element.getContext('2d')
  if (!context) return

  const image = context.createImageData(side, side)
  for (let row = 0; row < side; row += 1) {
    for (let column = 0; column < side; column += 1) {
      const value = sample.pixels[row][column]
      const offset = (row * side + column) * 4
      image.data[offset] = value
      image.data[offset + 1] = value
      image.data[offset + 2] = value
      image.data[offset + 3] = 255
    }
  }
  context.putImageData(image, 0, 0)
}
</script>

<template>
  <div class="grid gap-5 p-4 lg:grid-cols-2">
    <div>
      <p class="text-[11px] text-muted">混淆矩阵（行 = 真实，列 = 预测）</p>
      <table class="mt-2 w-full table-fixed text-center text-[11px]">
        <thead>
          <tr class="text-muted">
            <th class="py-1"></th>
            <th
              v-for="(name, index) in classes"
              :key="`head-${index}`"
              class="py-1 font-normal"
            >
              预测 {{ name }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, truth) in confusion" :key="`row-${truth}`">
            <th class="py-1 text-right font-normal text-muted">
              真实 {{ labelOf(truth) }}
            </th>
            <td
              v-for="(value, guess) in row"
              :key="`cell-${truth}-${guess}`"
              class="border py-1.5 font-mono text-secondary"
              :style="{
                borderColor: 'var(--border-subtle)',
                background: hotness(value),
              }"
            >
              {{ value }}
            </td>
          </tr>
        </tbody>
      </table>
      <p class="mt-2 text-[10px] leading-relaxed text-muted">
        对角线是判对的样本；非对角线的数值越大，说明两类越容易混。
      </p>
    </div>

    <div>
      <p class="text-[11px] text-muted">样本预测（红框 = 判错）</p>
      <div class="mt-2 grid grid-cols-6 gap-2">
        <div
          v-for="(sample, index) in samples"
          :key="index"
          class="flex flex-col items-center gap-1"
        >
          <canvas
            :ref="(element) => drawSample(element, sample)"
            class="w-full rounded-sm border-2"
            :style="{
              borderColor:
                sample.label === sample.prediction
                  ? 'var(--success)'
                  : 'var(--danger)',
              imageRendering: 'pixelated',
            }"
          />
          <span class="text-[9px] text-muted">
            {{ labelOf(sample.prediction) }} ·
            {{ (sample.probability * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
      <p class="mt-2 text-[10px] leading-relaxed text-muted">
        标签显示「预测类别 · 置信度」；判错的样本用红色边框标出。
      </p>
    </div>
  </div>
</template>
