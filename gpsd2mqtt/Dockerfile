ARG BUILD_FROM
FROM $BUILD_FROM

# Execute during the build of the image
ARG TEMPIO_VERSION BUILD_ARCH
#RUN \
#    curl -sSLf -o /usr/bin/tempio \
#    "https://github.com/home-assistant/tempio/releases/download/${TEMPIO_VERSION}/tempio_${BUILD_ARCH}"

RUN apk add --no-cache bash py3-pip py3-paho-mqtt py3-pyserial

# Add edge for gpsd ONLY, to get latest version
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main gpsd=3.26.1-r0 gpsd-clients=3.26.1-r0

RUN pip install --break-system-packages gpsdclient
# RUN pip install paho-mqtt gpsdclient

# Copy data for add-on
COPY run.sh /
COPY gpsd2mqtt.py /

RUN chmod a+x /run.sh /gpsd2mqtt.py

CMD [ "/run.sh" ]
