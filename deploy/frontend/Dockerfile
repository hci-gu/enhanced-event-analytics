FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --exclude=.env --exclude=node_modules --exclude=dist frontend/ ./
RUN pnpm build

FROM golang:1.27-alpine AS gateway-build
WORKDIR /src
COPY deploy/frontend/gateway.go ./
RUN CGO_ENABLED=0 go build -o /gateway gateway.go

FROM tailscale/tailscale:stable AS tailscale

FROM nginxinc/nginx-unprivileged:alpine
COPY --from=tailscale /usr/local/bin/tailscale /usr/local/bin/tailscaled /usr/local/bin/
COPY --from=gateway-build /gateway /usr/local/bin/gateway
COPY deploy/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/gateway"]
