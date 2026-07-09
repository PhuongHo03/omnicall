FROM node:22-alpine

RUN apk add --no-cache wget

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN npm ci

COPY frontend /app/frontend

EXPOSE 5173

CMD ["npm", "run", "dev"]
