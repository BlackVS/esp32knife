#!/usr/bin/env python3
import os
import struct
import base64
import binascii
import shutil
from hexdump import hexdump
from collections import OrderedDict

nvs_types =  {
  0x01: "U8",
  0x11: "I8",
  0x02: "U16",
  0x12: "I16",
  0x04: "U32",
  0x14: "I32",
  0x08: "U64",
  0x18: "I64",
  0x21: "STR",
  0x41: "BLOB",
  0x42: "BLOB_DATA",
  0x48: "BLOB_IDX",
  0xFF: "ANY"
}

entry_state_descs = {
        3: "Empty",
        2: "Written",
        0: "Erased"
}

nvs_sector_states = {
        0xFFFFFFFF : "EMPTY",
        0xFFFFFFFE : "ACTIVE",
        0xFFFFFFFC : "FULL",
        0xFFFFFFF8 : "FREEING",
        0xFFFFFFF0 : "CORRUPT"
}

namespaces = {}

BLOB_DATA_DIR   = "blob_data"
BLOD_DATA_INDEX = 0

def ASHEX(b):
    return " ".join(map(hex, b))


def create_empty_dir(fname):
    if os.path.exists(fname):
        shutil.rmtree(fname)
    if not os.path.exists(fname):
        os.makedirs(fname)

def dump_nvs_entries(entries, entry_state_bitmap, fpos):
    entries_out = []
    i = 0
    while i < 126:
        entry_data = {}
        print("  Entry {} (offset = {:08x})".format(i,fpos+i*32))
        print("  Bitmap State : %s" % (entry_state_descs[int(entry_state_bitmap[i])]))
        entry_data["entry_state"] = entry_state_descs[int(entry_state_bitmap[i])]

        entry = entries[i]
        state = entry_state_bitmap[i]
    
        entry_ns = entry[0]
        entry_type = entry[1]
        entry_span = entry[2]
        chunk_index = entry[3]

        key = entry[8:24]

        data = entry[24:]
        if(entry_type == 0):
            i += 1
            continue

        if(nvs_types[entry_type] == "ANY"):
            i += 1
            continue

        decoded_key = ''
        for c in key:
            if(c == 0):
                break
            decoded_key += chr(c)

        key = decoded_key

        print("    Written Entry %d" % (i))
        print("      NS Index : %d" % (entry_ns))
        entry_data["entry_ns_index"] = entry_ns

        if(entry_ns != 0 and entry_ns in namespaces):
            print("          NS : %s" % (namespaces[entry_ns]))
            entry_data["entry_ns"] = namespaces[entry_ns]

        print("      Type : %s" % (nvs_types[entry_type]))
        print("      Span : %d" % (entry_span))
        print("      ChunkIndex : %d" % (chunk_index))
        print("      Key : " + key)
        entry_data["entry_type"] = nvs_types[entry_type]
        entry_data["entry_span"] = entry_span
        entry_data["entry_chunk_index"] = chunk_index
        entry_data["entry_key"] = key


        if(nvs_types[entry_type] == "U8"):
            data = struct.unpack("<B", data[0:1])[0]
            print("      Data (U8) : 0x{:x}".format(data))
            if(entry_ns == 0):
                namespaces[data] = key
            entry_data["entry_data_type"] = "U8"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "I8"):
            data = struct.unpack("<b", data[0:1])[0]
            print("      Data (I8) : 0x{:x}".format(data))
            entry_data["entry_data_type"] = "I8"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "U16"):
            data = struct.unpack("<H", data[0:2])[0]
            print("      Data (U16) : 0x{:02x}".format(data))
            entry_data["entry_data_type"] = "U16"
            entry_data["entry_data"] = data
        
        elif(nvs_types[entry_type] == "I16"):
            data = struct.unpack("<h", data[0:2])[0]
            print("      Data (I16) : 0x{:02x}".format(data))
            entry_data["entry_data_type"] = "I16"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "U32"):
            data = struct.unpack("<I", data[0:4])[0]
            print("      Data (U32) : 0x{:04x}".format(data))
            entry_data["entry_data_type"] = "U32"
            entry_data["entry_data"] = data
        
        elif(nvs_types[entry_type] == "I32"):
            data = struct.unpack("<i", data[0:4])[0]
            print("      Data (I32) : 0x{:04x}".format(data))
            entry_data["entry_data_type"] = "I32"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "STR"):
            str_size = struct.unpack("<H", data[0:2])[0]

            print("      String :")
            entry_data["entry_data_type"] = "STR"
            print("        Size : %d " % (str_size))
            print("        Rsv2 : %s " % ASHEX(data[2:4]))
            print("        CRC32: %s " % ASHEX(data[4:8]))
            entry_data["entry_data_size"] = str_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            data = data[0:str_size-1].decode('ascii')
            print("        Data : %s" % (data))
            entry_data["entry_data"] = str(data)

        elif(nvs_types[entry_type] == "BLOB_DATA"):
            blob_data_size = struct.unpack("<H", data[0:2])[0]
            print("      Blob Data :")
            entry_data["entry_data_type"] = "BLOB_DATA"
            print("        Size : %d " % (blob_data_size))
            entry_data["entry_data_size"] = blob_data_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            print("        Data :")
            hexdump(data[:blob_data_size])
            entry_data["entry_data"] = base64.b64encode(data[:blob_data_size]).decode('ascii')

        elif(nvs_types[entry_type] == "BLOB"):
            blob_size = struct.unpack("<H", data[0:2])[0]
            print("      Data (Blob) :")
            entry_data["entry_data_type"] = "BLOB"
            print("        Size : %d " % (blob_size))
            entry_data["entry_data_size"] = blob_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            print("        Data :")
            hexdump(data[:blob_size])
            entry_data["entry_data"] = base64.b64encode(data[:blob_size]).decode('ascii')

        elif(nvs_types[entry_type] == "BLOB_IDX"):
            idx_size = struct.unpack("<I", data[0:4])[0]
            chunk_count = struct.unpack("<B", data[5:6])[0]
            chunk_start = struct.unpack("<B", data[6:7])[0]
            print("      Blob IDX :")
            entry_data["entry_data_type"] = "BLOB_IDX"
            print("        Size        : %d " % (idx_size))
            print("        Chunk Count : %d " % (chunk_count))
            print("        Chunk Start  : %d " % (chunk_start))
            entry_data["entry_data_size"] = idx_size
            entry_data["entry_data_chunk_count"] = chunk_count
            entry_data["entry_data_chunk_start"] = chunk_start

        else:
            print("      Data : %s" % (str(data)))
            entry_data["entry_data"] = str(data)

        entries_out.append(entry_data)
        i += 1
        print("")
    return entries_out

