# TanStack Start (SSR via nitro) — built and served as a Node server.
# Node 24: its npm reads this lock file (npm 10 refuses a lock written by npm 11).
FROM node:24.21.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* at build time. Leave it empty: the browser then calls the API
# at the address it loaded the page from, which is what the proxy serves.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
# Build a Node server target instead of the config's default (cloudflare).
ENV NITRO_PRESET=node-server
RUN npm run build

FROM node:24.21.0-alpine AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
CMD ["node", ".output/server/index.mjs"]
