FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install -g npm@11 --no-audit --no-fund && npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
