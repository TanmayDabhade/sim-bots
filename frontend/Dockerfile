FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# npm's lockfile can omit Linux-only optional packages when it is generated on
# macOS. `npm install` reconciles those platform entries inside the image while
# still honoring the exact direct versions recorded in package-lock.json.
RUN npm install --ignore-scripts

FROM node:24-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
