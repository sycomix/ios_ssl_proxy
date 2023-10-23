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
import base64
import SocketServer
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn, BaseRequestHandler
from cStringIO import StringIO
from HTMLParser import HTMLParser
from OpenSSL import crypto, SSL
from pyasn1.type import univ, constraint, char, namedtype, tag
from pyasn1.codec.der.decoder import decode
from pyasn1.error import PyAsn1Error
import fcntl
import struct
import binascii
import netifaces
import hashlib
import requests
import uuid
import ConfigParser
import signal
from ProxyRewrite import *
from ProxyAPNHandler import *

TYPE_RSA = crypto.TYPE_RSA
TYPE_DSA = crypto.TYPE_DSA

# NOTE: these are special case hostnames where the cert forging isn't working correctly:
# gsa.apple.com, gsas.apple.com, and p**-fmip.icloud.com (such as p51-fmip.icloud.com)_


def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])

def with_color(c, s):
    return "\x1b[%dm%s\x1b[0m" % (c, s)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    # lets use IPv4 instead of IPv6
    #address_family = socket.AF_INET6
    address_family = socket.AF_INET
    daemon_threads = True

    def handle_error(self, request, client_address):
        # surpress socket/ssl related errors
        cls, e = sys.exc_info()[:2]
        if cls is not socket.error and cls is not ssl.SSLError:
            return HTTPServer.handle_error(self, request, client_address)