def nvs2txt(fh):
    pages = []
    fh.seek(0, os.SEEK_END)
    file_len = fh.tell()

    sector_pos = 0
    x = 0
    while(sector_pos < file_len):
        page_data = {}

        fh.seek(sector_pos)
        
        ofs_page = fh.tell()

        raw_page_state = fh.read(4)
        page_state = nvs_sector_states[struct.unpack("<I", raw_page_state)[0]]

        raw_seq_no = fh.read(4)
        seq_no = struct.unpack("<I", raw_seq_no)[0]

        raw_version = fh.read(1)
        version = (ord(raw_version) ^ 0xff) + 1

        print( "Page {} ( offset={:08x} )".format(x, ofs_page))
        print("  page state   : {} ({}) ".format(page_state, ASHEX(raw_page_state)))
        print("  page seq no. : {} ({}) ".format(seq_no, ASHEX(raw_seq_no)))
        print("  page version : {} ({}) ".format(version, ASHEX(raw_version)))
       
        page_data["page_state"] = page_state
        page_data["page_seq_no"] = seq_no
        page_data["page_version"] = version

        fh.read(19) # unused

        ofs_crc_32 = fh.tell()
        crc_32 = struct.unpack("<I", fh.read(4))[0]
        print("  crc32 : 0x{:04x} (offset={:08x})".format(crc_32, ofs_crc_32))
        page_data["page_crc_32"] = crc_32

        entry_state_bitmap = fh.read(32)
        entry_state_bitmap_decoded = ''

        for entry_num in range(0, 126):
            bitnum = entry_num * 2
            byte_index = int(bitnum / 8)
            temp = entry_state_bitmap[byte_index]
            
            temp = temp >> (6 - (bitnum % 8))
            temp = temp & 3
            entry_state_bitmap_decoded = entry_state_bitmap_decoded + str(temp)

        print("  page entry state bitmap (decoded) : %s" % (entry_state_bitmap_decoded))
        page_data["page_entry_state_bitmap"] = entry_state_bitmap_decoded 
        sector_pos += 4096
        x += 1

        entries = []
        entry_data = ''
        ofs_entries = fh.tell()
        print("\n  Read entries data ( offset = {:08x} ):".format(ofs_entries))
        for entry in entry_state_bitmap_decoded:
            entry_data = fh.read(32)
            entries.append(entry_data)

        page_data["entries"] = dump_nvs_entries(entries, entry_state_bitmap_decoded, ofs_entries )

        print("")
        print("")
        print("------------------------------------------------------------------------------")
        print("")
        pages.append(page_data)

    print("")
    return pages


