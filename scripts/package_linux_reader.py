"""Reproducible headless source runtime; no GPL driver binary bundled."""
import tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
from sys import path
path.insert(0,str(root))
from nexvary_usim_lab import __version__
out=root/'dist';out.mkdir(exist_ok=True)
with tarfile.open(out/f'NEXVARY-Virtual-SIM-Reader-{__version__}-Linux.tar.gz','w:gz') as package:
    for name in ('nexvary_usim_lab','requirements-reader.txt','docs/VIRTUAL-SIM-READER-AR.md','docs/VIRTUAL-SIM-SOURCES.md','docs/VIRTUAL-SIM-COMPATIBILITY.md','docs/RELEASE-0.10.2-AR.md','docs/WINDOWS-PCSC-DEVELOPMENT.md','scripts/linux/reader-preflight.sh','scripts/linux/build-vpcd-reviewed.sh','scripts/check_virtual_pcsc.py','scripts/check_field_pcsc.py','tests/test_virtual_sim.py','licenses'):
        source=root/name
        if source.is_dir():
            for file in sorted(source.rglob('*')):
                if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':package.add(file,arcname=str(file.relative_to(root)))
        else:package.add(source,arcname=name)
print('Headless Linux source runtime packaged; install dependencies and vpcd separately.')