class ProxyRequestHandler(BaseHTTPRequestHandler):
    cakey = 'ssl/ca.key'
    cacert = 'ssl/ca.crt'
    certkey = 'ssl/cert.key'
    certdir = 'certs/'
    timeout = 5
    lock = threading.Lock()
    certKey=None
    issuerCert=None
    issuerKey=None

    def __init__(self, *args, **kwargs):
        self.tls = threading.local()
        self.tls.conns = {}

        if ProxyRewrite.usejbca:
            self.cacert = 'ssl/jbca.crt'
            self.cakey = 'ssl/jbca.key'

        self.certKey=crypto.load_privatekey(crypto.FILETYPE_PEM, open(self.certkey, 'rt').read())
        self.issuerCert=crypto.load_certificate(crypto.FILETYPE_PEM, open(self.cacert, 'rt').read())
        self.issuerKey=crypto.load_privatekey(crypto.FILETYPE_PEM, open(self.cakey, 'rt').read())

        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_error(self, format, *args):
        # surpress "Request timed out: timeout('timed out',)"
        if isinstance(args[0], socket.timeout):
            return

        self.log_message(format, *args)

    # hack to handle so that we can ignore certain hostnames
    def handle(self):
        dst_ip, dst_port = ProxyRewrite.get_socket_info(self.request)
        #if ProxyRewrite.is_courier_push_ip(dst_ip) and dst_port == 443:
        #    print("APN connection %s:%s" % (dst_ip, dst_port))
        #    apnproxy = ProxyAPNHandler(dst_ip, dst_port)
        #    apnproxy.main_loop()
        #    return
        # use transparent mode
        if ProxyRewrite.transparent == True and dst_port != 80:
            certkey = None
            with self.lock:
                if ProxyRewrite.use_rewrite_pubkey:
                    certpath, keysize = ProxyRewrite.rewrite_cert_pubkey(self.certdir, self.certKey, self.issuerCert, self.issuerKey, dst_ip, dst_port)
                    certkey = f"ssl/keys/cert{keysize}.key"
                else:
                    certpath = ProxyRewrite.generate_cert(self.certdir, self.certKey, self.issuerCert, self.issuerKey, dst_ip, dst_port)
                    certkey = self.certkey
            try:
                self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=True, suppress_ragged_eofs=True)
            except ssl.SSLError as e:
                try:
                    ssl._https_verify_certificates(enable=False)
                    self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=False, suppress_ragged_eofs=True)
                except ssl.SSLError as e:
                    print("SSLError occurred on %s: %r" % (dst_ip,e))
                    self.finish()
        elif ProxyRewrite.server_address != dst_ip and dst_port in [443, 993]:
            print(f"Handling {dst_ip}:{dst_port}")
            certkey = None
            with self.lock:
                if ProxyRewrite.use_rewrite_pubkey:
                    certpath, keysize = ProxyRewrite.rewrite_cert_pubkey(self.certdir, self.certKey, self.issuerCert, self.issuerKey, dst_ip, dst_port)
                    certkey = f"ssl/keys/cert{keysize}.key"
                else:
                    certpath = ProxyRewrite.generate_cert(self.certdir, self.certKey, self.issuerCert, self.issuerKey, dst_ip, dst_port)
                    certkey = self.certkey
            try:
                self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=True, suppress_ragged_eofs=True)
            except ssl.SSLError as e:
                try:
                    ssl._https_verify_certificates(enable=False)
                    self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=False, suppress_ragged_eofs=True)
                except ssl.SSLError as e:
                    print("SSLError occurred on %s: %r" % (dst_ip,e))
                    self.finish()

        self.rfile = self.connection.makefile("rb", self.rbufsize)
        self.wfile = self.connection.makefile("wb", self.wbufsize)

        #    """Handle multiple requests if necessary."""
        self.close_connection = 1
        self.handle_one_request()
        while not self.close_connection:
            self.handle_one_request()

    def handle_one_request(self):
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(414)
                return
            if not self.raw_requestline:
                self.close_connection = 1
                return
            if re.search("CONNECT|OPTIONS|GET|HEAD|POST|PUT|DELETE|MKCOL|MOVE|REPORT|PROPFIND|PROPPATCH|ORDERPATCH", self.raw_requestline) is None:
                self.wfile.flush()
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                #self.close_connection = 1
                return
            mname = 'do_' + self.command
            if not hasattr(self, mname):
                self.do_GET()
            else:
                method = getattr(self, mname)
                method()
            self.wfile.flush() #actually send the response if not already done.
        except socket.timeout, e:
            #a read or a write timed out.  Discard this connection
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return

    def do_CONNECT(self):
        hostname = hostname = ProxyRewrite.get_hostname(self.headers, self.path)
        print(f"CONNECT {self.path}")

        if 'Proxy-Connection' in self.headers:
            del self.headers['Proxy-Connection']

        if ProxyRewrite.dev1info != None and ProxyRewrite.dev2info != None:
            self.headers = ProxyRewrite.rewrite_headers(self.headers, '')

        #if 'captive.apple.com' in self.path or 'static.ips.apple.com' in self.path:
        #    self.path = 'http://ui.iclouddnsbypass.com/deviceservices/buddy/barney_activation_help_en_us.buddyml'
        #    self.connect_intercept()
        if os.path.isfile(self.cakey) and os.path.isfile(self.cacert) and os.path.isfile(self.certkey) and os.path.isdir(self.certdir) and ProxyRewrite.intercept_this_host(hostname):
            self.connect_intercept()
        else:
            self.connect_relay()

    def connect_intercept(self):
        hostname = ProxyRewrite.get_hostname(self.headers, self.path)
        certkey = None

        with self.lock:
            if ProxyRewrite.use_rewrite_pubkey:
                certpath, keysize = ProxyRewrite.rewrite_cert_pubkey(self.certdir, self.certKey, self.issuerCert, self.issuerKey, hostname, 443)
                certkey = f"ssl/keys/cert{keysize}.key"
            else:
                certpath = ProxyRewrite.generate_cert(self.certdir, self.certKey, self.issuerCert, self.issuerKey, hostname, 443)
                certkey = self.certkey

        self.wfile.write("%s %d %s\r\n" % (self.protocol_version, 200, 'Connection Established'))
        self.end_headers()

        try:
            ssl._https_verify_certificates(enable=False)
            self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=False, suppress_ragged_eofs=True)
        except ssl.SSLError as e:
            print("SSLError occurred on %s: %r" % (self.path,e))
            try:
                ssl._https_verify_certificates(enable=False)
                self.connection = ssl.wrap_socket(self.connection, keyfile=certkey, certfile=certpath, ssl_version=ssl.PROTOCOL_TLSv1_2, server_side=True, do_handshake_on_connect=True, suppress_ragged_eofs=True)
            except ssl.SSLError as e:
                print("SSLError occurred on %s: %r" % (self.path,e))
                self.finish()

        self.rfile = self.connection.makefile("rb", self.rbufsize)
        self.wfile = self.connection.makefile("wb", self.wbufsize)

        conntype = self.headers.get('Connection', '')
        if self.protocol_version == "HTTP/1.1" and conntype.lower() != 'close':
            self.close_connection = 0
        else:
            self.close_connection = 1

    def connect_relay(self):
        address = self.path.split(':', 1)
        address[1] = int(address[1]) or 443
        try:
            s = socket.create_connection(address, timeout=self.timeout)
        except Exception as e:
            self.send_error(502)
            return
        self.send_response(200, 'Connection Established')
        self.end_headers()


        print(f"CONNECT {self.path}")
        if 'Proxy-Connection' in self.headers:
            del self.headers['Proxy-Connection']
        print(self.headers)

        conns = [self.connection, s]
        self.close_connection = 0
        while not self.close_connection:
            rlist, wlist, xlist = select.select(conns, [], conns, self.timeout)
            if xlist or not rlist:
                break
            for r in rlist:
                other = conns[1] if r is conns[0] else conns[0]
                data = r.recv(8192)
                if not data:
                    self.close_connection = 1
                    break
                other.sendall(data)

    def do_GET(self):
        if self.path == 'http://proxy2.test/':
            self.send_cacert(self.cacert)
            return
        elif self.path == 'http://proxy2.test/gsa':
            self.send_cacert('certs/gsa.apple.com.crt')
        elif self.path == 'http://proxy2.test/fmip':
            self.send_cacert('certs/p15-fmip.icloud.com.crt')

        #elif 'captive.apple.com' in self.path:
        #    self.path = 'http://ui.iclouddnsbypass.com/deviceservices/buddy/barney_activation_help_en_us.buddyml'

        req = self
        content_length = int(req.headers.get('Content-Length', 0))
        req_body = self.rfile.read(content_length) if content_length else None

        if req.path[0] == '/':
            if isinstance(self.connection, ssl.SSLSocket):
                req.path = f"https://{req.headers['Host']}{req.path}"
            else:
                req.path = f"http://{req.headers['Host']}{req.path}"

        # rewrite URL path if needed
        req.path = ProxyRewrite.rewrite_path(req.headers, req.path)

        req_body_modified = self.request_handler(req, req_body)
        if req_body_modified is False:
            self.send_error(403)
            return
        elif req_body_modified is not None:
            req_body = req_body_modified
            req.headers['Content-length'] = str(len(req_body))

        u = urlparse.urlsplit(req.path)
        scheme, netloc, path = (
            u.scheme,
            u.netloc,
            f'{u.path}?{u.query}' if u.query else u.path,
        )
        assert scheme in ('http', 'https')
        if netloc:
            if ':' in netloc: netloc = netloc.split(':')[0]
            req.headers['Host'] = netloc

        setattr(req, 'headers', self.filter_headers(req.headers))

        # fix for \r\n being replaced with \n when updating a header field
        for index in range(len(req.headers.headers)):
            if "\r" not in req.headers.headers[index]: req.headers.headers[index] = req.headers.headers[index].replace("\n", "\r\n")

        try:
            origin = (scheme, netloc)
            if origin not in self.tls.conns:
                if scheme == 'https':
                    self.tls.conns[origin] = httplib.HTTPSConnection(netloc, timeout=self.timeout)
                else:
                    self.tls.conns[origin] = httplib.HTTPConnection(netloc, timeout=self.timeout)
            conn = self.tls.conns[origin]
            conn.request(self.command, path, req_body, dict(req.headers))
            res = conn.getresponse()

            version_table = {10: 'HTTP/1.0', 11: 'HTTP/1.1'}
            setattr(res, 'headers', res.msg)
            # sets response_version *FIXME* check if this value is None, if so then do not send
            setattr(res, 'response_version', version_table[res.version])

            if 'albert.apple.com' in self.path:
                res.headers['Content-Length'] = str(0)

            # support streaming
            if (
                'Content-Length' not in res.headers
                and res.headers.get('Cache-Control')
                and 'no-store' in res.headers.get('Cache-Control')
            ):
                self.response_handler(req, req_body, res, '')
                setattr(res, 'headers', self.filter_headers(res.headers))
                self.relay_streaming(res)
                with self.lock:
                    self.save_handler(req, req_body, res, '')
                return

            res_body = res.read()
        except Exception as e:
            self.log_error("do_GET() Exception: %r", e)
            if origin in self.tls.conns:
                del self.tls.conns[origin]
                #self.send_error(502)
            return

        content_encoding = res.headers.get('Content-Encoding', 'identity')
        res_body_plain = self.decode_content_body(res_body, content_encoding)

        res_body_modified = self.response_handler(req, req_body, res, res_body_plain)
        if res_body_modified is False:
            self.send_error(403)
            return
        elif res_body_modified is not None:
            res_body_plain = res_body_modified
            res_body = self.encode_content_body(res_body_plain, content_encoding)
            res.headers['Content-Length'] = str(len(res_body))

        setattr(res, 'headers', self.filter_headers(res.headers))

        self.wfile.write("%s %d %s\r\n" % (self.protocol_version, res.status, res.reason))
        for line in res.headers.headers:
            self.wfile.write(line)
        self.end_headers()
        if res_body != None: self.wfile.write(bytes(res_body))
        self.wfile.flush()

        with self.lock:
            self.save_handler(req, req_body, res, res_body_plain)

    def relay_streaming(self, res):
        self.wfile.write("%s %d %s\r\n" % (self.protocol_version, res.status, res.reason))
        for line in res.headers.headers:
            self.wfile.write(line)
        self.end_headers()
        try:
            while True:
                if chunk := res.read(8192):
                    self.wfile.write(chunk)
                else:
                    break
            self.wfile.flush()
        except socket.error:
            # connection closed by client
            pass

    do_HEAD = do_GET
    do_POST = do_GET

    # handle all weird http requests used by apple servers
    do_PUT = do_GET
    do_DELETE = do_GET
    do_OPTIONS = do_GET
    do_MKCOL = do_GET
    do_MOVE = do_GET
    do_REPORT = do_GET
    do_PROPFIND = do_GET
    do_PROPPATCH = do_GET
    do_ORDERPATCH = do_GET

    def filter_headers(self, headers):
        # http://tools.ietf.org/html/rfc2616#section-13.5.1
        hop_by_hop = ('connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade', 'Proxy-Connection')
        for k in hop_by_hop:
            del headers[k]

        # accept only supported encodings
        if 'Accept-Encoding' in headers:
            ae = headers['Accept-Encoding']
            filtered_encodings = [x for x in re.split(r',\s*', ae) if x in ('identity', 'gzip', 'x-gzip', 'deflate')]
            # FIX for 'None' appearing on the line after Accept-Encoding
            headers['Accept-Encoding'] = ', '.join(filtered_encodings)

        return headers

    def encode_content_body(self, text, encoding):
        if encoding == 'identity':
            data = text
        elif encoding in ('gzip', 'x-gzip', 'x-compress'):
            io = StringIO()
            with gzip.GzipFile(fileobj=io, mode='wb') as f:
                f.write(text)
            data = io.getvalue()
        elif encoding == 'deflate':
            data = zlib.compress(text)
        else:
            raise Exception(f"Unknown Content-Encoding: {encoding}")
        return data

    def decode_content_body(self, data, encoding):
        if encoding == 'identity':
            text = data
        elif encoding in ('gzip', 'x-gzip', 'x-compress'):
            try:
                io = StringIO(data)
                with gzip.GzipFile(fileobj=io) as f:
                    text = f.read()
            except IOError:
                return data
        elif encoding == 'deflate':
            try:
                text = zlib.decompress(data)
            except zlib.error:
                text = zlib.decompress(data, -zlib.MAX_WBITS)
        else:
            raise Exception(f"Unknown Content-Encoding: {encoding}")
        return text

    def send_cacert(self, path):
        with open(path, 'rb') as f:
            data = f.read()

        self.wfile.write("%s %d %s\r\n" % (self.protocol_version, 200, 'OK'))
        self.send_header('Content-Type', 'application/x-x509-ca-cert')
        self.send_header('Content-Length', len(data))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)

    def print_info(self, req, req_body, res, res_body):
        def parse_qsl(s):
            return '\n'.join("%-20s %s" % (k, v) for k, v in urlparse.parse_qsl(s, keep_blank_values=True))

        req_header_text = "%s %s %s\n%s" % (req.command, req.path, req.request_version, req.headers)
        res_header_text = "%s %d %s\n%s" % (res.response_version, res.status, res.reason, res.headers)

        print with_color(33, req_header_text)

        u = urlparse.urlsplit(req.path)
        if u.query:
            query_text = parse_qsl(u.query)
            print with_color(32, "==== QUERY PARAMETERS ====\n%s\n" % query_text)

        cookie = req.headers.get('Cookie', '')
        if cookie:
            cookie = parse_qsl(re.sub(r';\s*', '&', cookie))
            print with_color(32, "==== COOKIE ====\n%s\n" % cookie)

        auth = req.headers.get('Authorization', '')
        if auth.lower().startswith('basic'):
            token = auth.split()[1].decode('base64')
            print with_color(31, "==== BASIC AUTH ====\n%s\n" % token)

        if req_body is not None:
            req_body_text = None
            content_type = req.headers.get('Content-Type', '')

            if content_type.startswith('application/x-www-form-urlencoded'):
                #if 'User-Agent' in req.headers and req.headers['User-Agent'].startswith("locationd"):
                #    req_body_text = ProxyRewrite.locationdDecode(req_body)
                req_body_text = parse_qsl(req_body)
            elif content_type.startswith('application/json'):
                try:
                    json_obj = json.loads(req_body)
                    json_str = json.dumps(json_obj, indent=2)
                    if json_str.count('\n') < 50 or req.path.endswith('fmip.icloud.com') or req.path.endswith('fmf.icloud.com') or req.path.endswith('fmipmobile.icloud.com'):
                        req_body_text = json_str
                    else:
                        lines = json_str.splitlines()
                        req_body_text = "%s\n(%d lines)" % ('\n'.join(lines[:50]), len(lines))
                except ValueError:
                    req_body_text = req_body
            elif len(req_body) < 1024:
                req_body_text = req_body

            if req_body_text:
                print with_color(32, "==== REQUEST BODY ====\n%s\n" % req_body_text)

        print with_color(36, res_header_text)

        cookies = res.headers.getheaders('Set-Cookie')
        if cookies:
            cookies = '\n'.join(cookies)
            print with_color(31, "==== SET-COOKIE ====\n%s\n" % cookies)

        if res_body is not None:
            res_body_text = None
            content_type = res.headers.get('Content-Type', '')

            if content_type.startswith('application/json'):
                try:
                    json_obj = json.loads(res_body)
                    json_str = json.dumps(json_obj, indent=2)
                    if json_str.count('\n') < 50:
                        res_body_text = json_str
                    else:
                        lines = json_str.splitlines()
                        res_body_text = "%s\n(%d lines)" % ('\n'.join(lines[:50]), len(lines))
                except ValueError:
                    res_body_text = res_body
            elif content_type.startswith('text/html'):
                m = re.search(r'<title[^>]*>\s*([^<]+?)\s*</title>', res_body, re.I)
                if m:
                    h = HTMLParser()
                    print with_color(32, "==== HTML TITLE ====\n%s\n" % h.unescape(m.group(1).decode('utf-8')))
            elif content_type.startswith('text/') and len(res_body) < 1024:
                res_body_text = res_body

            if res_body_text:
                print with_color(32, "==== RESPONSE BODY ====\n%s\n" % res_body_text)

    def request_handler(self, req, req_body):
        if ProxyRewrite.rewriteDevice == False: return req_body
        # can probably modify headers here:
        req.headers = ProxyRewrite.rewrite_headers(req.headers, req.path)
        # rewrite URL path if needed
        req.path = ProxyRewrite.rewrite_path(req.headers, req.path)
        hostname = ProxyRewrite.get_hostname(req.headers, req.path)

        # should be able to safely modify body here:
        req_body_plain = req_body
        if (
            'Content-Encoding' in req.headers
            and req.headers['Content-Encoding'] == 'gzip'
            and 'Content-Length' in req.headers
            and req.headers['Content-Length'] > 0
            and str(req_body) != ""
        ):
            content_encoding = req.headers.get('Content-Encoding', 'identity')
            req_body_plain = self.decode_content_body(str(req_body), content_encoding)

        #if 'albert.apple.com' in req.path and 'deviceservices/deviceActivation' in req.path:
        #     req_body_plain = ProxyRewrite.rewrite_plist_body_activation_new(req.headers, req_body_plain)
        #elif 'static.ips.apple.com' in req.path:
        #        req.path = 'http://ui.iclouddnsbypass.com/deviceservices/buddy/barney_activation_help_en_us.buddyml'
        #        req.headers['Host'] = 'ui.icloudbypass.com'

        req_body_modified = ProxyRewrite.rewrite_body(req_body_plain, req.headers, req.path)

        if 'Host' in req.headers and 'albert.apple.com' in req.headers['Host'] and 'drmHandshake' in self.path:
            bodypl = plistlib.readPlistFromString(req_body_modified)
            with open(ProxyRewrite.log_filename(f"fdr_{binascii.hexlify(bodypl['HandshakeRequestMessage'].data)}.bin"), "wb") as f: f.write(bodypl['FDRBlob'].data)
        # *TODO* implement protobuf decoder here
        if (
            req_body_modified != req_body_plain
            and 'Content-Encoding' in req.headers
            and req.headers['Content-Encoding'] == 'gzip'
            and 'Content-Length' in req.headers
            and req.headers['Content-Length'] > 0
            and str(req_body_modified) != ""
        ):
            content_encoding = req.headers.get('Content-Encoding', 'identity')
            req_body_modified = self.encode_content_body(str(req_body_modified), content_encoding)

        elif 'gs-loc.apple.com' in hostname or 'gsp-ssl.ls.apple.com' in hostname or 'gsp64-ssl.ls.apple.com' in hostname or 'gsp10-ssl.apple.com' in hostname:
            ProxyRewrite.locationdDecode2(req_body_modified)
        #elif 'identity.apple.com' in hostname:
        #    import xml2dict
        #    print(xml2dict.parse(req_body_modified))
        return req_body_modified

    def response_handler(self, req, req_body, res, res_body):
        if ProxyRewrite.rewriteDevice == False: return res_body
        hostname = ProxyRewrite.get_hostname(req.headers, req.path)

        if 'setup.icloud.com' in hostname and 'configurations/init?context=buddy' in self.path:
            p = plistlib.readPlistFromString(res_body)
            #p['setupAssistantServerEnabled'] = False
            #p['doQualification'] = True
            #if 'setupAssistantServerEnabled' in p: print(p['setupAssistantServerEnabled'])
            #res_body = plistlib.writePlistToString(p)
            #res.headers['Content-Length'] = str(len(res_body))
            return res_body
        elif ProxyRewrite.file_logging and 'static.ips.apple.com' in hostname and 'absinthe-cert/certificate.cer' in self.path:
            with open(ProxyRewrite.log_filename("certificate.cer"), "w") as f: f.write(ssl.DER_cert_to_PEM_cert(res_body))
        elif 'escrowproxy.icloud.com' in hostname and self.path.endswith("escrowproxy/api/get_records"):
            ProxyRewrite.decode_escrowproxy_record(res_body)
        elif ProxyRewrite.use_rewrite_pubkey and 'setup.icloud.com' in hostname and self.path.endswith("setup/qualify/cert?ver=P1.10.1"):
            res_body = ProxyRewrite.rewrite_cert_pubkey_data(res_body)
            #if 'Host' in req.headers and 'albert.apple.com' in req.headers['Host'] and 'drmHandshake' in self.path:
            #res_body='<xmlui><page><navigationBar title="Verification Failed" hidesBackButton="false"/><tableView><section footer="Please retry activation."/><section><buttonRow align="center" label="Try Again" name="tryAgain"/></section></tableView></page></xmlui>'
            #res.headers['Content-Length'] = str(len(res_body))
            #res.headers['Content-Type'] = 'application/x-buddyml'
            #print("replaced response for %s" % req.headers['Host'])
            #return res_body
        #elif 'Host' in req.headers and ('init-p01st.push.apple.com' in req.headers['Host'] or 'init-p01md.push.apple.com' in req.headers['Host']):
            #res_body = ProxyRewrite.rewrite_init_keybag(res_body, req.headers['Host'], self.certdir, self.certKey, self.issuerCert, self.issuerKey)
			#elif 'Host' in req.headers and 'init.ess.apple.com' in req.headers['Host']:
            # handle setting certs so we can intercept profile.ess.apple.com
            #p = plistlib.readPlistFromString(res_body)
            #print("Certs for %s" % req.headers['Host'])
            #print(p['certs'][0])
            #print(p['certs'][1])

        #    if os.path.isfile("certs/init-p01st.push.apple.com.crt"):
        #        st_cert=open("certs/init-p01st.push.apple.com.crt", 'rt').read()
        #        p['certs'][0] = ssl.PEM_cert_to_DER_cert(st_cert)

        #if 'captive.apple.com' in req.path:
        #    if 'hotspot-detect.html' in req.path:
        #        r = requests.get('http://ui.iclouddnsbypass.com/deviceservices/buddy/barney_activation_help_en_us.buddyml')
        #        res_body = r.text
        #        res.headers['Content-Length'] = str(len(r.text))
        # rewrite response status
        #res = ProxyRewrite.rewrite_status(req.path, res)
        #if 'setup.icloud.com/setup/get_account_settings' in self.path:
        #elif 'Host' in req.headers and 'static.ips.apple.com' in req.headers['Host']:
        #    #res_body = open('./barney_activation_help_en_us.buddyml', 'rt').read()
        #    #res.headers['Content-Length'] = str(len(res_body))        
        #    r = requests.get('http://ui.iclouddnsbypass.com/deviceservices/buddy/barney_activation_help_en_us.buddyml')
        #    res_body = r.text
        #    res.headers['Content-Length'] = str(len(r.text))

        return res_body

    def save_handler(self, req, req_body, res, res_body):
        headers_only = False
        if ProxyRewrite.file_logging == False: return
        hostname = ProxyRewrite.get_hostname(req.headers, req.path)

        if 'icloud.com' in hostname or 'apple.com' in hostname:
            req_body_plain = req_body
            if 'Content-Encoding' in req.headers and req.headers['Content-Encoding'] == 'gzip' and 'Content-Length' in req.headers and req.headers['Content-Length'] > 0 and len(str(req_body)) > 0:
                content_encoding = req.headers.get('Content-Encoding', 'identity')
                req_body_plain = self.decode_content_body(str(req_body), content_encoding)
            # ignore saving binary data we don't care about, also don't save bookmarks because the logfile will continuously group
            if self.path.endswith(".png") or self.path.endswith(".jpeg") or self.path.endswith(".gz") or self.path.endswith(".zip") or self.path.endswith(".xz"): headers_only = True
            if 'setup.icloud.com/setup/qualify/cert' in self.path: headers_only = True
            elif 'setup.icloud.com/setup/account/getPhoto' in self.path or 'setup.icloud.com/setup/family/getMemberPhoto' in self.path: 
                headers_only = True
            elif 'bookmarks.icloud.com' in hostname: headers_only = True
            elif 'ckdatabase.icloud.com' in req.path or 'ckdevice.icloud.com' in req.path or 'caldav.icloud.com' in req.path: headers_only = True
            elif 'keyvalueservice.icloud.com' in req.path: headers_only = True
            elif 'appldnld.apple.com' in req.path: headers_only = True

            #for index in range(len(req.headers.headers)):
            #    print(req.headers.headers[index])
            #    #result = re.match("(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})", req.headers.headers[index])
            #    #if result:
            #    #    result = result.group(0)
            #    #    print(result)
            #    #    req.headers.headers[index].replace(result, result + " (base64)")

            if headers_only == True:
                req_header_text = "%s %s %s" % (req.command, req.path, req.request_version)
                res_header_text = "%s %d %s\n" % (res.response_version, res.status, res.reason)
                print with_color(33, req_header_text)
                print with_color(32, res_header_text)
            else:
                self.print_info(req, req_body_plain, res, res_body)

            logname = hostname
            # remove 'pXX-' from hostname for log filename
            if 'icloud.com' in hostname: logname = re.sub(r'^p\d\d-', '', hostname)

            if ProxyRewrite.unique_log_dir:
                logdir = ProxyRewrite.log_filename('')
            else:
                logdir = "logs"

            if os.path.exists(logdir) == False:
                os.mkdir(logdir)

            urllogger = open("%s/urls.log" % logdir, "ab")
            urllogger.write(str(self.command+' '+self.path+"\n"))
            urllogger.close()

            errlogger = open("%s/errors.log" % logdir, "ab")
            if res.status == 404 or res.status == 400 or res.status == 424 or res.status == 500 or res.status == 502:
                errlogger.write(str(self.command+' '+self.path+"\n"))
                errlogger.write(str(req.headers))
                if req_body: errlogger.write(str(req_body))
                errlogger.write(str("\r\n%s %d %s\r\n" % (self.protocol_version, res.status, res.reason)))
                errlogger.write(str(res.headers))
                errlogger.write(str(res_body))
                errlogger.write(str("\n"))

            if ProxyRewrite.split_logs:
                if self.path.startswith("https"): path = self.path.replace("https://", "")
                elif self.path.startswith("http"): path = self.path.replace("http://", "")
                if 'icloud.com' in path: path = re.sub(r'^p\d\d-', '', path)
                logdir = ("%s/%s" % (logdir, os.path.dirname(path)))
                parts = logdir.split("/")
                fullpath = parts[0]
                for dirname in parts[1:]:
                    fullpath = ("%s/%s" % (fullpath, dirname))
                    if os.path.exists(fullpath) == False: os.mkdir(fullpath)
                path, logname = os.path.split(self.path)
                if '?' in logname: logname = logname.split('?')[0]
                print("%s %s" % (logdir, logname))

            path = ("%s/%s.log" % (logdir, logname))
            if logname == '': path = ("%s.log" % logdir)
            logger = open(path, "ab")
            logger.write(str(self.command+' '+self.path+"\n"))
            logger.write(str(req.headers))

            if headers_only == False and ProxyRewrite.singlelogfile:
                ProxyRewrite.logger.write(str(self.command+' '+self.path+"\n"))
                ProxyRewrite.logger.write(str(req.headers))

            # format json request before writing to log file
            if req_body and 'Content-Type' in req.headers and req.headers['Content-Type'].startswith('application/json'):
                req_body_orig = req_body
                try:
                    json_obj = json.loads(req_body)
                    req_body = json.dumps(json_obj, indent=2)
                except ValueError:
                    req_body = req_body_orig

            if headers_only == False and req_body:
                logger.write(str(req_body))
                if ProxyRewrite.singlelogfile: ProxyRewrite.logger.write(str(req_body))

            logger.write("\r\n%s %d %s\r\n" % (self.protocol_version, res.status, res.reason))
            logger.write(str(res.headers))

            if ProxyRewrite.singlelogfile:
                ProxyRewrite.logger.write(str("\r\n%s %d %s\r\n" % (self.protocol_version, res.status, res.reason)))
                ProxyRewrite.logger.write(str(res.headers))

            # format json response before writing to log file
            if res_body and 'Content-Type' in res.headers and res.headers['Content-Type'].startswith('application/json'):
                res_body_orig = res_body
                try:
                    json_obj = json.loads(res_body)
                    res_body = json.dumps(json_obj, indent=2)
                except ValueError:
                    res_body = res_body_orig

            if headers_only == False and res_body:
                logger.write(str(res_body))
                if ProxyRewrite.singlelogfile: ProxyRewrite.logger.write(str(res_body))

            if headers_only == False and ProxyRewrite.singlelogfile: ProxyRewrite.logger.write(str("\n"))
            logger.write(str("\n"))
            logger.close()