def parse_nvs_entries(entries, entry_state_bitmap):
    entries_out = []
    i = 0
    while i < 126:
        entry_data = {}
        entry_data["entry_state"] = entry_state_descs[int(entry_state_bitmap[i])]

        entry = entries[i]
        state = entry_state_bitmap[i]
    
        entry_ns = entry[0]
        entry_type = entry[1]
        entry_span = entry[2]
        chunk_index = entry[3]

        key = entry[8:24]

        data = entry[24:]
        if(entry_type == 0):
            i += 1
            continue

        if(nvs_types[entry_type] == "ANY"):
            i += 1
            continue

        decoded_key = ''
        for c in key:
            if(c == 0):
                break
            decoded_key += chr(c)

        key = decoded_key

        if(entry_ns != 0):
            entry_data["entry_ns"] = entry_ns

        entry_data["entry_type"] = nvs_types[entry_type]
        entry_data["entry_span"] = entry_span
        entry_data["entry_chunk_index"] = chunk_index
        entry_data["entry_key"] = key

        if(nvs_types[entry_type] == "U8"):
            data = struct.unpack("<B", data[0:1])[0]
            if(entry_ns == 0):
                namespaces[data] = key
            entry_data["entry_data_type"] = "U8"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "I8"):
            data = struct.unpack("<b", data[0:1])[0]
            entry_data["entry_data_type"] = "I8"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "U16"):
            data = struct.unpack("<H", data[0:2])[0]
            entry_data["entry_data_type"] = "U16"
            entry_data["entry_data"] = data
        
        elif(nvs_types[entry_type] == "I16"):
            data = struct.unpack("<h", data[0:2])[0]
            entry_data["entry_data_type"] = "I16"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "U32"):
            data = struct.unpack("<I", data[0:4])[0]
            entry_data["entry_data_type"] = "U32"
            entry_data["entry_data"] = data
        
        elif(nvs_types[entry_type] == "I32"):
            data = struct.unpack("<i", data[0:4])[0]
            entry_data["entry_data_type"] = "I32"
            entry_data["entry_data"] = data

        elif(nvs_types[entry_type] == "STR"):
            str_size = struct.unpack("<H", data[0:2])[0]
            entry_data["entry_data_type"] = "STR"
            entry_data["entry_data_size"] = str_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            data = data[0:str_size-1].decode('ascii')
            entry_data["entry_data"] = str(data)

        elif(nvs_types[entry_type] == "BLOB_DATA"):
            blob_data_size = struct.unpack("<H", data[0:2])[0]
            entry_data["entry_data_type"] = "BLOB_DATA"
            entry_data["entry_data_size"] = blob_data_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            #hexdump(data[:blob_data_size])
            entry_data["entry_data"] = base64.b64encode(data[:blob_data_size]).decode('ascii')

        elif(nvs_types[entry_type] == "BLOB"):
            blob_size = struct.unpack("<H", data[0:2])[0]
            entry_data["entry_data_type"] = "BLOB"
            entry_data["entry_data_size"] = blob_size
            data = b'' 
            for x in range(1, entry_span):
                i += 1
                data += entries[i]
            #hexdump(data[:blob_size])
            entry_data["entry_data"] = base64.b64encode(data[:blob_size]).decode('ascii')

        elif(nvs_types[entry_type] == "BLOB_IDX"):
            idx_size = struct.unpack("<I", data[0:4])[0]
            chunk_count = struct.unpack("<B", data[5:6])[0]
            chunk_start = struct.unpack("<B", data[6:7])[0]
            entry_data["entry_data_type"] = "BLOB_IDX"
            entry_data["entry_data_size"] = idx_size
            entry_data["entry_data_chunk_count"] = chunk_count
            entry_data["entry_data_chunk_start"] = chunk_start

        else:
            entry_data["entry_data"] = str(data)

        entries_out.append(entry_data)
        i += 1
    return entries_out


def get_entries(entries, ename, etype):
    chunks = dict()
    chsize = 0
    for pc in entries:
        if pc["entry_state"]=="Written" and pc["entry_type"]==etype and pc["entry_key"]==ename:
            chunks[ pc["entry_chunk_index"] ]=pc
            chsize += pc["entry_data_size"]

    chunks = OrderedDict( sorted(chunks.items()) )
    return (chsize, chunks)

