FROM node:23

WORKDIR /app

COPY simulator/*.json /app
RUN npm install
RUN npm install --save-dev @types/express @types/node pm2

COPY simulator/*.ts /app
RUN npx tsc

CMD ["npx", "pm2-runtime", "src.js"]
