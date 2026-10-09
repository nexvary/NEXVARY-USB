"""Run the actual test suite and emit machine-readable platform evidence."""
import json, platform, re, subprocess, sys
from pathlib import Path
out=Path('test-evidence');out.mkdir(exist_ok=True)
result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],capture_output=True,text=True)
log=result.stdout+result.stderr
(out/'unittest.txt').write_text(log,encoding='utf-8')
match=re.search(r'Ran (\d+) tests',log)
(out/'summary.json').write_text(json.dumps(dict(platform=platform.platform(),python=platform.python_version(),
    tests=int(match[1]) if match else None,exit_code=result.returncode,hardware_tested=False,
    evidence='synthetic protocol tests; preserved owner reports are prior observations'),indent=2),encoding='utf-8')
print(log);sys.exit(result.returncode)
