FROM node:20-alpine AS base

WORKDIR /app

FROM base AS deps

COPY package*.json ./
RUN npm ci

FROM deps AS development

ENV NODE_ENV=development

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]

FROM deps AS builder

ARG NEXT_PUBLIC_API_URL
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY . .

RUN npm run build

FROM base AS production-deps

COPY package*.json ./
RUN npm ci --omit=dev

FROM base AS production

ARG NEXT_PUBLIC_API_URL
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY --from=production-deps /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
