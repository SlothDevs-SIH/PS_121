# SMRITI frontend image: build the SPA with Node, serve it with nginx.
# Override NODE_IMAGE / NGINX_IMAGE to build from an internal mirror or a base image that
# trusts a corporate TLS-inspection CA.
# Pinned by digest (the multi-arch index; backend/tests/unit/test_image_pins.py checks it). To
# update: docker buildx imagetools inspect node:22-alpine (and nginx:1.28-alpine)
ARG NODE_IMAGE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
ARG NGINX_IMAGE=nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG GIT_SHA=dev
ARG APP_VERSION=dev
ARG BUILD_TIME=""
ENV VITE_GIT_SHA=$GIT_SHA \
    VITE_APP_VERSION=$APP_VERSION \
    VITE_BUILD_TIME=$BUILD_TIME
RUN npm run build

FROM ${NGINX_IMAGE}
ENV API_UPSTREAM=http://api:8000 \
    MAP_TILE_URL="" \
    MAP_TILE_ATTRIBUTION="" \
    MAP_TILE_ORIGIN="" \
    GRAFANA_URL=""
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
