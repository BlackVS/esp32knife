#!/usr/bin/env python3

import sys, os
import esptool
import espefuse
# from espefuse import efuses_init_commands
import argparse
import time
import shutil
import hashlib
import binascii
import struct
import re
import esp32firmware as esp32
import esp32partgen as esp32part
import copy
from makeelf.elf import *
import esp32nvs

try:
    import serial.tools.list_ports as list_ports
except ImportError:
    printlog("The installed version (%s) of pyserial appears to be too old for esptool.py (Python interpreter %s). "
          "Check the README for installation instructions." % (sys.version, sys.executable))
    raise

from esp32exceptions import *
from esp32utils import *
import io
import json

BASEDIR_DIS = "parsed"
#BASEFILE = ""

FILE_EFUSES_TXT = "{}/efuses".format(BASEDIR_DIS)
FILE_FIRMWARE = "{}/firmware.bin".format(BASEDIR_DIS)
FILE_LOGNAME = "{}/knife.log".format(BASEDIR_DIS)
FILE_LOG = None
FILE_BOOTLOADER = "{}/bootloader.bin".format(BASEDIR_DIS)
FILE_PARTITIONS_CSV = "{}/partitions.csv".format(BASEDIR_DIS)
FILE_PARTITIONS_BIN = "{}/partitions.bin".format(BASEDIR_DIS)
FILE_PARTITIONS = "{}/part".format(BASEDIR_DIS)

NVS_BLOB_DATA_DIR = BASEDIR_DIS+"/nvs_blob_data"

FIRMWARE_CHIP = None
FIRMWARE_ESP  = None

FIRMWARE_PARTITIONS_TABLE_OFFSETS = [ 0x8000, 0x9000 ]
FIRMWARE_PARTITIONS_TABLE_SIZE   = 0xC00

DETECTED_FLASH_SIZES_STR = {    0x12: '256KB', 
                            0x13: '512KB', 
                            0x14: '1MB', 
                            0x15: '2MB', 
                            0x16: '4MB', 
                            0x17: '8MB', 
                            0x18: '16MB'
                        }

DETECTED_FLASH_SIZES_INT = {0x12: 256*1024, 
                            0x13: 512*1024, 
                            0x14: 1*1024*1024, 
                            0x15: 2*1024*1024, 
                            0x16: 4*1024*1024, 
                            0x17: 8*1024*1024, 
                            0x18: 16*1024*1024
                        }

DRAM0_DATA_START = None
DRAM0_DATA_END   = None


def printlog(*args, **kwargs):
    global FILE_LOG
    print(*args, **kwargs)
    if FILE_LOG:
        kwargs['file']=FILE_LOG
        print(*args, **kwargs)


def log(f, txt=""):
    printlog(txt)
    f.write( "{}\n".format(txt))

def arg_auto_int(x):
    return int(x, 0)


def print_mac(label, mac):
    printlog('%s: %s' % (label, ':'.join(map(lambda x: '%02x' % x, mac))))

def read_mac(esp):
    return esp.read_mac()


class ESPFLASHSIZEARG:
    flash_size = ""
    def __init__(self, flash_size="detect"):
        self.flash_size = flash_size


def esp_flash_size(esp):
    flash_id = esp.flash_id()
    size_id = flash_id >> 16
    return DETECTED_FLASH_SIZES_INT.get(size_id, None)
    # a =  ESPFLASHSIZEARG('detect')
    # esptool.detect_flash_size(esp, a)
    # printlog(a)

def get_seg_name(image, addr):
    return ",".join([seg_range[2] for seg_range in image.ROM_LOADER.MEMORY_MAP if seg_range[0] <= addr < seg_range[1]])

def get_memory_segments(image, addr):
    return set( [seg_range[2] for seg_range in image.ROM_LOADER.MEMORY_MAP if seg_range[0] <= addr < seg_range[1]] )

def if_addr_in_seg(image, addr, segname):
    for seg in image.ROM_LOADER.MEMORY_MAP:
        if seg[2]==segname and seg[0] <= addr < seg[1]:
            return True
    return False

def memory_segment(image, segname):
    for seg in image.ROM_LOADER.MEMORY_MAP:
        if seg[2]==segname:
            return seg
    return None

def parse_nvs_partition(partfilename):
    #cvs
    logfilename=partfilename+".cvs"
    printlog("      Parsing NVS partition: {} to {}".format(partfilename, logfilename))
    flog = open(logfilename, "wt")
    with open(partfilename, 'rb') as fh:
        std=sys.stdout
        if flog: 
            sys.stdout = flog
        #pages = esp32nvs.read_nvs_pages(fh,True)
        pages = esp32nvs.nvs2cvs(fh, NVS_BLOB_DATA_DIR)
        sys.stdout = std

    #text
    logfilename=partfilename+".txt"
    printlog("      Parsing NVS partition: {} to {}".format(partfilename, logfilename))
    flog = open(logfilename, "wt")
    with open(partfilename, 'rb') as fh:
        std=sys.stdout
        if flog: 
            sys.stdout = flog
        pages = esp32nvs.nvs2txt(fh)
        sys.stdout = std

    #json
    logfilename=partfilename+".json"
    printlog("      Parsing NVS partition: {} to {}".format(partfilename, logfilename))
    with open(partfilename, 'rb') as fh:
        sys.stdout = open(os.devnull, 'w') # block print()
        pages = esp32nvs.nvs2txt(fh)
        sys.stdout = sys.stdout = sys.__stdout__ # re-enable print()
        with open(logfilename, "wt") as f:
            f.writelines(json.dumps(pages, indent=4))
            

