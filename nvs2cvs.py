#!/usr/bin/env python3
import os, sys
import struct
import base64
import binascii
import argparse
import json
from hexdump import hexdump
from esp32nvs import *


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("nvs_bin_file", help="nvs partition binary file", type=str)
  parser.add_argument("--type", "-t", help="output type", type=str, choices=["cvs", "text", "json"], default="cvs")

  args = parser.parse_args()

  with open(args.nvs_bin_file, 'rb') as fh:
    if args.type == "cvs":
      nvs2cvs(fh)
    elif args.type == "text":
      pages = nvs2txt(fh)
      sys.stdout = sys.stdout = sys.__stdout__ # re-enable print()
    elif args.type == "json":
      sys.stdout = open(os.devnull, 'w') # block print()
      pages = nvs2txt(fh)
      sys.stdout = sys.stdout = sys.__stdout__ # re-enable print()
      print(json.dumps(pages, indent=4))
    else:
      assert(0)


def _main():
    try:
        main()
    except Exception as inst:
        print(type(inst))
        print(inst.args)
        print(inst)


if __name__ == '__main__':
    _main()