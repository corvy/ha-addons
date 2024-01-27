ARG BUILD_FROM
FROM $BUILD_FROM

# Execute during the build of the image
ARG TEMPIO_VERSION BUILD_ARCH
#RUN \
#    curl -sSLf -o /usr/bin/tempio \
#    "https://github.com/home-assistant/tempio/releases/download/${TEMPIO_VERSION}/tempio_${BUILD_ARCH}"

RUN apk add --no-cache gpsd gpsd-clients bash py3-pip gpsd-clients py3-gpsd py3-paho-mqtt py3-pyserial
# RUN pip install paho-mqtt gpsdclient

# Copy data for add-on
COPY run.sh /
COPY gpsd2mqtt.py /

RUN chmod a+x /run.sh /gpsd2mqtt.py

CMD [ "/run.sh" ]
