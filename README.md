# esp32knife
Tools for ESP32 firmware dissection

Still alpha.

install dependency by executing
```bash
pip install -r requirements.txt
```
or 
```bash
python3 -m pip install requirements.txt
```

Examples:

Load from device
```bash
esp32knife.py load_from_device --port=auto -e
esp32knife.py load_from_device --port=/dev/ttyUSB0 -e
esp32knife.py load_from_device --port=auto --baud=2000000 -e
esp32knife.py --chip=esp32 -m=nncbadge2019 load_from_device --port=auto --baud=2000000 -e
esp32knife.py --chip=esp32 -m=nncbadge2019 load_from_device --port=auto -e
```

Load from full binary file
```bash
esp32knife.py --chip=esp32 -m=esp32badge2019 load_from_file firmware_esp32os_full.bin
esp32knife.py --chip=esp32 load_from_file firmware_nnc2019_full.bin
esp32knife.py --chip=esp32 -m=nncbadge2019 load_from_file boards/nncbadge2019/firmware_nnc2019_full.bin
```

NVS2CVS
```bash
nvs2cvs.py -t=cvs parsed/part.0.nvs
nvs2cvs.py -t=text parsed/part.0.nvs
nvs2cvs.py -t=json parsed/part.0.nvs
nvs2cvs.py -t=cvs espressif/nvs_flash/nvs_partition_generator/sample_multipage_blob.bin
```


