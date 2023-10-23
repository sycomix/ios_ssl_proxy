#!/usr/bin/python3
# used to unpack certsTable.data
# The certsIndex.data file is a Database Index file that contains an array which can be read using NSData,
# this contains a list of sha1 hashes and offsets. 


import binascii
import struct
import sys
import os
from OpenSSL import crypto
import hashlib
import plistlib
import datetime

if sys.argv[1:]:
        cmdtype = sys.argv[1]
else:
        print(f"Usage: {sys.argv[0]} unpack|pack")
        exit(0)

def month_string_to_number(m):
        mtable = [ 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        try:
                return mtable[m-1]
        except:
            raise ValueError('Not a month %d' % m)

def file_sha256(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).digest()

def extract_certs(filename):
        count=0
        st_key=bytearray(open(filename, 'rb').read())
        dirname = f"{os.path.splitext(os.path.basename(filename))[0]}"
        os.mkdir(dirname)

        while 1: 
            index = st_key.find(b"\x30\x82")
            if index < 0: break
            length = struct.unpack(">h", st_key[index+2:index+4])[0] + 5
            if length > len(st_key):
                print("Length of %d extends past end" % length)
                return
            print("index=%d, length=%d" % (index, length))
            certdata = st_key[index:index+length]
            with open(os.path.join(dirname, "%d.cer" % count), "wb") as f:
                f.write(certdata)
            count = count + 1
            st_key = st_key[index+length:]

# block_length determines the offset to the next 8 bytes before the cert.
# index_length is the actual length of the certificate, and if index_length < block_length,
# then the rest of the block is padded with 0xFF bytes
def unpack_certTable(filename):
        st_key=bytearray(open(filename, 'rb').read())
        index=0
        count=0
        dirname = "certsTable" #% os.path.splitext(os.path.basename(filename))[0])
        #os.mkdir(dirname)

        while index < len(st_key):
                index = st_key.find(b"\x30\x82", index)
                if index < 0: break
                clength = struct.unpack(">h", st_key[index+2:index+4])[0] + 5
                ilength = struct.unpack("<I", st_key[index-4:index])[0]
                blength = struct.unpack("<I", st_key[index-8:index-4])[0]
                calclength = ((ilength + 8) & (~7)) + 8 if (ilength + 8) & 7 else ilength + 8
                if calclength != blength: print("%x != %x" % (calclength, blength))
                print("index=%d, index_length=%x, block_length=%x, calclength=%x" % (index, ilength, blength, calclength))
                certdata = st_key[index:index+ilength]
                #cert=crypto.load_certificate(crypto.FILETYPE_ASN1, bytes(certdata))
                #certhash = hashlib.sha1(crypto.dump_publickey(crypto.FILETYPE_ASN1, cert.get_pubkey())).hexdigest()
                #print(certhash)
                #print(cert.digest('sha1').replace(':',''))
                #print(cert.get_subject())
                with open(os.path.join(dirname, "%d.cer" % count), "wb") as f:
                        f.write(certdata)
                count = count + 1
                index = index + clength

def pack_certTable(path, filename):
        index=0
        count=0
        with open(filename, "wb") as outf:
                while 1:
                    filepath = os.path.join(path, "%d.cer" % count)
                    if os.path.isfile(filepath):
                        certdata=open(filepath, 'rb').read()
                        ilength = len(certdata)
                        calclength = ilength + 8
                        if (ilength + 8) & 7: calclength = ((ilength + 8) & (~7)) + 8
                        print("loading %s: len=%x blen=%x" % (filepath, ilength, calclength))
                        outf.write(struct.pack("<I", calclength))
                        outf.write(struct.pack("<I", ilength))
                        outf.write(certdata)
                        outf.write(b"\xFF" * (calclength - ilength - 8))
                    else: break
                    count = count + 1

def unpack_indexTable(filename, path):
        inf = open(filename, 'rb')
        outf = open("certsTable/certsIndex.txt", "wt")
        count=0
        while 1:
                hashdata = inf.read(20)
                if hashdata is None: return
                if len(hashdata) <= 0: return
                index = struct.unpack("<I", inf.read(4))[0] + 8
                filepath = os.path.join(path, "%d.cer" % count)
                outf.write(str("%s %s %d\n" % (filepath, binascii.hexlify(hashdata).decode("utf-8"), index)))
                count=count + 1

def pack_indexTable(path, filename):
        with open(filename, "wb") as outf:
                with open('certsTable/certsIndex.txt') as f:
                    for line in f:
                        parts = line.strip().split(' ')
                        #print(parts)
                        indexbin = struct.pack("<I", int(parts[2])-8)
                        outf.write(binascii.unhexlify(parts[1]))
                        outf.write(indexbin)

def int_to_bytes(x):
    return x.to_bytes((x.bit_length() // 8) + 1, byteorder='little')

def split_hex(value):
        if len(value) <=2: return value
        value = value[2:] if len(value) % 2 == 0 else f"0{value[2:]}"
        return " ".join(value[i:i+2] for i in range(0, len(value), 2))

if cmdtype == 'pack':
        print("Packing certsTable directory to certsTable.data...")
        pack_certTable("./certsTable", "certsTable.data.new")
        pack_indexTable("certsTable", "certsIndex.data.new")
        allowed=plistlib.load(open("Allowed.plist", 'rb'), fmt=plistlib.FMT_BINARY)
        for item in allowed['65F231AD2AF7F7DD52960AC702C10EEFA6D53B11']:
            print(str(binascii.hexlify(item), 'ascii'))
        pm=plistlib.load(open("manifest.data", 'rb'), fmt=plistlib.FMT_BINARY)
        pm['certsIndex.data'] = file_sha256("certsIndex.data")
        pm['certsTable.data'] = file_sha256("certsTable.data")
        plistlib.dump(pm, open("manifest.data.new", 'wb'), fmt=plistlib.FMT_BINARY)
elif cmdtype == 'test':
        if sys.argv[2:]:
                filename = sys.argv[2]
        else:
                print(f"Usage: {sys.argv[0]} test <filename>")
                exit(0)

        print("Creating TrustStore html entry...")
        st_cert=open(filename, 'rb').read()
        cert=crypto.load_certificate(crypto.FILETYPE_ASN1, st_cert)

        outline = f"<tr><td>{cert.get_subject().CN} </td>"
        outline = f"{outline}<td> {cert.get_issuer().CN} </td>"
        key = cert.get_pubkey()
        if key.type() == crypto.TYPE_RSA:
                outline = f"{outline}<td> RSA </td>"
        else:
                print(key.type())
        outline = ("%s<td> %d bits </td>" % (outline, key.bits()))

        sigal = str(cert.get_signature_algorithm(), 'ascii')
        if sigal.startswith('sha1'): sigal = "SHA-1"
        elif sigal.startswith('sha256'): sigal = "SHA-256"
        elif sigal.startswith('sha384'): sigal = "SHA-384"
        elif sigal.startswith('md5'): sigal = "MD5"
        outline = f"{outline}<td> {sigal} </td>"

        serialnum = ('%X' % cert.get_serial_number())
        if len(serialnum) % 2 != 0:
                serialnum = f"0{serialnum}"
        outline = f"{outline}<td> {split_hex(serialnum)} </td>"

        expstr = datetime.datetime.strptime(str(cert.get_notAfter(),'ascii'), "%Y%m%d%H%M%SZ")
        month = month_string_to_number(expstr.month)
        exp = ("%.2d:%.2d:%.2d %s %s, %s" % (expstr.hour, expstr.minute, expstr.second, month, expstr.day, expstr.year))
        outline = f"{outline}<td> {exp} </td>"
        outline = f"{outline}<td> Always</td></tr>"
        print(outline)
elif cmdtype == 'unpack':
        print("Unpacking certsTable.data to certsTable directory...")
        unpack_certTable("certsTable.data")
        unpack_indexTable("certsIndex.data", "certsTable")