def flash_image_info(chip, data, filename):
    global DRAM0_DATA_START, DRAM0_DATA_END

    f_info=open("{}.info".format(filename),"wt+")
    f_map =open("{}.map".format(filename),"wt+")

    try:
        image = esptool.bin_image.LoadFirmwareImage(chip, data)
    except Exception as inst:
        printlog("Failed to parse : " + filename)
        printlog(inst)
        return False
        
    log(f_info, "Image version: {}".format( image.version ) )
    if image.entrypoint != 0:
        log(f_info, "Entry point: {:08x}".format(image.entrypoint))
    else:
        log(f_info, "Entry point not set")
    image_size = image.data_length + len(image.stored_digest)
    log(f_info, "real partition size: {}".format(image_size))
    log(f_info, "secure_pad: {}".format(image.secure_pad))
    log(f_info, "flash_mode: {}".format(image.flash_mode))
    log(f_info, "flash_size_freq: {}".format(image.flash_size_freq))
    f_map.write("0x{:x}\n".format(image.entrypoint))
    f_map.write("{}\n".format(len(image.segments)))
    f_map.write("{} {} {} \n".format(image.secure_pad,image.flash_mode,image.flash_size_freq))

    log(f_info, '%d segments' % len(image.segments))
    log(f_info)

    idx = 0
    for seg in image.segments:
        idx += 1
        log(f_info, "Segment {} : {} {}".format( idx, seg, get_seg_name(image, seg.addr)))
        if if_addr_in_seg(image, seg.addr, "DRAM"):
            if DRAM0_DATA_START==None or seg.addr<DRAM0_DATA_START:
                DRAM0_DATA_START = seg.addr
            dend = seg.addr + len(seg.data)
            if DRAM0_DATA_END==None or dend > DRAM0_DATA_END:
                DRAM0_DATA_END = dend
        if if_addr_in_seg(image, seg.addr, "DROM"):
            seg_app_data = esp32.ESP_APP_DESC_STRUCT(seg.data)
            printlog("  DROM, app data: {}".format(seg_app_data))
        #log(f_info, "  addr=0x{:x} file_offs=0x{:x} include_in_checksum={}\n".format(seg.addr, seg.file_offs, seg.include_in_checksum))
        fsegname="{}.seg{}".format(filename,idx)
        with open(fsegname, "wb+") as file:
            file.write(seg.data)
        f_map.write("{} {} 0x{:08x} 0x{:08x} {}\n".format(idx, fsegname, seg.addr, seg.file_offs, seg.include_in_checksum))

            
    calc_checksum = image.calculate_checksum()
    log(f_info, 'Checksum: %02x (%s)' % (image.checksum, 'valid' if image.checksum == calc_checksum else 'invalid - calculated %02x' % calc_checksum))
    try:
        digest_msg = 'Not appended'
        if image.append_digest:
            is_valid = image.stored_digest == image.calc_digest
            digest_msg = "%s (%s)" % (hexify(image.calc_digest).lower(),
                                      "valid" if is_valid else "invalid")
            printlog('Validation Hash: %s' % digest_msg)
    except AttributeError:
        pass  # ESP8266 image has no append_digest field

    f_map.close()
    f_info.close()
    return True


def flash_progress(progress, length, message=""):
    msg = '%d (%d %%) %s' % (progress, progress * 100.0 / length, message)
    padding = '\b' * len(msg)
    if progress == length:
        padding = '\n'
    sys.stdout.write(msg + padding)
    sys.stdout.flush()



def read_flash(esp, flash_address, flash_size, flash_progress=flash_progress):
    t = time.time()
    data = esp.read_flash(flash_address, flash_size, flash_progress)
    t = time.time() - t
    printlog('\rRead %d bytes at 0x%x in %.1f seconds (%.1f kbit/s)...' % (len(data), flash_address, t, len(data) / t * 8 / 1000))
    return data



class ESPEFUSEARGS:
    format = ""
    file = ""

    def __init__(self, filename="", format=""):
        self.file =  open(filename, "wt") if filename else sys.stdout
        self.format = format



