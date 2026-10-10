"""Pinned isolated Windows build adaptation; no installation or certificate actions."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

def patch(root):
    root=Path(root);d=root/'virtualsmartcard/win32/BixVReader'
    ns={'m':'http://schemas.microsoft.com/developer/msbuild/2003'}
    ET.register_namespace('',ns['m'])
    p=d/'BixVReader.vcxproj';tree=ET.parse(p);project=tree.getroot()
    for target in list(project.findall('m:Target',ns)):
        if target.get('Name')=='AutoTestSignUMDF':project.remove(target)
    for item in project.iter():
        if item.text:
            item.text=item.text.replace('$(WindowsSdkDir)Include\\wdf\\umdf\\$(UMDF_VERSION_MAJOR).$(UMDF_VERSION_MINOR)', '$(NexvaryWdkRoot)\\c\\Include\\wdf\\umdf\\1.9')
    for item in project.findall('m:ItemGroup/m:None',ns):
        if item.get('Include') == 'BixVReader.inf': item.set('Include','NEXVARYVirtualSIMReader.inf')
    tree.write(p,encoding='utf-8',xml_declaration=True)
    # The build is a dedicated single loopback reader, not arbitrary INI-selected RPC.
    p=d/'device.cpp';s=p.read_text(encoding='utf-8-sig')
    s=s.replace('GetPrivateProfileInt(L"Driver",L"NumReaders",1,L"BixVReader.ini")','1')
    s=s.replace('GetPrivateProfileInt(section,L"RPC_TYPE",0,L"BixVReader.ini")','2')
    s=s.replace('GetPrivateProfileStringA(sectionA,"VENDOR_NAME","Bix",readers[i]->vendorName,sizeof readers[i]->vendorName,"BixVReader.ini");','strcpy_s(readers[i]->vendorName, sizeof readers[i]->vendorName, "NEXVARY");')
    s=s.replace('GetPrivateProfileStringA(sectionA,"VENDOR_IFD_TYPE","VIRTUAL_CARD_READER",readers[i]->vendorIfdType,sizeof readers[i]->vendorIfdType,"BixVReader.ini");','strcpy_s(readers[i]->vendorIfdType, sizeof readers[i]->vendorIfdType, "Virtual SIM directory reader");')
    p.write_text(s,encoding='utf-8-sig')
    p=d/'VpcdReader.cpp';s=p.read_text(encoding='utf-8-sig')
    s=s.replace('rpcType=2;','rpcType=2;\n\tctx = NULL;\n\tserverThread = NULL;')
    s=s.replace('port=(short) GetPrivateProfileInt(section,L"TCP_PORT",portBase+instance,L"BixVReader.ini");','port=(short) 35963;')
    s=s.replace('if (atr_len > 0) {','if (atr_len == 2 && atr && atr[0] == 0x3B && atr[1] == 0x00 && *ATRsize >= 2) {')
    s=s.replace('} else {\n\t\t\tsignalRemoval();\n\t\t}\n\t}\n\n\treturn r;\n}\n\nvoid VpcdReader::Power', '} else {\n\t\t\tfree(atr);\n\t\t\tsignalRemoval();\n\t\t}\n\t}\n\n\treturn r;\n}\n\nvoid VpcdReader::Power')
    # Card presence is announced only after the expected transport ATR is verified.
    s=s.replace('if (vicc_present((struct vicc_ctx *) ctx) == 1)', 'BYTE atr[2]; DWORD size=sizeof(atr);\n\tif (QueryATR(atr, &size))')
    s=s.replace('cardPresent = true;\n\t\twhile', 'if (!initProtocols()) { signalRemoval(); return; }\n\t\tcardPresent = true;\n\t\tstate = SCARD_SWALLOWED;\n\t\twhile')
    p.write_text(s,encoding='utf-8-sig')
    p=root/'virtualsmartcard/src/vpcd/vpcd.c';s=p.read_text()
    s=s.replace('if (r < 0)\n            return r;', 'if (r <= 0)\n            return -1;',1)
    start=s.index('ssize_t recvall(SOCKET sock, void *buffer, size_t size) {');end=s.index('\nstatic SOCKET opensock',start)
    s=s[:start]+'''ssize_t recvall(SOCKET sock, void *buffer, size_t size) {
    size_t got = 0;
    while (got < size) {
        int n = recv(sock, ((char *)buffer) + got, (int)(size - got), 0);
        if (n <= 0) return -1;
        got += n;
    }
    return (ssize_t)got;
}
''' +s[end:]
    s=s.replace('cur->ai_addrlen) != -1)\n\t\t\tbreak;', '''cur->ai_addrlen) != -1) {
#ifdef _WIN32
            DWORD deadline = 3000;
            if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char *)&deadline, sizeof(deadline)) != 0 ||
                setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char *)&deadline, sizeof(deadline)) != 0) {
                close(sock); sock = INVALID_SOCKET; continue;
            }
#endif
            break;
        }''')
    s=s.replace('\t\tclose(sock);\n\t}\n\nerr:\n\tfreeaddrinfo(res);', '\t\tclose(sock);\n        sock = INVALID_SOCKET;\n\t}\n\nerr:\n\tif (res) freeaddrinfo(res);')
    s=s.replace('if (!vicc_connect(ctx, 0, 0) || vicc_getatr(ctx, &atr) <= 0)\n        return 0;\n\n    free(atr);\n\n    return 1;', 'int present = 0;\n    if (vicc_connect(ctx, 0, 0)) present = vicc_getatr(ctx, &atr) > 0;\n    free(atr);\n    return present;')
    p.write_text(s)
    p=d/'BixVReader.ini';p.write_text(p.read_text().replace('DECIVE_UNIT','DEVICE_UNIT'))
    p=d/'BixVReader.inf';s=p.read_text();s=s.replace('DriverVer= ; is set via stampinf','DriverVer=10/10/2026,0.10.2.1')
    s=s.replace('Virtual Smart Card Architecture','NEXVARY (vsmartcard derivative)').replace('Bix Virtual Smart Card Reader','NEXVARY Virtual SIM Reader (development)')
    s=s.replace('BixVReader','NEXVARYVirtualSIMReader').replace('root\\BixVirtualReader','root\\NEXVARYVirtualSIMReader')
    s=s.replace('A44A2DF4-DCA4-4767-8EC4-86FE611C2EA7','67398A7C-9468-4F55-87BC-918521FA6020')
    # Only x64 was built; never advertise an unbuilt ARM64 payload.
    s=s.replace('Standard,NTamd64,NTARM64','Standard,NTamd64')
    s=s.replace('[Standard.NTARM64]\n%DeviceName%=VReader_Install,root\\NEXVARYVirtualSIMReader\n','')
    (d/'NEXVARYVirtualSIMReader.inf').write_text(s)
    p.unlink()
    for name in ['exports.def','BixVReader.rc','VirtualSCReader.idl']:
        p=d/name;s=p.read_text(encoding='utf-8-sig')
        s=s.replace('BixVReader.dll','NEXVARYVirtualSIMReader.dll').replace('"BixVReader"','"NEXVARYVirtualSIMReader"')
        s=s.replace('A44A2DF4-DCA4-4767-8EC4-86FE611C2EA7','67398A7C-9468-4F55-87BC-918521FA6020')
        p.write_text(s,encoding='utf-8-sig')
    return d
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('source');print(patch(a.parse_args().source))
