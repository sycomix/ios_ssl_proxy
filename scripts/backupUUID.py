#!/usr/bin/python2.7

# -*- coding: utf-8 -*-
import sys
import os
import socket
import hashlib
import plistlib
from operator import xor

def load_device_info(sn):
    return (
        plistlib.readPlist(sn)
        if '.xml' in sn
        else plistlib.readPlist(f"devices/{sn}.xml")
    )

if sys.argv[1:]:
    device = sys.argv[1]
else:
    print(f"Usage: {sys.argv[0]} <device>")
    exit(0)

devinfo = load_device_info(device)
backupuuid = int(hashlib.sha1(devinfo['UniqueDeviceID']).hexdigest(), 16)
print('{:x}'.format(backupuuid))
backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['DeviceClass']).hexdigest(), 16))
print('{:x}'.format(backupuuid))
backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['ProductType']).hexdigest(), 16))
print('{:x}'.format(backupuuid))
#backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['SerialNumber']).hexdigest(), 16))
#print('{:x}'.format(backupuuid))
#backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['DeviceColor']).hexdigest(), 16))
#print('{:x}'.format(backupuuid))
backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['HardwareModel']).hexdigest(), 16))
print('{:x}'.format(backupuuid))
backupuuid = xor(backupuuid, int(hashlib.sha1("iPhone 6s Plus").hexdigest(), 16))
print('{:x}'.format(backupuuid))
backupuuid = xor(backupuuid, int(hashlib.sha1(devinfo['EnclosureColor']).hexdigest(), 16))
print('{:x}'.format(backupuuid))


# calculate FMD hash:
#  v3 = objc_msgSend(self->_dsid, "hash");
#  v4 = (unsigned int)v3 ^ (unsigned int)objc_msgSend(v2->_udid, "hash");
#  v5 = v4 ^ (unsigned int)objc_msgSend(v2->_serialNumber, "hash");
#  return (unsigned int)objc_msgSend(v2->_productType, "hash") ^ v5;

