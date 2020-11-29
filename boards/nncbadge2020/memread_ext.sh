#!/bin/bash

PORT=/dev/ttyUSB0
CHIP=esp32
BAUD=2000000

esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3fff0030 4 flash_mem_ext_0.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3fff0034 736 flash_mem_ext_1.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40078000 19444 flash_mem_ext_2.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40080400 3644 flash_mem_ext_3.bin
