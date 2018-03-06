#!/usr/bin/env python
import socket
import os
import winrm
import base64
import argparse
import sys
import libvirt
import time
import logging

chk_logger = logging.getLogger('install_hck')
chk_logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
fmt = logging.Formatter('%(asctime)s %(levelname)s: [winrm] %(message)s', datefmt='%d/%m/%Y %T')
ch.setFormatter(fmt)
chk_logger.addHandler(ch)

reload(sys)
sys.setdefaultencoding("UTF8")


def rebootvm(client):
    lv = libvirt.open('qemu:///system')
    vm = lv.lookupByName(client)
    chk_logger.error("Rebooting %s" % client)
    vm.destroy()
    vm.create()
    return True


def winrm_port_online(ip, vm_name):
    winrm_port = 5985
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, winrm_port))
            chk_logger.debug("WinRM port on %s is open, proceeding with configuration" % ip)
            # WinRM port is open, continue installing
            break
        except socket.error as e:
            chk_logger.error("WinRM port is closed on %s, rebooting. Error: %s" % (ip, e))
            # If WinRM port is closed, VM is stuck and must reboot
            rebootvm(vm_name)

        s.close()
        # Wait time to reboot before trying again
        time.sleep(180)


def get_ps_enc(file_name):
    with open(file_name, 'r') as f:
        ps = "\n" + f.read()

    enc_ps = base64.b64encode(ps.encode("utf-16-le"))
    return enc_ps


def run_ps(file_name, ip_server, auth, x64):
    file_name = os.path.join(os.path.dirname(__file__), file_name)
    enc_ps = get_ps_enc(file_name)
    s = winrm.Session('http://' + ip_server + ':5985/wsman', auth)
    if x64:
        r = s.run_cmd('%SystemRoot%\\syswow64\\WindowsPowerShell\\v1.0\\powershell.exe', ["-EncodedCommand", "%s" % enc_ps])
    else:
        r = s.run_cmd("powershell", ["-EncodedCommand", "%s" % enc_ps])

    return r.status_code, r.std_out, r.std_err

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='This is a simple WinRM client.')
    parser.add_argument('ip', metavar='<IP address>',
                        help='Server IP address.')
    parser.add_argument('-f', metavar='<powershell file>',
                        required=True,
                        help='the powershell file to send/execute.')
    parser.add_argument('-x64', help='Switch to x64. Default: i386', action='store_true')
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                        action="store_true")
    opts = parser.parse_args()

    print "- Using file " + opts.f + " on server " + opts.ip
    if opts.x64:
        print "- Running 64 bit powershell"
    else:
        print "- Running 32 bit powershell"

    output = run_ps(opts.f, opts.ip, opts.x86)

    if not output[0]:
        print "\n-Status: Script went ok\n"
    else:
        print "\n-Status: Something failed\n"

    if opts.verbose:
        print "-Script Output: \n ----------------------\n" + output[1] + output[2]
