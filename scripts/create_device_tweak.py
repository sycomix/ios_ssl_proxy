#!/usr/bin/python

import binascii
import struct
import sys
import os
from OpenSSL import crypto
import hashlib
import plistlib
import datetime

# scp com.nablac0d3.SSLKillSwitchSettings.plist root@192.168.0.144:/var/mobile/Library/Preferences/com.nablac0d3.SSLKillSwitchSettings.plist
key_list = ["BuildVersion", "DeviceColor", "DeviceEnclosureColor", "HardwareModel", "MarketingName", "ModelNumber", "ProductType", "ProductVersion", "SerialNumber", "UniqueDeviceID", "WiFiAddress", "DieId", "EnclosureColor", "HardwareModel", "HardwarePlatform", "BluetoothAddress", "EthernetAddress", "UniqueChipID", "DieID", "MLBSerialNumber", "FirmwareVersion", "CPUArchitecture", "WirelessBoardSnum", "BasebandCertId", "BasebandChipID", "BasebandKeyHashInformation", "BasebandMasterKeyHash", "BasebandSerialNumber", "BasebandVersion", "BasebandRegionSKU", "BoardId", "InternationalMobileEquipmentIdentity", "MobileEquipmentIdentifier", "WirelessBoardSerialNumber", "RegulatoryModelNumber", "PkHash", "BasebandFirmwareManifestData", "ChipID", "ChipSerialNo", "CertID", "BasebandRegionSKU", "IntegratedCircuitCardIdentity", "CarrierBundleInfoArray", "InternationalMobileSubscriberIdentity"]

def load_device_info(sn):
    return (
        plistlib.readPlist(sn)
        if '.xml' in sn
        else plistlib.readPlist(f"devices/{sn}.xml")
    )

if sys.argv[1:]:
    device = sys.argv[1]
else:
    print(f"Usage: {sys.argv[0]} device")
    exit(0)

p = dict()
p["shouldDisableCertificateValidation"] = True
devinfo = load_device_info(device)
for key in devinfo:
    if key in key_list:
        if key == "BasebandVersion":
            p['BasebandFirmwareVersion'] = devinfo[key]
            p[key] = devinfo[key]
        elif key == "DieID":
            p['DieId'] = devinfo[key]
        elif key == "EnclosureColor":
            p['DeviceEnclosureColor'] = devinfo[key]
        elif key == "EthernetAddress":
            p['EthernetMacAddress'] = devinfo[key]
        elif key == "HardwareModel":
            p['HWModelStr'] = devinfo[key]
            p[key] = devinfo[key]
        elif key == "MarketingName":
            p['marketing-name'] = devinfo[key]
        elif key == "WiFiAddress":
            p['WifiAddress'] = devinfo[key]
        elif key == "WirelessBoardSerialNumber":
            p['WirelessBoardSnum'] = devinfo[key]
        else:
            p[key] = devinfo[key]
        print(f"{key} = {devinfo[key]}")

p['UniqueDeviceIDData'] = plistlib.Data(binascii.unhexlify(p['UniqueDeviceID']))
p['mac-address-wifi0'] = plistlib.Data(binascii.unhexlify(p['WifiAddress'].replace(':','')))
p['mac-address-bluetooth0'] = plistlib.Data(binascii.unhexlify(p['BluetoothAddress'].replace(':','')))
#p['IOMACAddress'] = p['mac-address-wifi0']
#udid = ~hex(devinfo['UniqueDeviceID'])
#print(udid)
plistlib.writePlist(p, "com.nablac0d3.SSLKillSwitchSettings.plist")