def read_firmware_from_device(chip, port, baud, read_efuses=True):
    global FIRMWARE_CHIP, FIRMWARE_ESP

    initial_baud = min(esptool.ESPLoader.ESP_ROM_BAUD, baud)  # don't sync faster than the default baud rate

    ports = [port]
    if port == 'auto':
        ports = sorted(ports.device for ports in list_ports.comports())
    printlog("Try detect board at ports: {}".format(ports))

    chip_def = None
    efuse_class = None
    chip_class = None
    for p in ports:
        printlog("Try serial port %s" % p)
        try:
            if chip == 'auto':
                esp = esptool.ESPLoader.detect_chip(p, initial_baud, 'default_reset', False)
            else:
                # chip_class = esptool.CHIP_DEFS[chip]
                chip_def = espefuse.efuse_interface.SUPPORTED_CHIPS.get(chip, None)
                efuse_class = chip_def.efuse_lib  # efuse for  get_efuses
                chip_class = chip_def.chip_class  # for get_chip_description, get_chip_features, get_crystal_freq

                esp = chip_class(p, initial_baud, False)
                esp.connect()
            break
        #except (FatalError, OSError) as err:
            #printlog("%s failed to connect: %s" % (p, err))
        except Exception as inst:
            #printlog(type(inst))
            #printlog(inst.args)
            printlog(inst)
            esp = None

    if esp is None:
        raise FatalError("Could not connect to an Espressif device at %s serial port." % ports)

    FIRMWARE_CHIP = esp.CHIP_NAME

    printlog("Chip is %s" % (esp.get_chip_description()))
    printlog("Features: %s" % ", ".join(esp.get_chip_features()))
    printlog("Crystal is %dMHz" % esp.get_crystal_freq())

    mac=read_mac(esp)
    print_mac("MAC", mac)

    espstub = esp.run_stub()        

    if baud > initial_baud:
        try:
            espstub.change_baud(baud)
        except NotImplementedInROMError:
            printlog("WARNING: ROM doesn't support changing baud rate. Keeping initial baud rate %d" % initial_baud)

    flash_size = esp_flash_size(espstub)
    printlog('Auto-detected Flash size:', flash_size)

    if read_efuses:
        if esp.CHIP_NAME == 'ESP8266':
            efuses = esp.get_efuses()
            with open(FILE_EFUSES_TXT+".txt","wt") as f:
                f.write(bin(efuses))
        else:
            if not chip_def:
                printlog("WARNING: Efuse definitions for %s not available" % esp.CHIP_NAME)
                return None

            with espefuse.init_commands(esp=esp) as efuses_cmd:
                with open(FILE_EFUSES_TXT+".cvs", "wt") as f:
                    log(f, "EFUSES:")
                    for b in efuses_cmd.efuses.blocks:
                        log(f, "\nName={}\nid={} Alias={} Read_addr=0x{:04x} Write_addr=0x{:04x} len={} read_disable_bit={} write_disable_bit={} key_purpose_name={}".format(
                            b.name, b.id, b.alias, b.rd_addr, b.wr_addr, b.len, b.read_disable_bit, b.write_disable_bit, b.key_purpose_name
                        ))
                        log(f, "BITS  ={}".format(b.bitarray.hex))
                        log(f, "WRBITS={}".format(b.wr_bitarray.hex))

                # s = efuses.efuses.summary()
                # if s:
                with open(FILE_EFUSES_TXT+".summary.txt", "wt") as f:
                    efuses_cmd.summary(format="summary", file=f)
                with open(FILE_EFUSES_TXT+".summary.json", "wt") as f:
                    efuses_cmd.summary(format="json", file=f)


    flash = read_flash(espstub, 0, flash_size)
        
    FIRMWARE_ESP = esp
    return flash

# section header flags
# Key to Flags:
#   W (write), A (alloc), X (execute), M (merge), S (strings), I (info),
#   L (link order), O (extra OS processing required), G (group), T (TLS),
#   C (compressed), x (unknown), o (OS specific), E (exclude),
#   p (processor specific)

def calcShFlg(flags):
    mask = 0
    if 'W' in flags:
        mask |= SHF.SHF_WRITE
    if 'A' in flags:
        mask |= SHF.SHF_ALLOC
    if 'X' in flags:
        mask |= SHF.SHF_EXECINSTR
    if 'M' in flags:
        mask |= SHF.SHF_MERGE
    if 'S' in flags:
        mask |= SHF.SHF_STRINGS
    if 'I' in flags:
        mask |= SHF.SHF_INFO_LINK
    if 'L' in flags:
        mask |= SHF.SHF_LINK_ORDER
    if 'O' in flags:
        mask |= SHF.SHF_OS_NONCONFORMING
    if 'G' in flags:
        mask |= SHF.SHF_GROUP
    if 'T' in flags:
        mask |= SHF.SHF_TLS
    if 'o' in flags:
        mask |= SHF.SHF_MASKOS
    if 'p' in flags:
        mask |= SHF.SHF_MASKPROC
    # if 'C' in flags:
    #     mask |= SHF.SHF_EXECINSTR
    # if 'x' in flags:
    #     mask |= SHF.SHF_EXECINSTR
    # if 'E' in flags:
    #     mask |= SHF.SHF_EXECINSTR
            
    return mask


