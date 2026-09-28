/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Commit the image was built from (set by the Docker build). */
  readonly VITE_GIT_SHA?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
