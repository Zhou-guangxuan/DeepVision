import type { LabActivation, LabInit, LabOptimizer } from '@/api/lab'

/** 教学任务的参数预设与达标条件 */

export interface TeachingPreset {
  inputUnits: number
  outputUnits: number
  hiddenLayers: number[]
  activation: LabActivation
  init: LabInit
  optimizer: LabOptimizer
  learningRate: number
  batchSize: number
  epochs: number
  l2: number
  dropout: number
}

export interface Checkpoint {
  question: string
  options: string[]
  answer: number
  explain: string
}

export type SuccessRule =
  | { metric: 'accuracy'; threshold: number }
  | { metric: 'issue'; codes: string[] }

export interface TeachingTask {
  id: string
  kind: 'goal' | 'pitfall'
  title: string
  goal: string
  hint: string
  preset: TeachingPreset
  success: SuccessRule
  checkpoints: Checkpoint[]
}

const BASE: TeachingPreset = {
  inputUnits: 2,
  outputUnits: 2,
  hiddenLayers: [64, 64],
  activation: 'relu',
  init: 'he',
  optimizer: 'adam',
  learningRate: 0.05,
  batchSize: 64,
  epochs: 200,
  l2: 0,
  dropout: 0,
}

export const TEACHING_TASKS: TeachingTask[] = [
  {
    id: 'spiral-baseline',
    kind: 'goal',
    title: '任务一：把双螺旋分开',
    goal: '理解「隐藏层 + 非线性激活」如何把线性不可分的数据分开',
    hint: '预设已是「64×64 两隐藏层、学习率 0.05、200 轮」，直接训练，观察验证准确率能否超过 0.9。',
    preset: { ...BASE },
    success: { metric: 'accuracy', threshold: 0.9 },
    checkpoints: [
      {
        question: '训练到一半，验证准确率长期停在 0.5 附近，最可能的原因是？',
        options: [
          '数据里根本没有可学习的信号',
          '模型还没学到可分的特征，需要更多训练或更强的网络',
          '验证集太小，统计噪声导致',
        ],
        answer: 1,
        explain:
          '0.5 是二分类的随机水平，说明模型暂时没学到区分性特征；先看训练 loss 是否还在下降，再看网络容量。',
      },
      {
        question: '隐藏层里的 ReLU 主要贡献是什么？',
        options: [
          '让参数量变少',
          '引入非线性，使网络能拟合弯曲的决策边界',
          '加快训练速度',
        ],
        answer: 1,
        explain:
          '若没有非线性激活，多层线性堆叠仍等价于单层线性模型，只能画出直线边界，分不开螺旋数据。',
      },
    ],
  },
  {
    id: 'lr-too-high',
    kind: 'pitfall',
    title: '错误示范：学习率过大',
    goal: '亲眼看到学习率过大会让 loss 震荡甚至发散',
    hint: '学习率被设为 1.0、批大小 8，直接训练，观察曲线是否剧烈跳动。',
    preset: {
      ...BASE,
      hiddenLayers: [8, 8],
      learningRate: 1.0,
      batchSize: 8,
      epochs: 40,
    },
    success: { metric: 'issue', codes: ['diverged', 'lr_too_high'] },
    checkpoints: [
      {
        question: '训练 loss 上下剧烈跳动、验证 loss 反而升高，说明？',
        options: [
          '学习率过大，参数在最优解附近来回跳过',
          '数据噪声太大，与学习率无关',
          '模型容量不足',
        ],
        answer: 0,
        explain:
          '步长超过了 loss 曲面的「谷宽」，参数会在谷底两侧反复横跳；把学习率降一个数量级通常就能稳定下来。',
      },
    ],
  },
  {
    id: 'too-narrow',
    kind: 'pitfall',
    title: '错误示范：隐藏层太窄',
    goal: '理解模型容量不足导致的欠拟合',
    hint: '隐藏层只有一个神经元，训练 60 轮后观察准确率与 loss。',
    preset: { ...BASE, hiddenLayers: [1], epochs: 60 },
    success: { metric: 'issue', codes: ['underfitting'] },
    checkpoints: [
      {
        question: '训练 loss 与验证 loss 都停在较高水平，说明？',
        options: [
          '过拟合，模型记住了训练集',
          '欠拟合，模型容量不足以拟合数据',
          '学习率过小',
        ],
        answer: 1,
        explain:
          '两个 loss 都高，说明模型连训练集都没学会（欠拟合）；增加层数 / 宽度或换更强的激活函数，而不是加正则。',
      },
    ],
  },
]
