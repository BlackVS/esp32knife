#!/usr/bin/env python3
import sys, os
import esptool
import io
import struct
import copy
import hashlib
import zlib, base64
import esp32utils
from esp32exceptions import *


# typedef struct {
#     uint32_t magic_word;        0   /*!< Magic word ESP_APP_DESC_MAGIC_WORD */
#     uint32_t secure_version;    4   /*!< Secure version */
#     uint32_t reserv1[2];        8   /*!< reserv1 */
#     char version[32];           16  /*!< Application version */
#     char project_name[32];      48  /*!< Project name */
#     char time[16];              80  /*!< Compile time */
#     char date[16];              96  /*!< Compile date*/
#     char idf_ver[32];           112 /*!< Version IDF */
#     uint8_t app_elf_sha256[32]; 144 /*!< sha256 of elf file */
#     uint32_t reserv2[20];       176 /*!< reserv2 */
# } esp_app_desc_t;               = len(196)

ESP_APP_DESC_MAGIC_WORD = 0xABCD5432
ESP_APP_DESC_STRUCT_FMT = '<IIQ32s32s16s16s32s32s20s'
ESP_APP_DESC_STRUCT_SIZE = 196

class ESP_APP_DESC_STRUCT:
    magic_word = None
    secure_version = None
    reserv1 = None
    version = None
    project_name = None
    time = None
    date = None
    idf_ver = None
    app_elf_sha256 = None
    reserv2 = None

    def __init__(self, buffer=None):
        if buffer!=None:
            self.unpack(buffer)

    def unpack(self, buffer):
        m = struct.unpack('<I', buffer[:4]) 
        if  m[0] != ESP_APP_DESC_MAGIC_WORD:
            print("Failed unpack ESP_APP_DESC_STRUCT: wrong magic {:08x}".format(m[0]))
            return None

        magic_word, secure_version, reserv1, version, project_name, time, date, idf_ver, app_elf_sha256, reserv2 = struct.unpack( ESP_APP_DESC_STRUCT_FMT, buffer[:ESP_APP_DESC_STRUCT_SIZE] )
        self.magic_word     = magic_word
        self.secure_version = secure_version
        self.reserv1        = reserv1
        self.version        = version.decode("utf-8").strip('\0')
        self.project_name   = project_name.decode("utf-8").strip('\0')
        self.time           = time.decode("utf-8").strip('\0')
        self.date           = date.decode("utf-8").strip('\0')
        self.idf_ver        = idf_ver.decode("utf-8").strip('\0')
        self.app_elf_sha256 = app_elf_sha256
        self.reserv2        = reserv2

    def __repr__(self):
        if self.magic_word==None:
            return "No description found."
        return "secure_version = {:04x} app_version={} project_name={} date={} time={} sdk={}".format( self.secure_version, self.version, self.project_name, self.date, self.time, self.idf_ver )