def add_elf_symbols(elf,filename):
    #pass
    fh = open(filename, "rt")
    if not fh: 
        return

    elf.append_special_section('.symtab')

    lines = fh.readlines()

    bind_map = {"LOCAL" : STB.STB_LOCAL, "GLOBAL" : STB.STB_GLOBAL}
    type_map = {"NOTYPE": STT.STT_NOTYPE, "OBJECT" : STT.STT_OBJECT, "FUNC" : STT.STT_FUNC, "FILE" : STT.STT_FILE}

    for line in lines:
        line = line.split()
        sym_binding = line[4]
        sym_type = line[3]
        sym_size = int(line[2])
        sym_val = int(line[1], 16)
        sym_name = line[7]
                                  
        sym_section = SHN.SHN_ABS
        #try locate section by addresses
        if sym_type in ['NOTYPE','OBJECT','FUNC']:
            for sindex, shdr in enumerate(elf.Elf.Shdr_table):
                if shdr.sh_type != SHT.SHT_PROGBITS:
                    continue
                if sym_val>=shdr.sh_addr and sym_val<shdr.sh_addr+shdr.sh_size:
                    sym_section=sindex
                    break
        elf.append_symbol(sym_name, sym_section, sym_val, sym_size, sym_binding=bind_map[sym_binding], sym_type=type_map[sym_type])


def convert_sec2seg_flg(sec_flags):
    res = "r"
    for s in sec_flags:
        if s in "WX":
            res+=s
    return res.lower()
    
def combine_seg_flags(f1, f2):
    return "".join( set(f1)|set(f2) )
    
def calcPhFlg(flags):
    p_flags = 0
    if 'r' in flags:
        p_flags |= PF.PF_R
    if 'w' in flags:
        p_flags |= PF.PF_W
    if 'x' in flags:
        p_flags |= PF.PF_X
    return p_flags

