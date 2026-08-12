FROM node:20-alpine

WORKDIR /app

# 同 backend/Dockerfile：默认走国内 npm 镜像。前端依赖有 1100+ 个包，
# 官方 registry 在国内动辄十几分钟甚至中途失败，这一步是整个构建里最脆弱的环节。
# 想用官方源：docker compose build --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com

COPY package.json .npmrc ./
# --fetch-retries：网络抖动时自动重试，而不是直接把整个构建判死
RUN npm config set registry "$NPM_REGISTRY" && \
    npm install --fetch-retries=5 --fetch-retry-maxtimeout=120000

COPY . .

CMD ["npm", "run", "dev:h5"]
