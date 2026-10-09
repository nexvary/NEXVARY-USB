"""Real Qt page navigation, screenshots and reachability, synthetic hardware.

Run in separate processes per QT_SCALE_FACTOR. No test sends AT to hardware.
"""
import os,sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontMetrics,QFontDatabase
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from nexvary_usim_lab.gui import Workstation
from nexvary_usim_lab.discovery import Inventory,_parse_windows
from nexvary_usim_lab.grouping import group_devices

out=Path(os.environ.get('NEXVARY_UI_OUTPUT','ui-evidence'));out.mkdir(parents=True,exist_ok=True)
scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
app=QApplication([]);ui=Workstation(auto_refresh=False)
assert QFontMetrics(QFont('Noto Sans Arabic')).inFontUcs4(ord('م')), 'Arabic font glyph missing'
assert QFontMetrics(QFont('Noto Sans')).inFontUcs4(ord('N')), 'Latin font glyph missing'
ui.display_inventory(Inventory('NOT_DETECTED',[],[],'لا جهاز متصل في بيئة الاختبار','OK'))
ui.show();app.processEvents();checks=[]
for physical_w,physical_h in [(1024,768),(1280,720),(1366,768),(1920,1080)]:
    ui.setFixedSize(int(physical_w/scale),int(physical_h/scale));app.processEvents()
    for page in ui.pages:
        QTest.mouseClick(ui.nav[page],Qt.LeftButton);app.processEvents()
        assert ui.current_page==page
        scroll=ui.pages[page][0]
        assert scroll.viewport().width()>=280, (physical_w,scale,page,scroll.viewport().width())
        for b in ui.pages[page][1].findChildren(QPushButton):
            assert b.width()>=35 and b.height()>=35,(page,b.text(),b.size())
            scroll.ensureWidgetVisible(b);app.processEvents()
            # Layout or scrollbar makes each control reachable; no cropped control.
            mapped=b.mapTo(scroll.viewport(),b.rect().topLeft())
            assert mapped.y()>=-1 and mapped.y()+b.height()<=scroll.viewport().height()+1,(page,b.text(),mapped,scroll.viewport().size())
        scroll.verticalScrollBar().setValue(0);scroll.horizontalScrollBar().setValue(0);app.processEvents()
        assert (ui.width(),ui.height())==(int(physical_w/scale),int(physical_h/scale)), 'Native window resized by desktop'
        shot=ui.grab()
        assert abs(shot.width()-physical_w)<=2 and abs(shot.height()-physical_h)<=2, 'Physical screenshot dimensions invalid'
        path=out/f'{physical_w}x{physical_h}-scale{scale:g}-{page}-no-hardware.png'
        assert shot.save(str(path))
        checks.append(dict(resolution=f'{physical_w}x{physical_h}',scale=scale,page=page,logical_size=[ui.width(),ui.height()],screenshot=path.name,hardware=False))
# Explicitly marked fixture: one composite modem + a second physical modem.
items=[]
for suffix,com in [('A',7),('B',9)]:
    parent='USB\\VID_12D1&PID_14C9\\SYNTHETIC-'+suffix
    for i,(name,kind) in enumerate([('Huawei K3770 Vodafone','USB'),(f'Vodafone Secondary Modem (COM{com})','Modem'),(f'Vodafone Diagnostics (COM{com-1})','Ports')]):
        items.append(dict(Name=name,Class=kind,Status='OK',InstanceId=parent if i==0 else 'USB\\VID_12D1&PID_14C9&MI_0'+str(i)+'\\SYNTHETIC-'+suffix,Ancestors=[parent]))
ui.setFixedSize(int(1366/scale),int(768/scale));ui.display_inventory(Inventory('COM_AVAILABLE',_parse_windows(json.dumps(items)),[],'محاكاة PnP صريحة — ليست أجهزة متصلة','OK'));ui.show('devices');app.processEvents()
ui.connection_label.setText('اختبار واجهة ببيانات اصطناعية — لا نتائج فحص أجهزة فعلية')
assert len(ui.devices)==2 and len(ui.devices[0].interfaces)==3
assert ui.grab().save(str(out/f'1366x768-scale{scale:g}-devices-synthetic.png'))
# Actual decoded UCS2 fixture displayed in the running UI, explicitly synthetic.
from nexvary_usim_lab.pdu import deliver
from nexvary_usim_lab.gui import rows
payload='مرحبا من NEXVARY'.encode('utf-16-be')
pdu='00000C91020100000000000862109021436500'+f'{len(payload):02X}'+payload.hex()
message=deliver(pdu)
ui.show('sms');rows(ui.sms_table,[('1','********0000','REC READ — محاكاة',message['text'])]);ui.sms_status.setText('اختبار PDU ببيانات اصطناعية — ليست رسالة مستلمة من جهاز فعلي');app.processEvents()
scroll=ui.pages['sms'][0];scroll.ensureWidgetVisible(ui.sms_table);app.processEvents()
assert ui.grab().save(str(out/f'1366x768-scale{scale:g}-sms-pdu-synthetic.png'))
ui.show('network');scroll=ui.pages['network'][0];scroll.ensureWidgetVisible(ui.data_status);app.processEvents()
assert ui.grab().save(str(out/f'1366x768-scale{scale:g}-network-data-controls-no-hardware.png'))
# Foreground offline contract: synthetic credential is masked, never screenshot raw QR.
from nexvary_usim_lab.esim_integration import parse_activation, qr_png, read_qr
from PySide6.QtWidgets import QLineEdit
import tempfile
ui.show('esim');ui.activation_input.setText('LPA:1$example.invalid$SYNTHETIC-SECRET')
assert ui.activation_input.echoMode()==QLineEdit.Password
assert ui.validate_activation() is not None
assert 'SYNTHETIC-SECRET' not in ui.activation_status.text()
with tempfile.TemporaryDirectory() as directory:
    qr_path=Path(directory)/'synthetic.png'
    qr_path.write_bytes(qr_png(parse_activation(ui.activation_input.text())))
    assert read_qr(qr_path).matching_id_present
ui.clear_activation();assert not ui.activation_input.text()
ui.activation_status.setText('اختبار تكامل بصيغة اصطناعية — لا كود حقيقي ولا تفعيل على هاتف')
app.processEvents()
assert ui.grab().save(str(out/f'1366x768-scale{scale:g}-esim-contract-synthetic.png'))
ui.show('devices');app.processEvents()
# Back is exercised through an actual button click, not only direct methods.
QTest.mouseClick(ui.nav['sim'],Qt.LeftButton);app.processEvents();QTest.mouseClick(ui.back_button,Qt.LeftButton);app.processEvents();assert ui.current_page=='devices'
(out/f'layout-checks-scale{scale:g}.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
ui.close();print(f'GUI PASS: {len(checks)} page/resolution checks at scale {scale:g}, synthetic grouping and Back')
