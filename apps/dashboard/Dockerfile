FROM node:20-alpine

WORKDIR /app
ARG NEXT_PUBLIC_MIXPOST_URL=
ENV NEXT_PUBLIC_MIXPOST_URL=${NEXT_PUBLIC_MIXPOST_URL}
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
