/**
 * 轻量 CSV 解析与列类型推断。
 *
 * 设计文档原定使用 PapaParse，但本机 npm 依赖树损坏（`Invalid Version`）且
 * `node_modules` 被运行中的 dev server 占用，无法安装；改为自研解析器，
 * 覆盖引号、转义双引号、字段内换行、CRLF 与 BOM 等常见情况。
 */

export type ColumnDtype = 'number' | 'category' | 'date'
export type MissingStrategy = 'mean' | 'median' | 'mode' | 'drop'

export interface ParsedCsv {
  headers: string[]
  rows: string[][]
}

export interface ColumnProfile {
  name: string
  dtype: ColumnDtype
  missing: number
}

const DATE_PATTERN = /^\d{4}-\d{1,2}-\d{1,2}$/

export function parseCsv(text: string): ParsedCsv {
  const input = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  const records: string[][] = []

  let field = ''
  let record: string[] = []
  let inQuotes = false
  let index = 0

  const pushField = (): void => {
    record.push(field)
    field = ''
  }

  const pushRecord = (): void => {
    pushField()
    // 跳过完全空白的行
    const isBlank = record.length === 1 && record[0].trim() === ''
    if (!isBlank) records.push(record)
    record = []
  }

  while (index < input.length) {
    const char = input[index]

    if (inQuotes) {
      if (char === '"') {
        if (input[index + 1] === '"') {
          field += '"'
          index += 2
          continue
        }
        inQuotes = false
        index += 1
        continue
      }
      field += char
      index += 1
      continue
    }

    if (char === '"') {
      inQuotes = true
      index += 1
      continue
    }

    if (char === ',') {
      pushField()
      index += 1
      continue
    }

    if (char === '\r') {
      if (input[index + 1] === '\n') index += 1
      pushRecord()
      index += 1
      continue
    }

    if (char === '\n') {
      pushRecord()
      index += 1
      continue
    }

    field += char
    index += 1
  }

  if (field !== '' || record.length > 0) pushRecord()

  if (records.length === 0) return { headers: [], rows: [] }

  const [headers, ...rows] = records
  return { headers: headers.map((header) => header.trim()), rows }
}

function isNumeric(value: string): boolean {
  return value !== '' && Number.isFinite(Number(value))
}

export function profileColumns(
  headers: string[],
  rows: string[][],
): ColumnProfile[] {
  return headers.map((name, columnIndex) => {
    let missing = 0
    let nonEmpty = 0
    let allNumeric = true
    let allDate = true

    for (const row of rows) {
      const value = (row[columnIndex] ?? '').trim()
      if (value === '') {
        missing += 1
        continue
      }
      nonEmpty += 1
      if (allNumeric && !isNumeric(value)) allNumeric = false
      if (allDate && !DATE_PATTERN.test(value)) allDate = false
    }

    let dtype: ColumnDtype = 'category'
    if (nonEmpty > 0 && allNumeric) dtype = 'number'
    else if (nonEmpty > 0 && allDate) dtype = 'date'

    return { name, dtype, missing }
  })
}

/** 按缺失值策略计算处理后剩余样本数（与后端 dropna 语义一致） */
export function countProcessedRows(
  rows: string[][],
  headers: string[],
  selectedColumns: string[],
  strategy: MissingStrategy,
): number {
  if (strategy !== 'drop') return rows.length

  const indices = selectedColumns
    .map((name) => headers.indexOf(name))
    .filter((index) => index >= 0)

  if (indices.length === 0) return 0

  return rows.filter((row) =>
    indices.every((index) => (row[index] ?? '').trim() !== ''),
  ).length
}
