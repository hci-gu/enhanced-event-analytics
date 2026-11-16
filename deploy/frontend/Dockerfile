FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --exclude=.env --exclude=node_modules --exclude=dist frontend/ ./
RUN pnpm build

FROM nginxinc/nginx-unprivileged:alpine
COPY deploy/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
