/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** SSE endpoint for live backend events. Unset = use the mock replayer. */
  readonly VITE_SSE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
