ARG BUILD_FROM
FROM $BUILD_FROM

ARG TEMPIO_VERSION BUILD_ARCH

RUN apk add bash
RUN npm install -g --unsafe-perm signalk-server

CMD [ "signalk-server" ]
