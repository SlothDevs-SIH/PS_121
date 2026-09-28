# SMRITI frontend image: build the SPA with Node, serve it with nginx.
# Override NODE_IMAGE / NGINX_IMAGE to build from an internal mirror or a base image that
# trusts a corporate TLS-inspection CA.
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.28-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG GIT_SHA=dev
ENV VITE_GIT_SHA=$GIT_SHA
RUN npm run build

FROM ${NGINX_IMAGE}
ENV API_UPSTREAM=http://api:8000 \
    MAP_TILE_URL="" \
    MAP_TILE_ATTRIBUTION="" \
    MAP_TILE_ORIGIN=""
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
