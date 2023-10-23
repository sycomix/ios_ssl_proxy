#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
import sys
import os
import socket
import ssl
import select
import httplib
import urlparse
import threading
import gzip
import zlib
import time
import json
import re
import plistlib

# Idea I have to load the devices plist file, then for every item in the plist file, search all log files for uppercase, lowercase, base64 encoded, converted hex->binary if hex value, converted decimal to hex if hex value, base84 decoded if base64 encoded, remove colons if MAC address

if sys.argv[1:]:
        devicestr = sys.argv[1]
else:
        print(f"Usage: {sys.argv[0]} <device>")
        exit(0)

def load_device_info(sn):
        return (plistlib.readPlist(sn)
                if '.xml' in sn else plistlib.readPlist(f"devices/{sn}.xml"))

devinfo = load_device_info(devicestr)

for file in os.listdir("logs"):
            #print("filename %s" % file)
        for key in devinfo:
                if key in ['ProductName', 'DeviceClass']: continue
                if isinstance(devinfo[key], str):
                        if devinfo[key] == '' or len(devinfo[key]) < 3: continue
                        data=bytes(open(os.path.join("logs", file), 'rb').read())
                        if devinfo[key] in data:
                                print(f"{key} {devinfo[key]} in {file}")
                            #print("%s: %s" % (key, devinfo[key]))
                elif isinstance(devinfo[key], bool):
                    continue
                elif isinstance(devinfo[key], int):
                        if len(str(devinfo[key])) > 2 and str(devinfo[key]) in data:
                                print(f"{key} {devinfo[key]} in {file}")
                elif isinstance (devinfo[key], plistlib.Data):
                        datastr = str(devinfo[key].data)
                        if len(datastr)> 2 and datastr in data:
                                print(f"{key} {devinfo[key]} in {file}")
