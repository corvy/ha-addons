ARG BUILD_FROM
FROM $BUILD_FROM

# Python is unpinned and follows the Alpine base, so nothing may hardcode a
# python minor version. run.sh logs the version at startup.
#
# paho-mqtt is held below 2.x: gpsd2mqtt.py uses the v1 callback signatures, and
# 2.x requires an explicit CallbackAPIVersion.
RUN apk add --no-cache bash py3-pip "py3-paho-mqtt<2" py3-pyserial

# gpsd comes from edge because stable is still on 3.26.1. The floor is 3.27.1,
# which carries the CVE-2025-67268 and CVE-2025-67269 fixes.
#
# A minimum rather than an exact version: edge is rolling, so an exact pin
# disappears and breaks the build at an arbitrary time. Revisit once Alpine
# stable reaches 3.27.1 and this override can be dropped entirely.
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main \
    "gpsd>=3.27.1" "gpsd-clients>=3.27.1"

# Pinned so image builds stay reproducible.
RUN pip install --break-system-packages gpsdclient==1.3.2

# Copy data for add-on
COPY run.sh /
COPY gpsd2mqtt.py /

RUN chmod a+x /run.sh /gpsd2mqtt.py

CMD [ "/run.sh" ]
