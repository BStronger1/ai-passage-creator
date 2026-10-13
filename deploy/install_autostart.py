#!/usr/bin/env python3
"""Install one user crontab entry, preserving all existing jobs."""
from pathlib import Path
import subprocess
import shlex
root=Path(__file__).resolve().parents[2]
old=subprocess.run(['crontab','-l'],capture_output=True,text=True)
if old.returncode not in (0,1):
    raise SystemExit('Cannot read user crontab')
if old.returncode==1 and 'no crontab for' not in old.stderr:
    raise SystemExit('Cannot read user crontab')
marker='# yangbin-passage-autostart'
line='@reboot '+shlex.quote(str(root/'runtime/bin/python'))+' '+shlex.quote(str(root/'app/deploy/service.py'))+' start >> '+shlex.quote(str(root/'logs/bootstrap.log'))+' 2>&1 '+marker
if marker not in old.stdout:
    (root/'crontab.before-passage').write_text(old.stdout)
    subprocess.run(['crontab','-'],input=old.stdout.rstrip()+'\n'+line+'\n',text=True,check=True)
    print('Installed application autostart; existing crontab entries preserved.')
else:
    print('Application autostart already installed.')
