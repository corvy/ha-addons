#!/bin/bash
echo Merging gpsd2mqtt_beta to gpsd2mqtt
rsync  -av --exclude-from=./exclude_list.txt ./ ../gpsd2mqtt/
