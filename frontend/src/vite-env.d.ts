/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Commit the image was built from (set by the Docker build). */
  readonly VITE_GIT_SHA?: string
  /** Release version of the web app (Docker build arg APP_VERSION). */
  readonly VITE_APP_VERSION?: string
  /** When the image was built, ISO-8601 UTC (Docker build arg BUILD_TIME). */
  readonly VITE_BUILD_TIME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
