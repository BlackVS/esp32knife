#!/bin/bash

PORT=/dev/ttyUSB0
CHIP=esp32
BAUD=2000000

#esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40000000 0x60000 flash_mem_rom0.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40000000 0x70000 flash_mem_rom0_ext.bin
#esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FF90000 0x10000 flash_mem_rom1.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FF90000 0x70000 flash_mem_rom1_ext.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40070000 0x10000 flash_mem_sram0.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x40080000 0x20000 flash_mem_sram0mmu.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FFE0000 0x20000 flash_mem_sram1_1.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x400A0000 0x20000 flash_mem_sram1_2.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FFAE000 0x12000 flash_mem_sram2.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FFC0000 0x20000 flash_mem_sram2_mmu.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x3FF80000 0x2000 flash_mem_rtcfast_1.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x400C0000 0x2000 flash_mem_rtcfast_2.bin
esptool.py --chip $CHIP --port $PORT --baud $BAUD dump_mem 0x50000000 0x2000 flash_mem_rtcslow.bin
