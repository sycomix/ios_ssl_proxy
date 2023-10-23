#!/usr/bin/python2.7
import frida
import sys

# MobileGestalt functions:
# CFPropertyListRef MGCopyAnswer(CFStringRef property);
# int MGSetAnswer(CFStringRef question, CFTypeRef answer);
# Boolean MGGetBoolAnswer(CFStringRef property);
# MGGetSInt32Answer
# Note: the SHA1 hashes seem to be the SHA1 hashes of DER certificates

session = frida.get_usb_device().attach("Settings")
fo = open("SSL.bin", "wb")
#fo2 = open("CCDigest.bin", "wb")
fo3 = open("functionlog.txt", "wt")
#fo4 = open("CCCryptorCreateWithMode", "wb")
#fo5 = open("decode.bin", "wb")
#fo6 = open("aesencrypt.bin", "wb")
script = session.create_script("""
var f1 = Module.findExportByName("Foundation",
    "CFWriteStreamWrite");
Interceptor.attach(f1, {
    onEnter: function (args) {
                var bytes = Memory.readByteArray(args[1], args[2].toInt32());
                send("CFWriteStreamWrite", bytes);
    }
});
/*
var f1 = Module.findExportByName("Security",
    "SSLWrite");
Interceptor.attach(f1, {
    onEnter: function (args) {
		var bytes = Memory.readByteArray(args[1], args[2].toInt32());
		send("SSLWrite", bytes);
    }
});
var f2 = Module.findExportByName("Security",
    "SSLRead");
Interceptor.attach(f2, {
    onEnter: function (args) {
 		this.dataPtr = args[1];
		this.dataSize = args[2].toInt32();
    },
    onLeave: function (retval) {
		var bytes = Memory.readByteArray(this.dataPtr, this.dataSize);
		send("SSLRead", bytes);
    }
});
*/
/*
var f3 = Module.findExportByName("libcommonCrypto.dylib",
    "CCDigest");
Interceptor.attach(f3, {
    onEnter: function (args) {
		var bytes = Memory.readByteArray(args[2], args[1].toInt32());
		send("CCDigest", bytes);
    }
});
var f4 = Module.findExportByName("libcommonCrypto.dylib",
    "CCCryptorCreateWithMode");
Interceptor.attach(f4, {
    onEnter: function (args) {
		var bytes = Memory.readByteArray(args[5], args[6].toInt32());
		send("CCCryptorCreateWithMode", bytes);
    }
});
var f5 = Module.findExportByName("libcommonCrypto.dylib",
    "CCCryptorGCMAddIV");
Interceptor.attach(f5, {
    onEnter: function (args) {
		var bytes = Memory.readByteArray(args[1], args[2].toInt32());
		send("CCCryptorGCMAddIV", bytes);
    }
});
*/
/*
var f6 = Module.findExportByName("libcrypto.so",
    "AES_set_decrypt_key");
Interceptor.attach(f6, {
    onEnter: function (args) {
		var bytes = Memory.readByteArray(args[0], 16);
		send("AES_set_decrypt_key", bytes);
    }
});
*/
""")
def on_message(message, data):
	pname = message['payload']
	print(pname)
	fo3.write(pname+"\n")
	if pname in ["CFWriteStreamWrite", "SSLRead"]:
		fo.write(data)
	#elif (pname == "CCDigest"):
	#	fo2.write(data)
	#elif (pname == "CCCryptorCreateWithMode"):
	#	fo4.write(data)
	#elif (pname == "CCCryptorGCMAddIV"):
	#	fo5.write(data)
	#elif (pname == "AES_cbc_encrypt"):
	#	fo6.write(data)
try:
    script.on('message', on_message)
    script.load()
    sys.stdin.read()
except KeyboardInterrupt as e:
    fo.close()
    #fo2.close()
    fo3.close()
    #fo4.close()
    #fo5.close()
    #fo6.close()
    sys.exit(0)