def export_bin2elf(chip, data, filename, board_ext_symbols, board_ext_segments):
    global DRAM0_DATA_START, DRAM0_DATA_END

    image = esptool.bin_image.LoadFirmwareImage(chip, data)
    image_name = filename+".elf"

    elf = ELF(e_machine=EM.EM_XTENSA, e_data=ELFDATA.ELFDATA2LSB)
    elf.Elf.Ehdr.e_entry = image.entrypoint

    # maps segment names to ELF sections

    # map to hold pre-defined ELF section header attributes
    # http://man7.org/linux/man-pages/man5/elf.5.html

    # Section Headers: APPLICATION
    # [Nr] Name              Type            Addr     Off    Size   ES Flg Lk Inf Al
    # [ 0]                   NULL            00000000 000000 000000 00      0   0  0
    # [ 1] .rtc.text         PROGBITS        400c0000 0da579 000000 00   W  0   0  1
    # [ 2] .rtc.dummy        PROGBITS        3ff80000 0da579 000000 00   W  0   0  1
    # [ 3] .rtc.force_fast   PROGBITS        3ff80000 0da579 000000 00   W  0   0  1
    # [ 4] .rtc_noinit       PROGBITS        50000000 0da579 000000 00   W  0   0  1
    # [ 5] .rtc.force_slow   PROGBITS        50000000 0da579 000000 00   W  0   0  1
    # [ 6] .iram0.vectors    PROGBITS        40080000 02b000 000400 00  AX  0   0  4
    # [ 7] .iram0.text       PROGBITS        40080400 02b400 01502c 00 WAX  0   0  4
    # [ 8] .dram0.data       PROGBITS        3ffb0000 027000 003250 00  WA  0   0 16
    # [ 9] .noinit           PROGBITS        3ffb3250 0da579 000000 00   W  0   0  1
    # [10] .dram0.bss        NOBITS          3ffb3250 02a250 007088 00  WA  0   0  8
    # [11] .flash.rodata     PROGBITS        3f400020 001020 025fd4 00  WA  0   0 16
    # [12] .flash.text       PROGBITS        400d0018 041018 099561 00  AX  0   0  4
    # [13] .debug_frame      PROGBITS        00000000 0da57c 01f734 00      0   0  4
    # [14] .debug_info       PROGBITS        00000000 0f9cb0 4c8452 00      0   0  1
    # [15] .debug_abbrev     PROGBITS        00000000 5c2102 0675d6 00      0   0  1
    # [16] .debug_loc        PROGBITS        00000000 6296d8 0fdb69 00      0   0  1
    # [17] .debug_aranges    PROGBITS        00000000 727248 00c038 00      0   0  8
    # [18] .debug_ranges     PROGBITS        00000000 733280 01ac48 00      0   0  8
    # [19] .debug_line       PROGBITS        00000000 74dec8 214042 00      0   0  1
    # [20] .debug_str        PROGBITS        00000000 961f0a 07490b 01  MS  0   0  1
    # [21] .comment          PROGBITS        00000000 9d6815 0000d9 01  MS  0   0  1
    # [22] .xtensa.info      NOTE            00000000 9d68ee 000038 00      0   0  1
    # ...

    # Section Headers: BOOTLOADER
    #   [Nr] Name              Type            Addr     Off    Size   ES Flg Lk Inf Al
    #   [ 0]                   NULL            00000000 000000 000000 00      0   0  0
    #   [ 1] .iram_loader.text PROGBITS        40078000 003000 0033b2 00  AX  0   0  4
    #   [ 2] .iram.text        PROGBITS        40080400 006400 000ec0 00  AX  0   0  4
    #   [ 3] .dram0.bss        NOBITS          3fff0000 001000 000018 00  WA  0   0  4
    #   [ 4] .dram0.data       PROGBITS        3fff0018 001018 000004 00  WA  0   0  4
    #   [ 5] .dram0.rodata     PROGBITS        3fff001c 00101c 001a00 00   A  0   0  4
    #   [ 6] .debug_frame      PROGBITS        00000000 0072c0 000ef8 00      0   0  4
    #   [ 7] .debug_info       PROGBITS        00000000 0081b8 0554ae 00      0   0  1
    #   [ 8] .debug_abbrev     PROGBITS        00000000 05d666 00525e 00      0   0  1
    #   [ 9] .debug_loc        PROGBITS        00000000 0628c4 007d2f 00      0   0  1
    #   [10] .debug_aranges    PROGBITS        00000000 06a5f3 000698 00      0   0  1
    #   [11] .debug_ranges     PROGBITS        00000000 06ac8b 000fe0 00      0   0  1
    #   [12] .debug_line       PROGBITS        00000000 06bc6b 011bb8 00      0   0  1
    #   [13] .debug_str        PROGBITS        00000000 07d823 009998 01  MS  0   0  1
    #   [14] .comment          PROGBITS        00000000 0871bb 000025 01  MS  0   0  1
    #   [15] .xtensa.info      NOTE            00000000 0871e0 000038 00      0   0  1
    #   [16] .symtab           SYMTAB          00000000 087218 001660 10     17  72  4
    #   [17] .strtab           STRTAB          00000000 088878 0014ec 00      0   0  1
    #   [18] .shstrtab         STRTAB          00000000 089d64 0000d9 00      0   0  1

    # ES    : sh_entsize
    # Flg   : sh_flags
    # Lk    : sh_link
    # Inf   : sh_info
    # Al    : sh_addralign
    #                           ES    Flg   Lk Inf Al
    SECTIONNS_ELF_ATTRS = {
            '.iram0.vectors'    : (0x00, 'AX' ,  0, 0, 4),
            '.iram0.text'       : (0x00, 'WAX',  0, 0, 4), 
            '.iram.text'        : (0x00, 'WAX',  0, 0, 4), 
            '.iram_loader.text' : (0x00, 'AX' ,  0, 0, 4),

            '.irom0.text'       : (0x00, 'WAX',  0, 0, 4), 
            '.irom1.text'       : (0x00, 'WAX',  0, 0, 4), 

            '.dram0.data'   : (0x00, 'WA' ,  0, 0, 16),
            '.dram0.bss'    : (0x00, 'WA' ,  0, 0, 8),

            '.flash.rodata' : (0x00, 'WA' ,  0, 0, 16),
            '.flash.text'   : (0x00, 'AX' ,  0, 0, 4),

            '.rtc.text'   : (0x00, 'AX' ,  0, 0, 4),
    }

    iram_vectors_found = False

    IRAM_SEG = memory_segment(image, "IRAM")
    
    elf_sections = []

    #segment sorted by addresses i.e. if some segment was split we can easily join it back
    for seg in sorted(image.segments, key=lambda s:s.addr):

        # get memroy segments at specified address
        mem_segments = get_memory_segments(image, seg.addr)

        if not mem_segments:
            printlog("Unknown segment at 0x{:08x}!!!!".format(seg.addr))
            return

        elf_segment = ""
        ## for application
        ## bin 2 elf mapping
        # DROM                   : .flash.rodata
        # BYTE_ACCESSIBLE + DRAM : .dram0.data , after it usually is .dram0.bss but we don't know it size - can create maximum?
        # IRAM                   : .iram0.text or .iram0.vectors , vectors 400 size and first, before text
        # IROM                   : .flash.text

        if 'DROM' in mem_segments:
            elf_segment = ".flash.rodata"
        elif 'DRAM' in mem_segments:
            elf_segment = ".dram0.data"
        elif 'IROM' in mem_segments:
            elf_segment = ".flash.text"
        elif 'IRAM' in mem_segments:
            if IRAM_SEG[0]==seg.addr:
                elf_segment = ".iram0.vectors"
                iram_vectors_found = True
            else:
                elf_segment = ".iram0.text" # ".iram.text" for bootloader!
        elif 'CACHE_APP' in mem_segments:
            elf_segment = ".iram_loader.text"
        elif 'RTC_IRAM' in mem_segments:
            elf_segment = ".rtc.text"
        else:
            printlog("Can't map {} to anything!!!".format(mem_segments))
            return
        printlog("Segment at addr=0x{:08x} => {} => {}".format(seg.addr, mem_segments, elf_segment))

        fjoin = len(elf_sections)>0 and elf_sections[-1][-1] == elf_segment and elf_sections[-1][0]+elf_sections[-1][1]==seg.addr
        if fjoin:
            printlog("Join segments 0x{:08x} and 0x{:08x}".format(elf_sections[-1][0], seg.addr))
            elf_sections[-1][1]+=len(seg.data)
            elf_sections[-1][2]+=seg.data
        else: 
            elf_sections.append( [seg.addr, len(seg.data), copy.copy(seg.data), elf_segment] )


    if board_ext_segments:
        for sname, saddr, slen, sfile in board_ext_segments:
            saddr = int(saddr, base=16)
            slen = int(slen, base=16)
            sdata = None
            with open(sfile,"rb") as fdata:
                sdata=fdata.read()
            if not sdata:
                printlog("Failed to read: " + sfile)
                return None
            if len(sdata)!=slen:
                printlog("File size and size in config mismath: 0x{:x} != 0x{:8} ".format(len(sdata), slen))
                return None

            if DRAM0_DATA_START!=None and DRAM0_DATA_START>=saddr and DRAM0_DATA_START <saddr+slen:
                slen = (DRAM0_DATA_START - saddr) & ~0xffff #paragraph align? Or page?
            elf_sections.append( [saddr, slen, sdata[:slen], sname] )


    for sec_addr, sec_len, sec_data, sec_name in elf_sections:
        sh_entsize, sh_flags, sh_link, sh_info, sh_addralign = SECTIONNS_ELF_ATTRS.get(sec_name, (None,None,None,None,None))
        if sh_entsize==None:
            printlog("Can't get attributes for {} section!!!".format(sec_name))
            #elf.append_section(name, data, addr)        
            return
        flg = calcShFlg(sh_flags)
        # adding progbits (all from binary app partition are progbits)
        # ES    : sh_entsize
        # Flg   : sh_flags
        # Lk    : sh_link
        # Inf   : sh_info
        # Al    : sh_addralign        
        elf._append_section(sec_name, sec_data, sec_addr, SHT.SHT_PROGBITS, flg, sh_link, sh_info, sh_addralign, sh_entsize )


    elf.append_special_section('.strtab')


    if board_ext_symbols:
        for fname in board_ext_symbols:
            add_elf_symbols(elf, fname)


    # there is an initial program header that we don't want...
    elf.Elf.Phdr_table.pop()

    bytes(elf) # kind of a hack, but __bytes__() calculates offsets in elf object

    printlog("\nAdding program headers")
    #  Section to Segment mapping:
    #   Segment Sections... application
    #    00     .flash.rodata 
    #    01     .dram0.data .dram0.bss 
    #    02     .iram0.vectors .iram0.text 
    #    03     .flash.text 

    #   Segment Sections... bootloader
    #    00     .dram0.bss .dram0.data .dram0.rodata 
    #    01     .iram_loader.text 
    #    02     .iram.text 

    ## i.e dram0 and iram0 combined in one prg.segment

    ## [ addr, size, flags, sec_name ]
    pg_segments = []
    for sec_addr, sec_len, sec_data, sec_name in elf_sections:
        sec_flags = convert_sec2seg_flg( SECTIONNS_ELF_ATTRS[sec_name][1] ) 
        if  ( sec_name.startswith(".dram0") and len(pg_segments)>0 and pg_segments[-1][-1].startswith(".dram0") and pg_segments[-1][0] + pg_segments[-1][1] == sec_addr) or \
            ( sec_name.startswith(".iram0") and len(pg_segments)>0 and pg_segments[-1][-1].startswith(".iram0") and pg_segments[-1][0] + pg_segments[-1][1] == sec_addr):
                printlog("combine section {} and {} in one program segment".format( pg_segments[-1][-1], sec_name))
                pg_segments[-1][1]+=sec_len
                pg_segments[-1][2] = combine_seg_flags( pg_segments[-1][2], sec_flags )
        else:
            pg_segments.append( [sec_addr, sec_len, sec_flags, sec_name ] )

    for i,p in enumerate(pg_segments):
        printlog("prg_seg {} : {:08x} {:08x} {} {}".format( i, p[0], p[1], p[2], p[3]))

    size_of_phdrs = len(Elf32_Phdr()) * len(pg_segments) # to pre-calculate program header offsets


    printlog("Program Headers:")
    printlog("Type  Offset    VirtAddr  PhysAddr  FileSize  MemSize  Flg Align")

    for pg_addr, pg_size, pg_flags, pg_first_section in pg_segments:
        p_flags = calcPhFlg(pg_flags)

        align = 0x1000
        p_type = PT.PT_LOAD

        shstrtab_hdr, shstrtab = elf.get_section_by_name(pg_first_section)
        offset = shstrtab_hdr.sh_offset + size_of_phdrs # account for new offset

        # build program header
        Phdr = Elf32_Phdr(PT.PT_LOAD, p_offset=offset, p_vaddr=pg_addr,
                p_paddr=pg_addr, p_filesz=pg_size, p_memsz=pg_size,
                p_flags=p_flags, p_align=align, little=elf.little)

        #printlog(pg_first_section + ": " + str(Phdr))
        printlog("{:2}    {:08x}  {:08x}  {:08x}  {:08x}  {:08x}  {}  {:04x}".format( Phdr.p_type, Phdr.p_offset, Phdr.p_vaddr, Phdr.p_paddr, Phdr.p_filesz, Phdr.p_memsz, Phdr.p_flags, Phdr.p_align))
        elf.Elf.Phdr_table.append(Phdr)

    # write out elf file
    printlog("\nWriting ELF to " + image_name + "...")
    with open(image_name, "wb") as fd:
        fd.write(bytes(elf))

