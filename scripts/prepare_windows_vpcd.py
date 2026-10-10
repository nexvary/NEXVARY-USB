"""Prepare an isolated upstream UMDF1 source tree, never install a driver.

GPL-3.0-or-later upstream remains separate from the NEXVARY EXE. Requires an
appropriate Windows WDK/UMDF1 toolchain to build; no signing key is provided.
"""
import argparse
from pathlib import Path
import subprocess
REV='8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8'

def prepare(path):
    path=Path(path)
    if path.exists():raise ValueError('Choose a fresh isolated source directory.')
    subprocess.run(['git','clone','--no-checkout','https://github.com/frankmorgner/vsmartcard.git',str(path)],check=True)
    subprocess.run(['git','-C',str(path),'checkout','--detach',REV],check=True)
    driver=path/'virtualsmartcard/win32/BixVReader'
    source=driver/'VpcdReader.cpp';text=source.read_text(encoding='utf-8-sig')
    needle='ctx = vicc_init(NULL, port);'
    if text.count(needle)!=1:raise ValueError('Unexpected upstream source; refusing patch.')
    text=text.replace(needle,'ctx = vicc_init("127.0.0.1", port);\n\tif (!ctx) { signalRemoval(); return ERROR_NOT_READY; }')
    source.write_text(text,encoding='utf-8-sig')
    (driver/'BixVReader.ini').write_text('[Driver]\nNumReaders=1\n\n[Reader0]\nRPC_TYPE=2\nVENDOR_NAME=NEXVARY (development source)\nVENDOR_IFD_TYPE=Virtual SIM directory reader\nTCP_PORT=35963\nDECIVE_UNIT=0\n')
    (path/'NEXVARY-DEVELOPMENT-ONLY.txt').write_text('Pinned upstream '+REV+'\nSingle reverse-mode loopback reader, no network listener.\nSource preparation only, not build/signing/installation/PCSC evidence.\nKeep upstream copyright and GPL licenses with derived driver.\nNo test-signing or Secure Boot changes are performed.\n')
    print(driver/'BixVReader.vcxproj')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination');prepare(p.parse_args().destination)
