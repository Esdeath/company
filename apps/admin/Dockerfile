FROM node:24.18.0-alpine AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/admin/package.json apps/admin/package.json

RUN pnpm install --frozen-lockfile --filter @company/admin...

COPY apps/admin apps/admin

RUN pnpm --filter @company/admin build

FROM nginxinc/nginx-unprivileged:1.30.4-alpine AS runtime

COPY apps/admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/admin/dist /usr/share/nginx/html

EXPOSE 8080
