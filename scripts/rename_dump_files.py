#!/usr/bin/python

import os

for filename in os.listdir("."):
    if '.dmp' not in filename: continue
    addr = filename.split('.')[0].replace('dump', '')
    addr = str.format('{:08X}', int(addr, 16))
    newfilename = f"dump0x{addr}.dmp"
    if (filename == newfilename): continue
    print(f"rename {filename} to {newfilename}")
    os.rename(filename, newfilename)

with open("../process.dmp", "ab") as fout:
    for filename in os.listdir("."):
        if '.dmp' not in filename: continue
        data = open(filename,'rb').read()
        fout.write(data)