def run_http_server(HandlerClass=ProxyRequestHandler, ServerClass=ThreadingHTTPServer, protocol="HTTP/1.1"):
    try:
        ssl._https_verify_certificates(enable=False)
        HandlerClass.protocol_version = protocol
        httpd = ServerClass(ProxyRewrite.server_address, HandlerClass)
        httpd.allow_reuse_address = True
        httpd.request_queue_size = 256

        #ProxyRewrite.logger = open("rewrite_%s_%s.log" % (device1, device2), "w")

        sa = httpd.socket.getsockname()
        print "Serving HTTP Proxy on", sa[0], "port", sa[1], "..."
        httpd.serve_forever()
    except KeyboardInterrupt:
        print '^C received, shutting down proxy'
        httpd.socket.close()


def test(HandlerClass=ProxyRequestHandler, ServerClass=ThreadingHTTPServer, protocol="HTTP/1.1"):
    config = ConfigParser.ConfigParser()
    config.read('proxy2.cfg')

    if sys.argv[2:]:
        device1 = sys.argv[1]
        device2 = sys.argv[2]
    elif config.has_option('proxy2', 'device1') and config.has_option('proxy2', 'device2'):
        device1 = config.get('proxy2', 'device1')
        device2 = config.get('proxy2', 'device2')
    else:
        print("Usage: %s <device1> <device2>" % sys.argv[0])
        return 0

    if device1 != 'none' and device2 != 'none':
        print("Proxy set to rewrite device %s with device %s" % (device1, device2))
        ProxyRewrite.dev1info = ProxyRewrite.load_device_info(device1)
        ProxyRewrite.dev2info = ProxyRewrite.load_device_info(device2)
    else:
        ProxyRewrite.dev1info = None
        ProxyRewrite.dev2info = None

    port = config.getint('proxy2', 'port')
    if config.has_option('proxy2', 'interface'): ProxyRewrite.interface = config.get('proxy2', 'interface')
    ProxyRewrite.transparent = config.getboolean('proxy2', 'transparent')
    if config.has_option('proxy2', 'apnproxy'): ProxyRewrite.apnproxy = config.getboolean('proxy2', 'apnproxy')
    if config.has_option('proxy2', 'apnproxyssl'): ProxyRewrite.apnproxyssl = config.getboolean('proxy2', 'apnproxyssl')
    if config.has_option('proxy2', 'usejbca'): ProxyRewrite.usejbca = config.getboolean('proxy2', 'usejbca')
    if config.has_option('proxy2', 'file_logging'): ProxyRewrite.file_logging = config.getboolean('proxy2', 'file_logging')
    if config.has_option('proxy2', 'unique_log_dir'): ProxyRewrite.unique_log_dir = config.getboolean('proxy2', 'unique_log_dir')
    if config.has_option('proxy2', 'split_logs'): ProxyRewrite.split_logs = config.getboolean('proxy2', 'split_logs')
    if config.has_option('proxy2', 'use_rewrite_pubkey'): ProxyRewrite.use_rewrite_pubkey = config.getboolean('proxy2', 'use_rewrite_pubkey')
    if config.has_option('proxy2', 'remove_certs'): ProxyRewrite.remove_certs = config.getboolean('proxy2', 'remove_certs')
    ProxyRewrite.changeClientID = config.getboolean('proxy2', 'change_clientid')
    ProxyRewrite.changeBackupDeviceUUID = config.getboolean('proxy2', 'change_backupdeviceuuid')
    ProxyRewrite.rewriteOSVersion = config.getboolean('proxy2', 'rewrite_osversion')
    ProxyRewrite.rewriteDevice = config.getboolean('proxy2', 'rewrite_device')
    ProxyRewrite.jailbroken = config.getboolean('proxy2', 'jailbroken')
    ProxyRewrite.singlelogfile = config.getboolean('proxy2', 'singlelogfile')


    if ProxyRewrite.remove_certs:
        print("Removing old certs")
        for filename in os.listdir("./certs"):
            file_path = os.path.join("./certs", filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)

    logdir = ProxyRewrite.log_filename('')
    if ProxyRewrite.file_logging and ProxyRewrite.unique_log_dir and os.path.exists(logdir) == False:
        os.mkdir(logdir)
    else:
        print("%s already exists, using for logs" % logdir)

    if config.has_option('proxy2', 'ProductVersion'):
        ProxyRewrite.dev2info['ProductVersion'] = config.get('proxy2', 'ProductVersion')
    if config.has_option('proxy2', 'BuildVersion'):
        ProxyRewrite.dev2info['BuildVersion'] = config.get('proxy2', 'BuildVersion')

    if ProxyRewrite.rewriteDevice == False:
        print("Disabled Device Rewrite")
    elif ProxyRewrite.rewriteOSVersion == False:
        print("Disabled iOS version rewrite")

    if ProxyRewrite.transparent == True:
        print("Setting transparent mode")

    if ProxyRewrite.changeClientID == True:
        if config.has_option('proxy2', 'clientid') == False:
            ProxyRewrite.dev2info['client-id'] = ProxyRewrite.generate_new_clientid()
            config.set('proxy2', 'clientid', ProxyRewrite.dev2info['client-id'])
            print("Generated new client-id %s for device %s" % (ProxyRewrite.dev2info['client-id'], ProxyRewrite.dev2info['SerialNumber']))
            with open('proxy2.cfg', 'wb') as configfile:
                 config.write(configfile)
        else:
            ProxyRewrite.dev2info['client-id'] = config.get('proxy2', 'clientid')
            print("Retrieved new client-id %s for device %s from proxy2.cfg" % (ProxyRewrite.dev2info['client-id'], ProxyRewrite.dev2info['SerialNumber']))

    iflist = netifaces.interfaces()
    ProxyRewrite.server_address = ('', port)

    if ProxyRewrite.interface != None:
        print("Setting interface to %s" % (ProxyRewrite.interface))
        ProxyRewrite.server_address = (get_ip_address(ProxyRewrite.interface), port)
    elif 'ap1' in iflist: ProxyRewrite.server_address = (get_ip_address('ap1'), port)
    elif 'ap0' in iflist: ProxyRewrite.server_address = (get_ip_address('ap0'), port)
    elif 'ppp0' in iflist: ProxyRewrite.server_address = (get_ip_address('ppp0'), port)
    elif 'wlxe0b94db08046' in iflist: ProxyRewrite.server_address = (get_ip_address('wlxe0b94db08046'), port)
    elif 'wlp61s0' in iflist: ProxyRewrite.server_address = (get_ip_address('wlp61s0'), port)
    elif 'wlo1' in iflist: ProxyRewrite.server_address = (get_ip_address('wlo1'), port)

    os.putenv('LANG', 'en_US.UTF-8')
    os.putenv('LC_ALL', 'en_US.UTF-8')

    # ugly hack due to python issue5853 (for threaded use)
    try:
        import mimetypes
        mimetypes.init()
    except UnicodeDecodeError:
        # Python 2.x's mimetypes module attempts to decode strings
        sys.argv # unwrap demand-loader so that reload() works
        reload(sys) # resurrect sys.setdefaultencoding()
        oldenc = sys.getdefaultencoding()
        sys.setdefaultencoding("latin1") # or any full 8-bit encoding
        mimetypes.init()
        sys.setdefaultencoding(oldenc)

    #ssl._https_verify_certificates(enable=False)
    #HandlerClass.protocol_version = protocol
    #httpd = ServerClass(ProxyRewrite.server_address, HandlerClass)
    #httpd.allow_reuse_address = True
    #httpd.request_queue_size = 256

    if ProxyRewrite.singlelogfile:
        ProxyRewrite.logger = open("rewrite_%s_%s.log" % (device1, device2), "w")

    t1 = None
    if ProxyRewrite.apnproxy:
        apsd = ProxyAPNHandler(ProxyRewrite.server_address[0], 8083)
        print "Serving APNS Proxy on", ProxyRewrite.server_address[0], "port", 8083, "..."
        t1 = threading.Thread(target=apsd.main_loop)
        t1.daemon = True
        t1.start()

    run_http_server()
    if t1 != None: t1.join(2)

    if ProxyRewrite.singlelogfile:
        ProxyRewrite.logger.close()
    #print '^C received, shutting down proxy'
    #httpd.socket.close()

if __name__ == '__main__':
    test()
