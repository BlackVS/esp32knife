#!/bin/bash
if [[ $# -eq 0 ]] ; then
    echo 'please specify firmware file'
    exit 1
fi
esptool.py -p /dev/ttyUSB0 -b 2000000 read_flash 0x0 0x400000 $1