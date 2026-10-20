# Etapa 1 — build estático com Node
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# URL da API vista pelo NAVEGADOR (não pelo container)
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# Modo demonstração: mostra rota e nota do Score em cada resposta (desligado se ausente)
ARG VITE_SHOW_DEBUG=false
ENV VITE_SHOW_DEBUG=$VITE_SHOW_DEBUG
RUN npm run build

# Etapa 2 — nginx servindo os arquivos na porta 5173
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 5173