def main():
    global FIRMWARE_CHIP, FIRMWARE_ESP, FILE_LOG

    #### globally accessed bins and pased data
    FIRMWARE_FULL_BIN = None
    FIRMWARE_PARTITIONS_BIN = None
    FIRMWARE_PARTITIONS_TABLE = None
    FIRMWARE_PARTITIONS_FNAMES = []
 
    BOOTLOADER_IMAGE     = None #parsed
    BOOTLOADER_IMAGE_BIN = None #binary

    BOARD_EXT_SYMBOLS = []
    BOARD_EXT_SEGMENTS = []

    try:
        printlog("Prepare output directories:")


        if os.path.exists(BASEDIR_DIS):
            printlog("- removing old directory: {}".format(BASEDIR_DIS))
            shutil.rmtree(BASEDIR_DIS)

        if not os.path.exists(BASEDIR_DIS):
            printlog("- creating directory: {}".format(BASEDIR_DIS))
            os.makedirs(BASEDIR_DIS)
            FILE_LOG = open(FILE_LOGNAME, "wt")


        parser = argparse.ArgumentParser(add_help=True, description='ESP32 analyzer')

        parser.add_argument('--chip', '-c',
                            help='Target chip type',
                            choices=['auto', 'esp8266', 'esp32', 'esp32s2'],
                            default=os.environ.get('ESPTOOL_CHIP', 'auto'))
        parser.add_argument('--board', '-m',
                            help='Target board',
                            default=None)

        subparsers = parser.add_subparsers(
            dest='operation',
            help='Run esp32parse {command} -h for additional help')

            
        parser_load_from_file = subparsers.add_parser(
            'load_from_file',
            help='Load an image from binary file')
        parser_load_from_file.add_argument('filename', help='Firmware full image')

        parser_load_from_device = subparsers.add_parser(
            'load_from_device',
            help='Load an image directly from device')
        parser_load_from_device.add_argument(
            '--port', '-p',
            help='Serial port device. If "auto" - try all serial ports',
            #default=os.environ.get('ESPTOOL_PORT', esptool.ESPLoader.DEFAULT_PORT)
            default='auto'
            )
        parser_load_from_device.add_argument(
            '--baud', '-b',
            help='Serial port baud rate used when flashing/reading',
            type=arg_auto_int,
            default=os.environ.get('ESPTOOL_BAUD', esptool.ESPLoader.ESP_ROM_BAUD))
        parser_load_from_device.add_argument(
            '--read_efuses', '-e',
            help="Read EFUSEs from device",
            action='store_true')

        if len(sys.argv) == 1:
            printlog("Wrong arguments!!!")
            parser.print_help()
            exit(0)

        args = parser.parse_args()

        esp = None
        if args.board!=None:
            pathboard = os.path.join("boards",args.board)
            printlog("Try load additional board info from: {}".format(pathboard))
            if not os.path.exists(pathboard):
                printlog("Path not exists: " + pathboard)
                return 0
            pathconfig = os.path.join(pathboard, "config.txt")
            printlog("Loading board config from: ")
            if not os.path.exists(pathconfig):
                printlog("Path not exists: " + pathconfig)
                return 0
            with open(pathconfig, "rt") as fc:
                for line in fc:
                    ctype, cvalue = line.split(":")
                    ctype=ctype.strip()
                    cvalue=cvalue.strip()
                    if ctype=="symbols":
                        csymbols = [ os.path.join(pathboard, c) for c in cvalue.split() ]
                        BOARD_EXT_SYMBOLS+=csymbols
                    if ctype=="segment":
                        csegment = list(cvalue.split())
                        csegment[-1]=os.path.join(pathboard, csegment[-1])
                        BOARD_EXT_SEGMENTS.append(tuple(csegment))


        if args.operation=='load_from_device':
            FIRMWARE_FULL_BIN = read_firmware_from_device(args.chip, args.port, args.baud, args.read_efuses)  
            esp = FIRMWARE_ESP
            printlog("Writing full firmware to: {}".format(FILE_FIRMWARE))
            with open(FILE_FIRMWARE,"wb") as f:
                f.write(FIRMWARE_FULL_BIN)

        elif args.operation=='load_from_file':
            if args.chip=='auto':
                printlog('Please specify chip!')
                return
            
            chip_def = espefuse.efuse_interface.SUPPORTED_CHIPS.get(args.chip, None)
            efuse_class = chip_def.efuse_lib  # efuse for  get_efuses
            chip_class = chip_def.chip_class  # for get_chip_description, get_chip_features, get_crystal_freq
            if not chip_class:
                printlog("Unsupported chip: {}".format(args.chip))
                return

            FIRMWARE_CHIP =  chip_class.CHIP_NAME

            printlog("Reading firmware from: {}".format(args.filename))
            with open(args.filename,"rb") as f:
                FIRMWARE_FULL_BIN = f.read() 
        else:
            printlog("Unknown operation: {}".format(args.operation))
            return

        if not FIRMWARE_FULL_BIN:
            printlog("Failed to read firmware!")
            return

        flash = FIRMWARE_FULL_BIN
        chip  = FIRMWARE_CHIP

        fbootloader = io.BytesIO( flash[ chip_class.BOOTLOADER_FLASH_OFFSET:] ) 
        fbootloader_bytes: bytes = fbootloader.getvalue()
        BOOTLOADER_IMAGE = esptool.bin_image.LoadFirmwareImage(chip, fbootloader_bytes )
        image_size = BOOTLOADER_IMAGE.data_length + len(BOOTLOADER_IMAGE.stored_digest)

        BOOTLOADER_IMAGE_BIN = flash[chip_class.BOOTLOADER_FLASH_OFFSET:chip_class.BOOTLOADER_FLASH_OFFSET+image_size]
        printlog("Writing bootloader to: {}".format(FILE_BOOTLOADER))
        with open(FILE_BOOTLOADER,"wb") as f:
            f.write(flash[0x1000:0x1000+image_size])
        printlog("Bootloader image info:")
        printlog("=================================================================================")
        fparsed=flash_image_info(chip, BOOTLOADER_IMAGE_BIN, FILE_BOOTLOADER)
        if fparsed:
            export_bin2elf( chip, BOOTLOADER_IMAGE_BIN, FILE_BOOTLOADER, None, None )
        printlog("=================================================================================\n")


        FIRMWARE_PARTITIONS_TABLE_OFFSET = None
        for part_offset in FIRMWARE_PARTITIONS_TABLE_OFFSETS:
            if flash[part_offset:part_offset+2] != esp32part.PartitionDefinition.MAGIC_BYTES:
                printlog("No partition table found at: {:x}".format(part_offset))
                continue
            printlog("Partition table found at: {:x}".format(part_offset))
            FIRMWARE_PARTITIONS_TABLE_OFFSET = part_offset
            break
        if FIRMWARE_PARTITIONS_TABLE_OFFSET==None:
            printlog("Failed to find partitions table, exiting")
            exit(1)

        FIRMWARE_PARTITIONS_BIN = flash[FIRMWARE_PARTITIONS_TABLE_OFFSET:FIRMWARE_PARTITIONS_TABLE_OFFSET+FIRMWARE_PARTITIONS_TABLE_SIZE]
        FIRMWARE_PARTITIONS_TABLE = esp32part.PartitionTable.from_binary(FIRMWARE_PARTITIONS_BIN)
        printlog("Verifying partitions table...")
        FIRMWARE_PARTITIONS_TABLE.verify()
        output = FIRMWARE_PARTITIONS_TABLE.to_csv()

        printlog("Writing partitions table to: {}".format(FILE_PARTITIONS_CSV))
        with open(FILE_PARTITIONS_CSV, 'wt') as f:
            f.write(output)

        printlog("Writing partitions table to: {}".format(FILE_PARTITIONS_BIN))
        with open(FILE_PARTITIONS_BIN, 'wb') as f:
            f.write(FIRMWARE_PARTITIONS_BIN)

        FIRMWARE_PARTITIONS_FNAMES = []
        printlog("PARTITIONS:")
        for i,p in enumerate(FIRMWARE_PARTITIONS_TABLE):
            fname = "{}.{}.{}".format(FILE_PARTITIONS, i, p.name)
            printlog("{:4} {} {}".format(i,p,fname))
            FIRMWARE_PARTITIONS_FNAMES.append(fname)
            with open(fname, "wb") as f:
                f.write( FIRMWARE_FULL_BIN[ p.offset: p.offset+p.size] )
            if p.type == esp32part.DATA_TYPE and p.subtype == esp32part.SUBTYPES[esp32part.DATA_TYPE]['nvs']:
                parse_nvs_partition(fname)


        printlog("\nAPP PARTITIONS INFO:")
        printlog("=================================================================================")
        for i,p in enumerate(FIRMWARE_PARTITIONS_TABLE):
            if p.type != esp32part.APP_TYPE:
                continue
            printlog("Partition {}".format(p))
            printlog("-------------------------------------------------------------------")
            fparsed=flash_image_info( chip, FIRMWARE_FULL_BIN[ p.offset: p.offset+p.size], FIRMWARE_PARTITIONS_FNAMES[i] )
            if fparsed:
                export_bin2elf( chip, FIRMWARE_FULL_BIN[ p.offset: p.offset+p.size], FIRMWARE_PARTITIONS_FNAMES[i], BOARD_EXT_SYMBOLS, BOARD_EXT_SEGMENTS )
        printlog("=================================================================================\n")

    except Exception as inst:
        printlog(type(inst))
        printlog(inst.args)
        printlog(inst)
    finally:
        if FILE_LOG:
            FILE_LOG.close()





def _main():
    try:
        main()
    except FatalError as e:
        printlog('\nA fatal error occurred: %s' % e)
        sys.exit(2)


if __name__ == '__main__':
    _main()

# [ ".iram0.text", ".iram0.vectors", ".dram0.data", ".flash.rodata", ".flash.text" ]
#      IRAM               IRAM             DRAM            DROM            IROM
#                                       BYTE_ACCESSIBLE            

