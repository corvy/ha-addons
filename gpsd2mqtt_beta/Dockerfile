ARG BUILD_FROM
FROM $BUILD_FROM

# py3-paho-mqtt is constrained to 1.x on purpose: gpsd2mqtt.py uses the v1
# callback signatures, and paho-mqtt 2.x makes a bare mqtt.Client() raise
# ValueError (it requires an explicit CallbackAPIVersion). Alpine still ships
# 1.6.x, so this constraint is a no-op today and a guard for when it bumps.
RUN apk add --no-cache bash py3-pip "py3-paho-mqtt<2" py3-pyserial

# gpsd comes from the edge repository because Alpine stable lags behind.
# 3.27.3 picks up the 3.27.1 security fixes (CVE-2025-67268 heap out-of-bounds
# write in NMEA2000 parsing, CVE-2025-67269 integer underflow in NovAtel packet
# handling).
#
# NOTE: edge is a rolling repository, so this exact pin has a shelf life -- once
# edge moves past 3.27.3-r1 the version disappears and this line fails at build
# time with "unable to select packages". That build failure is the signal to
# come back and bump the pin. Check the current version at:
# https://pkgs.alpinelinux.org/packages?name=gpsd&branch=edge&repo=main
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main \
    gpsd=3.27.3-r1 gpsd-clients=3.27.3-r1

# Pinned so image builds stay reproducible.
RUN pip install --break-system-packages gpsdclient==1.3.2

# Copy data for add-on
COPY run.sh /
COPY gpsd2mqtt.py /

RUN chmod a+x /run.sh /gpsd2mqtt.py

CMD [ "/run.sh" ]
