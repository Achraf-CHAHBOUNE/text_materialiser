# TanStack Start (SSR via nitro) — built and served as a Node server.
# Node 24: its npm reads this lock file. node:20-alpine ships npm 10.8, which
# refuses a lock written by npm 11 ("Missing: lru-cache from lock file") and the
# image could not be built at all.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* at build time; override with --build-arg VITE_API_URL=...
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# Build a Node server target instead of the config's default (cloudflare).
ENV NITRO_PRESET=node-server
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/.output ./.output
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
