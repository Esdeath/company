FROM node:24.18.0-alpine AS deps

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --frozen-lockfile --filter @company/web...

FROM deps AS build

COPY apps/web/nuxt.config.ts apps/web/tsconfig.json apps/web/eslint.config.mjs apps/web/vitest.config.ts apps/web/
COPY apps/web/app apps/web/app
COPY apps/web/public apps/web/public
COPY apps/web/server apps/web/server

RUN pnpm --filter @company/web build

FROM node:24.18.0-alpine AS runtime

WORKDIR /app

ENV HOST=0.0.0.0 \
    PORT=3000 \
    NODE_ENV=production

COPY --from=build --chown=node:node /workspace/apps/web/.output ./

USER node

EXPOSE 3000

CMD ["node", "server/index.mjs"]