def entries2cvs(parsed):
    #print(namespaces)
    for ni,nn in namespaces.items():
        print("{},namespace,,".format(nn))
        for p in parsed:
            p_entry_state = p["entry_state"]
            if p_entry_state!="Written":
                continue
            p_entry_ns = p.get("entry_ns",None)
            if p_entry_ns==None or p_entry_ns!=ni: #None - new namespace
                continue
            # if p_entry_state!="Written":
            p_entry_type = p["entry_type"]
            p_entry_data = p.get("entry_data",None)
            p_entry_span  = p["entry_span"]
            p_chunk_index = p["entry_chunk_index"]
            p_entry_key   = p["entry_key"]
            p_entry_data_type = p["entry_data_type"]
            p_entry_data_size = p.get("entry_data_size", None)
            #p_entry_data_chunk_count = p["entry_data_chunk_count"]
            #p_entry_data_chunk_start = p["entry_data_chunk_start"]
            if p_entry_type=="U8":
                print("{},data,u8,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="I8":
                print("{},data,i8,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="U16":
                print("{},data,u16,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="I16":
                print("{},data,i16,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="U32":
                print("{},data,u32,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="I32":
                print("{},data,i32,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="U64":
                print("{},data,u64,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="I64":
                print("{},data,i64,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="STR":
                print("{},data,string,{}".format(p_entry_key,p_entry_data))
            elif p_entry_type=="BLOB":
                print(p_entry_key,p)
            elif p_entry_type=="BLOB_DATA": #data in base64
                if p_chunk_index==0: #rest already processed
                    # get all chunks with same name

                    chsize, chunks = get_entries( parsed, p_entry_key, p_entry_type )
                    data = bytes()
                    for i,c in chunks.items():
                        data += base64.b64decode( c["entry_data"] )

                    if len(chunks)==1 and chsize<100:
                        print("{},data,base64,{}".format(p_entry_key,p_entry_data))
                    else:
                        #print(data)
                        fname = os.path.join(BLOB_DATA_DIR, p_entry_key+".bin")
                        with open(fname,"wb+") as f:
                            f.write(data)
                        print("{},file,binary,{}".format(p_entry_key,fname))

            elif p_entry_type=="BLOB_IDX":
                pass #just skip due to already parsed, blobs joined
            elif p_entry_type=="ANY":
                print(p_entry_key,p)
            else:
                print(p)
                assert(0)

def nvs2cvs(fh, blobdatadir = "blob_data"):
    global BLOB_DATA_DIR
    BLOB_DATA_DIR = blobdatadir
    create_empty_dir(BLOB_DATA_DIR)

    fh.seek(0, os.SEEK_END)
    file_len = fh.tell()

    print("# NVS csv file")
    print("key,type,encoding,value")

    sector_pos = 0
    x = 0

    parsed = []
    
    while(sector_pos < file_len):

        fh.seek(sector_pos)
        

        raw_page_state = fh.read(4)
        raw_seq_no = fh.read(4)
        raw_version = fh.read(1)

        fh.read(19) # unused

        ofs_crc_32 = fh.tell()
        raw_crc_32 = fh.read(4)

        entry_state_bitmap = fh.read(32)
        entry_state_bitmap_decoded = ''

        for entry_num in range(0, 126):
            bitnum = entry_num * 2
            byte_index = int(bitnum / 8)
            temp = entry_state_bitmap[byte_index]
            
            temp = temp >> (6 - (bitnum % 8))
            temp = temp & 3
            entry_state_bitmap_decoded = entry_state_bitmap_decoded + str(temp)

        sector_pos += 4096
        x += 1

        entries = []
        entry_data = ''
        for entry in entry_state_bitmap_decoded:
            entry_data = fh.read(32)
            entries.append(entry_data)
        parsed += parse_nvs_entries(entries, entry_state_bitmap_decoded)

    entries2cvs(parsed)

    return True

#parser = argparse.ArgumentParser()
#parser.add_argument("nvs_bin_file", help="nvs partition binary file", type=str)
#parser.add_argument("-output_type", help="output type", type=str, choices=["text", "json"], default="text")

#args = parser.parse_args()

#with open(args.nvs_bin_file, 'rb') as fh:
#  if(args.output_type != "text"):
#    sys.stdout = open(os.devnull, 'w') # block print()

#  pages = read_pages(fh)

#  sys.stdout = sys.stdout = sys.__stdout__ # re-enable print()

#  if(args.output_type == "json"):
#      print(json.dumps(pages))

