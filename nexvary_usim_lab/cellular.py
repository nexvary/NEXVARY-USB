"""Owner-triggered OS-managed data sessions. Never changes unrelated routes/profiles.

Linux NetworkManager/ModemManager owns QMI/MBIM/PPP transport. Windows WWAN
owns MBIM-compatible adapters. Legacy serial Windows devices require an existing
RAS/vendor dialer and are not treated as WWAN devices.
"""
import os
import platform
import re
import shutil
import subprocess
import uuid
from .core import LabError, redact
from .coordination import lease

class CellularManager:
    def __init__(self, system=None, runner=None):
        self.system=system or platform.system();self.runner=runner or subprocess.run
    def _run(self, args, timeout=20):
        name=args[0]
        exe=(os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','netsh.exe')
             if name=='netsh' and self.system=='Windows' else shutil.which(name))
        if not exe:raise LabError('أداة النظام غير متاحة: '+name)
        try:
            result=self.runner([exe]+args[1:],shell=False,capture_output=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired):raise LabError('تعذر إكمال أمر الشبكة ضمن المهلة؛ افحص الحالة قبل إعادة المحاولة.') from None
        if result.returncode:raise LabError('رفضت خدمة الشبكة العملية؛ تحقق من التعريف والصلاحيات والتسجيل وملف الاتصال.')
        raw=result.stdout
        if len(raw)>65536:raise LabError('Network response exceeds limit.')
        return raw.decode('utf-8',errors='replace') if isinstance(raw,bytes) else raw
    def inventory(self):
        if self.system=='Windows':return redact(self._run(['netsh','mbn','show','interfaces']))
        if self.system=='Linux':return redact(self._run(['nmcli','--terse','--fields','DEVICE,TYPE,STATE','device','status']))
        raise LabError('نظام غير مدعوم لاتصال البيانات.')
    def profiles(self, interface):
        self._interface(interface)
        if self.system=='Windows':return redact(self._run(['netsh','mbn','show','profiles','interface='+interface]))
        if self.system=='Linux':return redact(self._run(['nmcli','--terse','--fields','UUID,TYPE,NAME','connection','show']))
        raise LabError('نظام غير مدعوم.')
    def _interface(self,value):
        if not isinstance(value,str) or not 1<=len(value)<=100 or any(ord(c)<32 or c in '"=\x7f' for c in value):raise LabError('اسم واجهة النظام غير صحيح.')
    def change(self,interface,profile=None,connect=True,confirmed=False):
        if not confirmed:raise LabError('تشغيل/إيقاف البيانات يحتاج موافقة صريحة؛ قد تُحتسب رسوم.')
        self._interface(interface)
        with lease('cellular:'+interface):
            if self.system=='Windows':
                if connect:
                    self._interface(profile)
                    self._run(['netsh','mbn','connect','interface='+interface,'connmode=name','name='+profile],60)
                else:self._run(['netsh','mbn','disconnect','interface='+interface],30)
                # Output is localized: don't infer CONNECTED from command success.
                info=self._run(['netsh','mbn','show','connection','interface='+interface])
                return 'نفّذ Windows الطلب. الحالة التالية من النظام؛ نجاح الإنترنت غير مثبت:\n'+redact(info)
            if self.system=='Linux':
                # Reject Wi-Fi/Ethernet and unrelated saved profiles before any mutation.
                kind=self._run(['nmcli','--get-values','GENERAL.TYPE','device','show',interface]).strip()
                if kind!='gsm':raise LabError('الواجهة المختارة ليست مودم بيانات GSM في NetworkManager.')
                if connect:
                    try:
                        if str(uuid.UUID(profile))!=profile:raise ValueError()
                    except (ValueError,TypeError,AttributeError):raise LabError('استخدم UUID لملف اتصال GSM موجود.') from None
                    kind=self._run(['nmcli','--get-values','connection.type','connection','show','uuid',profile]).strip()
                    if kind!='gsm':raise LabError('ملف الاتصال ليس من نوع GSM.')
                    self._run(['nmcli','--wait','55','connection','up','uuid',profile,'ifname',interface],60)
                else:self._run(['nmcli','--wait','25','device','disconnect',interface],30)
                state=self._run(['nmcli','--get-values','GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP6.ADDRESS','device','show',interface])
                return 'نفّذ NetworkManager الطلب؛ افحص العنوان والحالة. لم يُختبر الإنترنت:\n'+redact(state)
            raise LabError('نظام غير مدعوم.')
    def modem_status(self, modem):
        """ModemManager serializes QMI/MBIM operations with data-session ownership."""
        if self.system!='Linux' or not isinstance(modem,str) or not re.fullmatch(r'[0-9]{1,4}',modem):raise LabError('ModemManager يحتاج Linux ورقم مودم صحيحًا.')
        # Key-value output includes identities: only allow selected status fields.
        raw=self._run(['mmcli','--output-keyvalue','--modem',modem])
        allowed=('modem.generic.state','modem.generic.state-failed-reason','modem.generic.access-technologies','modem.generic.signal-quality','modem.3gpp.registration-state')
        return '\n'.join(line for line in raw.splitlines() if line.split(':',1)[0].strip() in allowed)
