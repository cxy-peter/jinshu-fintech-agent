# Optional additive pi build; the original engine remains byte-for-byte unchanged.
FROM python:3.11-alpine AS prepare
WORKDIR /src
COPY engine/services/pi-agent /src/engine/services/pi-agent
COPY services/pi-agent-overlay /src/services/pi-agent-overlay
RUN python services/pi-agent-overlay/prepare.py /prepared

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=prepare /prepared/package.json /prepared/package-lock.json ./
RUN npm ci --ignore-scripts
COPY --from=prepare /prepared/tsconfig.json ./
COPY --from=prepare /prepared/src ./src
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=prepare /prepared/package.json /prepared/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY --from=build /app/dist ./dist
EXPOSE 8100
CMD ["node", "dist/index.js"]
