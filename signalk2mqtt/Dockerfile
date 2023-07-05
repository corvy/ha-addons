ARG BUILD_FROM
FROM $BUILD_FROM

ARG TEMPIO_VERSION BUILD_ARCH

RUN apk add bash npm avahi avahi-tools avahi-dev nginx
RUN npm install -g --unsafe-perm signalk-server

COPY run.sh /
COPY nginx_signalk.conf /etc/nginx/http.d/
RUN rm -f /etc/nginx/http.d/default.conf
RUN chmod +x /run.sh

CMD [ "/run.sh" ]

