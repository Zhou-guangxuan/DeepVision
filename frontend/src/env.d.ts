/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 基地址；留空则使用 Vite 代理的相对路径 */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
