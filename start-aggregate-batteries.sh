#!/bin/bash

. /opt/victronenergy/serial-starter/run-service.sh

app="python3 /opt/victronenergy/dbus-aggregate-batteries/aggregatebatteries.py"
start 
