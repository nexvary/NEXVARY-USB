"""Qt desktop workstation: native Arabic shaping, RTL and DPI-aware layouts."""
from __future__ import annotations
import json
import queue
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, QCoreApplication
from PySide6.QtGui import QIcon, QPixmap, QFontDatabase, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QLineEdit, QTextEdit, QCheckBox, QComboBox, QSpinBox, QDialog)
from .core import Report, demo, probe, select_master_file, pcsc_readers, to_json, to_csv, LabError
from .catalog import load_profiles, model_from_text
from .discovery import detect, to_diagnostic_json
from .device_operations import ATSession
from .cellular import CellularManager, RasDataManager
from .pcsc import run as pcsc_run
from .grouping import group_devices, port_role, candidates
from .port_discovery import discover_at, PortPreferences
from .esim_integration import APK_IDENTITY, IntegrationError, parse_activation, qr_png, read_qr, read_recycling_csv
from . import __version__
from .usage_guide import STEPS, GOALS, connection_ok, explain_report

DARK='#050507'; PANEL='#10090D'; FIELD='#141016'; SILVER='#C3CBD3'
BLUE='#39FF14'; GREEN='#39FF14'; GOLD='#FFD176'; RED='#A51036'

ICON_DIR=Path(__file__).resolve().parent.parent/'assets'/'icons'/'oxygen'
ICON_KINDS=('devices','sim','sms','network','reports','about','scan','back','refresh','details')

def load_fonts():
    # Bundle fonts for native Windows, clean/offscreen runners and portable builds.
    directory=Path(__file__).resolve().parent.parent/'assets'/'fonts'
    for path in directory.glob('*.ttf'):
        if QFontDatabase.addApplicationFont(str(path))<0:
            raise RuntimeError('Bundled font failed to load: '+path.name)
    QApplication.instance().setFont(QFont('Noto Sans Arabic',10))

def icon(kind, color=BLUE):
    # Preserve the original full-color artwork; never tint raster icons.
    path=ICON_DIR/((kind if kind in ICON_KINDS else 'about')+'.png')
    result=QIcon(str(path))
    if result.isNull():
        raise RuntimeError('Bundled color icon missing: '+path.name)
    return result

def label(text, role=None, ltr=False):
    w=QLabel(text); w.setWordWrap(True); w.setTextFormat(Qt.PlainText)
    if role:w.setObjectName(role)
    w.setAlignment((Qt.AlignLeft if ltr else Qt.AlignRight)|Qt.AlignAbsolute)
    w.setLayoutDirection(Qt.LeftToRight if ltr else Qt.RightToLeft)
    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return w

def button(text, callback, kind='scan', accent=False):
    b=QPushButton(icon(kind,GOLD if accent else BLUE),text)
    b.setIconSize(QSize(28,28));b.setMinimumHeight(38);b.setCursor(Qt.PointingHandCursor)
    if accent:b.setObjectName('primary')
    b.clicked.connect(lambda _=False:callback())
    return b

def panel():
    w=QFrame();w.setObjectName('panel');v=QVBoxLayout(w);v.setContentsMargins(16,14,16,14);v.setSpacing(10)
    return w,v

def table(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers)
    t.setMinimumHeight(210);t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setAlternatingRowColors(True);t.verticalHeader().hide()
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    for i in range(len(headers)):t.setColumnWidth(i,150 if i<len(headers)-1 else 280)
    return t

def rows(t,data):
    t.setRowCount(len(data))
    for i,row in enumerate(data):
        for j,value in enumerate(row):
            text=str(value)
            display="\u2066"+text+"\u2069" if text.isascii() else text
            item=QTableWidgetItem(display);item.setToolTip(text)
            item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
            t.setItem(i,j,item)
    t.resizeRowsToContents()

STYLE='''
QWidget { background:#050507; color:#ECF1F6; font-family:"Noto Sans Arabic","Noto Sans","Segoe UI"; font-size:13px; }
QFrame#panel { background:#10090D; border:1px solid #83102D; border-radius:12px; }
QFrame#panel QLabel, QFrame#panel QCheckBox { background:transparent; }
QLabel#title { font-size:23px; font-weight:600; color:#F1F5F9; }
QLabel#brand { font-size:25px; font-weight:700; letter-spacing:2px; color:#B5BEC6; }
QLabel#muted { color:#B5BEC6; } QLabel#good { color:#39FF14; } QLabel#gold { color:#E7BE69; }
QPushButton { background:#171016; border:1px solid #6A1831; border-radius:7px; padding:7px 10px; text-align:right; }
QPushButton:hover { border-color:#39FF14; background:#26101A; }
QPushButton:checked { background:#351020; border-color:#39FF14; }
QPushButton#primary { color:#E7BE69; border-color:#39FF14; }
QPushButton:disabled { color:#697985; border-color:#253440; }
QLineEdit,QTextEdit,QComboBox,QSpinBox { background:#0A090D; border:1px solid #71808C; border-radius:5px; padding:8px; selection-background-color:#7D1230; }
QTableWidget { background:#0A090D; alternate-background-color:#1A0C13; gridline-color:#40202B; border:1px solid #83102D; }
QHeaderView::section { background:#30101C; color:#E8DDE2; padding:9px; border:0; }
QScrollArea { border:0; } QScrollBar:vertical { background:#09070B; width:12px; }
QScrollBar::handle:vertical { background:#A51036; min-height:24px; border-radius:5px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QToolTip { color:#ECF1F6; background:#26101A; border:1px solid #71808C; }
QFrame#panel:hover { border-color:#39FF14; }
QPushButton#primary { background:#39FF14; color:#050507; border-color:#39FF14; }
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus { border-color:#39FF14; }
'''

class Workstation(QMainWindow):
    def __init__(self, auto_refresh=True):
        super().__init__()
        load_fonts()
        self.setWindowTitle(f'NEXVARY USB Studio {__version__}')
        self.setWindowIcon(icon('devices',GOLD));self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1180,760);self.setMinimumSize(540,400);self.setStyleSheet(STYLE)
        self.inventory=None;self.devices=[];self.selected=None;self.active_port=None
        self.report=None;self.reports={};self.preferences=PortPreferences()
        self.busy=False;self.current_page='devices';self.history=[];self.jobs=queue.Queue();self.nav={};self.pages={}
        self.guide_stage=0;self.guide_active=False;self._guided_probe=False
        self._compose()
        self.timer=QTimer(self);self.timer.timeout.connect(self._drain);self.timer.start(40)
        if auto_refresh:QTimer.singleShot(0,self.refresh)

    def _compose(self):
        main=QWidget();self.setCentralWidget(main);outer=QVBoxLayout(main);outer.setContentsMargins(14,12,14,10)
        head=QHBoxLayout();self.brand=label('NEXVARY','brand',True);head.addWidget(self.brand)
        head.addStretch();head.addWidget(label(f'USB STUDIO  /  {__version__}','muted',True));outer.addLayout(head)
        self.connection_label=label('اختر جهازًا ثم ابدأ الفحص','muted');outer.addWidget(self.connection_label)
        body=QHBoxLayout();self.side=QWidget();nav=QVBoxLayout(self.side);nav.setContentsMargins(0,0,8,0)
        self.back_button=button('رجوع',self.back,'back');nav.addWidget(self.back_button)
        self.stack=QStackedWidget()
        menu=[('guide','ابدأ خطوة بخطوة','scan'),('devices','الأجهزة','devices'),('sim','معلومات الشريحة','sim'),('sms','الرسائل','sms'),
              ('network','الشبكة والاتصال','network'),('esim','eSIM Manager','sim'),('reports','التقارير','reports'),('about','النظام والتوافق','about')]
        self.nav_titles={k:title for k,title,_ in menu}
        for key,title,kind in menu:
            b=button(title,lambda k=key:self.show(k),kind);b.setCheckable(True);b.setToolTip(title)
            nav.addWidget(b);self.nav[key]=b
            scroll=QScrollArea();scroll.setWidgetResizable(True)
            page=QWidget();page.setMinimumWidth(310);v=QVBoxLayout(page);v.setContentsMargins(4,6,4,10);v.setSpacing(14)
            scroll.setWidget(page);self.stack.addWidget(scroll);self.pages[key]=(scroll,page,v)
        nav.addStretch();self.side.setFixedWidth(195);self.side_scroll=QScrollArea();self.side_scroll.setWidgetResizable(True);self.side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.side_scroll.setWidget(self.side);self.side_scroll.setFixedWidth(211);body.addWidget(self.side_scroll);body.addWidget(self.stack,1);outer.addLayout(body,1)
        self.status_label=label('جاهز — لم تُختبر أجهزة في هذه الجلسة','muted');outer.addWidget(self.status_label)
        for method in (self._build_guide,self._build_devices,self._build_sim,self._build_sms,self._build_network,self._build_esim,self._build_reports,self._build_about):method()
        self.pages['sim'][2].insertWidget(2,label('ابدأ بالفحص الشامل لمعرفة جاهزية الشريحة. قراءة EF-ICCID وفحص التطبيقات اختياريان للمستخدم المتقدم؛ لا يلزم تشغيلهما لقراءة الرسائل.','gold'))
        self.pages['sim'][2].insertWidget(3,button('متابعة مراحل الاستخدام',self._guide_return,'back'))
        self.pages['sms'][2].insertWidget(2,label('1. اضغط قراءة الوارد. 2. للإرسال أدخل الرقم الدولي والنص. 3. راجع الرقم والرسوم في الموافقة. لا تُرسل أي رسالة تلقائيًا.','gold'))
        self.pages['sms'][2].insertWidget(3,button('متابعة مراحل الاستخدام',self._guide_return,'back'))
        self.pages['network'][2].insertWidget(2,label('1. اقرأ حالة الشبكة. 2. اختر ملف اتصال بيانات موجودًا. 3. وافق على التشغيل بعد مراجعة رسوم المشغل. تغيير APN اختياري؛ استخدم القيمة التي يعطيها مشغلك.','gold'))
        self.pages['network'][2].insertWidget(3,button('متابعة مراحل الاستخدام',self._guide_return,'back'))
        self.pages['esim'][2].insertWidget(2,label('1. أدخل كود LPA الخاص بك. 2. اعرض QR وامسحه بالهاتف. 3. أكمل موافقة LPA على الهاتف. نقل الكود لا يعني نجاح التفعيل.','gold'))
        self.pages['esim'][2].insertWidget(3,button('متابعة مراحل الاستخدام',self._guide_return,'back'))
        self.pages['reports'][2].insertWidget(2,label('اختر حفظ JSON أو CSV بعد الفحص. التقرير منقح؛ لا يحفظ نصوص رسائلك. يمكنك إرساله للدعم لفهم الخطأ.','gold'))
        self.pages['reports'][2].insertWidget(3,button('متابعة مراحل الاستخدام',self._guide_return,'back'))
        self.show('guide',remember=False)

    def _build_guide(self):
        v=self._heading('guide','ابدأ خطوة بخطوة','اختر وظيفة واحدة في كل مرة. يمكنك الرجوع للمراحل أو فتح الأقسام المتقدمة في أي وقت.')
        self.guide_progress=label('','gold');v.addWidget(self.guide_progress)
        box,b=panel();self.guide_title=label('','title');b.addWidget(self.guide_title)
        self.guide_help=label('','muted');b.addWidget(self.guide_help)
        self.guide_devices=QComboBox();self.guide_devices.setMinimumHeight(40);b.addWidget(self.guide_devices)
        self.guide_result=label('','good');b.addWidget(self.guide_result)
        self.guide_goals=QComboBox();self.guide_goals.setMinimumHeight(40)
        for title,key,_ in GOALS:self.guide_goals.addItem(title,key)
        self.guide_goals.currentIndexChanged.connect(self._guide_goal_help);b.addWidget(self.guide_goals)
        self.guide_goal_help=label('','muted');b.addWidget(self.guide_goal_help)
        v.addWidget(box)
        self.guide_primary=button('البحث عن الأجهزة',self._guide_next,'scan',True)
        self.guide_previous=button('المرحلة السابقة',self._guide_previous,'back')
        self.guide_resume=button('احفظ التقرير',lambda:self.export_report('json'),'reports')
        v.addWidget(self.guide_primary);v.addWidget(self.guide_previous);v.addWidget(self.guide_resume)
        self.guide_error=label('','muted');v.addWidget(self.guide_error);v.addStretch()
        self._guide_update()

    def _guide_goal_help(self,*_):
        self.guide_goal_help.setText(GOALS[self.guide_goals.currentIndex()][2])

    def _guide_update(self):
        stage=self.guide_stage;title,help_=STEPS[stage]
        self.guide_progress.setText(f'المرحلة {stage+1} من {len(STEPS)}')
        self.guide_title.setText(title);self.guide_help.setText(help_)
        self.guide_devices.setVisible(stage==1)
        self.guide_result.setVisible(stage>=2)
        self.guide_result.setText(explain_report(self.report) if stage>=2 else '')
        self.guide_goals.setVisible(stage==3);self.guide_goal_help.setVisible(stage==3);self._guide_goal_help()
        self.guide_primary.setText(('البحث عن الأجهزة','التالي: فحص الجهاز','بدء الفحص','افتح الوظيفة المختارة','ابدأ مع جهاز آخر')[stage])
        self.guide_primary.setEnabled(not self.busy)
        self.guide_previous.setEnabled(stage>0 and not self.busy)
        self.guide_resume.setVisible(stage==4)

    def _guide_previous(self):
        if self.busy:return
        self.guide_stage=max(0,self.guide_stage-1);self.guide_error.clear();self._guide_update()

    def _guide_next(self):
        if self.busy:return
        self.guide_active=True;self.guide_error.clear()
        if self.guide_stage==0:
            self.refresh();self._guide_update();return
        if self.guide_stage==1:
            key=self.guide_devices.currentData()
            device=next((d for d in self.devices if d.key==key),None)
            if device is None:
                self.guide_error.setText('لا توجد فلاشة مختارة؛ ارجع للبحث بعد توصيل الجهاز.');return
            self._device_action(device,lambda:None)
            # A new guided scan must never advance using a cached report.
            self.report=None;self._populate_readings([]);self.guide_stage=2
        elif self.guide_stage==2:
            if self.selected is None:self.guide_stage=0
            else:
                self._guided_probe=True;self.run_probe();self._guide_update();return
        elif self.guide_stage==3:
            if not connection_ok(self.report):self.guide_stage=2
            else:
                self.guide_stage=4;self._guide_update();self.show(self.guide_goals.currentData());return
        else:
            self.guide_stage=0;self.selected=None;self.active_port=None;self.report=None
            self._populate_readings([]);rows(self.sms_table,[]);rows(self.network_table,[])
            self.card_label.setText('لا نتيجة حالية — اختر الجهاز وافحصه')
            self.connection_label.setText('اختر جهازًا ثم ابدأ الفحص')
        self._guide_update()

    def _guide_return(self):
        self._guide_update();self.show('guide')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'side'):return
        compact=self.width()<850
        self.side.setFixedWidth(62 if compact else 195)
        self.side_scroll.setFixedWidth(78 if compact else 211)
        self.back_button.setText('' if compact else 'رجوع')
        for key,b in self.nav.items():b.setText('' if compact else self.nav_titles[key])

    def _heading(self,key,title,desc):
        v=self.pages[key][2];v.addWidget(label(title,'title'));v.addWidget(label(desc,'muted'));return v
    def _actions(self,v,buttons):
        # Two columns keep every control reachable on low-resolution screens.
        grid=QGridLayout();grid.setSpacing(8)
        for i,(text,fn,kind,accent) in enumerate(buttons):grid.addWidget(button(text,fn,kind,accent),i//2,i%2)
        v.addLayout(grid)
    def show(self,key=None,remember=True):
        if key is None:return super().show()
        if remember and self.current_page!=key:self.history.append(self.current_page)
        self.current_page=key;self.stack.setCurrentWidget(self.pages[key][0])
        for k,b in self.nav.items():b.setChecked(k==key)
        self.back_button.setEnabled(bool(self.history))
    def back(self):
        if self.history:self.show(self.history.pop(),remember=False)

    def _build_devices(self):
        v=self._heading('devices','مركز الفلاشات','بطاقة لكل جهاز مرتبطة بعلاقات Windows PnP؛ تفاصيل الواجهات في الفحص المتقدم.')
        self._actions(v,[('تحديث الأجهزة',self.refresh,'refresh',True)])
        self.detection_label=label('لم يبدأ اكتشاف الأجهزة','muted');v.addWidget(self.detection_label)
        self.cards=QVBoxLayout();v.addLayout(self.cards);v.addStretch()

    def display_inventory(self,data):
        self.inventory=data;self.devices=group_devices(data)
        # Never retain an old COM selection after an unplug or refresh.
        self.selected=None;self.active_port=None;self.report=None
        self.connection_label.setText('اختر بطاقة الجهاز للفحص؛ لن تُرسل أوامر تلقائيًا')
        self._populate_readings([]);rows(self.sms_table,[]);rows(self.network_table,[])
        self.card_label.setText('لا نتيجة حالية — اختر الجهاز وافحصه')
        self.detection_label.setText(f'{len(self.devices)} جهاز/مجموعة • {len(data.devices)} واجهة تقنية • {data.message}')
        self._render_cards()
        self._guided_probe=False;self.guide_stage=0
        self.guide_devices.clear()
        for device in self.devices:self.guide_devices.addItem(device.title,device.key)
        if self.guide_active and self.devices:self.guide_stage=1
        self.guide_error.setText('اختر الفلاشة من القائمة؛ لا تحتاج لاختيار COM.' if self.devices else 'لم يثبت اكتشاف فلاشة. تأكد من التوصيل والتعريف ثم أعد البحث. '+data.message)
        self._guide_update()

    def _render_cards(self):
        while self.cards.count():
            w=self.cards.takeAt(0).widget()
            if w:w.deleteLater()
        if not self.devices:
            box,v=panel();v.addWidget(label('لا توجد فلاشة متصلة','title'))
            v.addWidget(label('وصّل الفلاشة، ثم اضغط تحديث الأجهزة. لا تُعرض بيانات محاكاة تلقائيًا.','muted'));self.cards.addWidget(box)
        for device in self.devices:
            previous=self.reports.get(device.key)
            values={r.name:r.value for r in previous.readings} if previous else {}
            if previous:
                model_reading=next((r for r in previous.readings if r.name=='Model' and r.status=='OK'),None)
                entry=model_from_text(model_reading.value) if model_reading else None
                if entry:device.title=entry.brand+' '+entry.model+(' — Vodafone' if 'Vodafone' in device.title else '')
            box,v=panel();title=QHBoxLayout();logo=QLabel();logo.setPixmap(icon('devices',GOLD).pixmap(38,38));title.addWidget(logo)
            title.addWidget(label(device.title,'title'),1);v.addLayout(title)
            v.addWidget(label('متصل عبر '+(', '.join(p.device for p in device.ports) or 'USB؛ لا يوجد COM مرتبط'),'good'))
            v.addWidget(label(device.driver_status+' • '+device.evidence,'muted'))
            options=candidates(device,self.preferences.get(device.key))
            v.addWidget(label('منفذ AT المرشح: '+(options[0].device+' — يحتاج اختبار AT' if options else 'لا يوجد؛ افتح الفحص المتقدم'),'muted'))
            if previous:v.addWidget(label('آخر فحص في هذه الجلسة: '+previous.timestamp_utc,'muted',True))
            v.addWidget(label('الشريحة: '+values.get('SIM status','لم تُفحص')+'\nFirmware: '+values.get('Firmware','لم يُقرأ')+'\nAPDU: '+values.get('APDU SELECT MF','لم يُفحص')+' • USIM AKA: غير مثبت'))
            self._actions(v,[(name,lambda d=device,f=fn:self._device_action(d,f),kind,accent) for name,fn,kind,accent in (
                ('ابدأ معي خطوة بخطوة',self._guide_start_device,'scan',True),('فحص الجهاز',self.run_probe,'scan',False),('معلومات الشريحة',lambda:self.show('sim'),'sim',False),
                ('الرسائل',lambda:self.show('sms'),'sms',False),('الشبكة والاتصال',lambda:self.show('network'),'network',False),
                ('الفحص المتقدم',self.advanced_details,'details',False),('تقرير الجهاز',lambda:self.show('reports'),'reports',False))])
            self.cards.addWidget(box)

    def _guide_start_device(self):
        self.guide_active=True;self.guide_stage=2;self.report=None;self._populate_readings([])
        self.guide_error.clear();self._guide_update();self.show('guide')

    def _device_action(self,device,fn):
        if self.busy:return
        changed=self.selected is None or self.selected.key!=device.key
        self.selected=device
        if changed:
            self.active_port=None;self.report=self.reports.get(device.key)
            self._populate_readings(self.report.readings if self.report else [])
            rows(self.sms_table,[]);rows(self.network_table,[])
            self.card_label.setText('الشريحة: لم تُفحص' if not self.report else 'نتيجة سابقة لهذا الجهاز في الجلسة')
        self.connection_label.setText(device.title+' • منفذ AT لم يُثبت' if not self.active_port else device.title+' • '+self.active_port)
        fn()

    def _build_sim(self):
        v=self._heading('sim','معلومات الشريحة','حالة SIM وPIN ومعرّف منقح. نجاح SELECT لا يثبت مصادقة USIM AKA.')
        self._actions(v,[('فحص شامل',self.run_probe,'scan',True),('قراءة EF-ICCID',self.check_ef,'sim',False),('اختبار SELECT MF',self.check_apdu,'sim',False),('تطبيقات SIM / USIM',self.check_applications,'sim',False)])
        self.card_label=label('الشريحة لم تُفحص','good');v.addWidget(self.card_label)
        self.sim_table=table(['الفحص','الحالة','النتيجة والتفسير']);v.addWidget(self.sim_table);v.addStretch()

    def _build_sms(self):
        v=self._heading('sms','الرسائل','عرض محلي للرسائل، وإرسال رسالة واحدة بعد تأكيد الرقم والنص. قد تُحتسب رسوم.')
        box,b=panel();b.addWidget(label('رقم الهاتف الدولي'))
        self.number_input=QLineEdit();self.number_input.setLayoutDirection(Qt.LeftToRight);self.number_input.setPlaceholderText('+201xxxxxxxxx');b.addWidget(self.number_input)
        b.addWidget(label('نص الرسالة'));self.sms_input=QTextEdit();self.sms_input.setFixedHeight(110);b.addWidget(self.sms_input)
        self.ucs2=QCheckBox('UCS2 عربي — تجريبي، لم يُثبت على المودم');b.addWidget(self.ucs2)
        self._actions(b,[('إرسال بموافقتي',self.send_sms,'sms',True),('قراءة PDU المستلمة',self.read_sms,'sms',False),('قراءة Text القديمة',self.read_text_sms,'sms',False)])
        self.sms_status=label('محتوى الرسائل لا يدخل تقارير التشخيص','muted');b.addWidget(self.sms_status);v.addWidget(box)
        self.sms_table=table(['رقم','المرسل المنقح','الحالة','معاينة محلية']);v.addWidget(self.sms_table)
        v.addWidget(label('قراءة PDU: UCS2 العربي وGSM7؛ الأجزاء المتعددة تُعرض منفصلة. دعم المودم يحتاج اختبارًا فعليًا.','muted'));v.addStretch()

    def _build_network(self):
        v=self._heading('network','الشبكة والاتصال','الإشارة والتسجيل والمشغل وAPN. لا يُشغّل البرنامج اتصال بيانات تلقائيًا.')
        self._actions(v,[('قراءة حالة الشبكة',self.read_network,'network',True)])
        self.network_table=table(['الفحص','الحالة','النتيجة']);v.addWidget(self.network_table)
        box,b=panel();b.addWidget(label('تعديل APN لسياق غير نشط فقط','gold'))
        self.cid=QSpinBox();self.cid.setRange(1,16);self.cid.setPrefix('CID ');self.cid.setLayoutDirection(Qt.LeftToRight);b.addWidget(self.cid)
        self.apn=QLineEdit();self.apn.setPlaceholderText('internet');self.apn.setLayoutDirection(Qt.LeftToRight);b.addWidget(self.apn)
        b.addWidget(button('حفظ APN بموافقتي',self.set_apn,'network'));v.addWidget(box)
        box,b=panel();b.addWidget(label('اتصال البيانات عبر خدمة النظام — قد تُحتسب رسوم','gold'))
        self.data_backend=QComboBox();self.data_backend.addItems(['WWAN / NetworkManager','Windows RAS — مودم COM قديم']);b.addWidget(self.data_backend)
        self.data_interface=QLineEdit();self.data_interface.setLayoutDirection(Qt.LeftToRight);self.data_interface.setPlaceholderText('واجهة WWAN في Windows أو جهاز GSM في Linux');b.addWidget(self.data_interface)
        self.data_profile=QLineEdit();self.data_profile.setLayoutDirection(Qt.LeftToRight);self.data_profile.setPlaceholderText('اسم ملف Windows أو UUID ملف GSM في Linux');b.addWidget(self.data_profile)
        self._actions(b,[('واجهات النظام',self.data_inventory,'network',False),('ملفات الاتصال',self.data_profiles,'network',False),('تشغيل البيانات',lambda:self.data_change(True),'network',True),('إيقاف البيانات',lambda:self.data_change(False),'network',False)])
        self.data_status=label('QMI/MBIM في Linux عبر خدمات النظام؛ Windows عبر WWAN أو ملف RAS بيانات *99 موجود للمودم القديم. اختر الملف الذي يخص جهازك.','muted');b.addWidget(self.data_status);v.addWidget(box);v.addStretch()

    def _build_esim(self):
        v=self._heading('esim','NEXVARY eSIM Manager','تكامل محلي مع تطبيق الهاتف 0.922.0: نقل كود LPA عبر QR واستيراد تقرير إعادة الاستخدام.')
        box,b=panel()
        b.addWidget(label('تطبيق الهاتف المراجع: com.nexvary.simmanager • 0.922.0','good',True))
        b.addWidget(label('إدارة وتنزيل وتفعيل ملفات eSIM تجري عبر LPA مصرح به على الهاتف. هذا المسار لا يثبت نجاح التفعيل أو دعم المودم.','muted'))
        b.addWidget(label('كود التفعيل سري — لا يُحفظ في تقارير التشخيص','gold'))
        self.activation_input=QLineEdit();self.activation_input.setLayoutDirection(Qt.LeftToRight)
        self.activation_input.setEchoMode(QLineEdit.Password);self.activation_input.setMaxLength(2048)
        self.activation_input.setPlaceholderText('LPA:1$SM-DP+$MATCHING-ID');b.addWidget(self.activation_input)
        self.activation_reveal=QCheckBox('إظهار الكود في هذه الجلسة')
        self.activation_reveal.toggled.connect(lambda checked:self.activation_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password));b.addWidget(self.activation_reveal)
        self.activation_status=label('أدخل كودًا تملكه أو استورد صورة QR محلية','muted');b.addWidget(self.activation_status)
        self._actions(b,[('التحقق من صيغة الكود',self.validate_activation,'scan',False),('عرض QR لنقله للهاتف',self.show_activation_qr,'sim',True),('استيراد صورة QR',self.import_activation_qr,'sim',False),('مسح الكود من الجلسة',self.clear_activation,'refresh',False)])
        b.addWidget(label('افتح ماسح QR في NEXVARY SIM Manager على الهاتف، ثم وافق على فتح LPA المتاح. لا تعرض QR أو ترسله لأي طرف آخر.','muted'));v.addWidget(box)
        box,b=panel();b.addWidget(label('تقارير إعادة استخدام الشرائح','gold'))
        b.addWidget(label('من الهاتف: صدّر nexvary_sim_recycling.csv ثم انقله محليًا. السجلات مستوردة من الهاتف وليست فحصًا فعليًا لأجهزة Windows.','muted'))
        b.addWidget(button('استيراد تقرير الهاتف CSV',self.import_recycling_report,'reports'))
        self.recycling_status=label('لم يُستورد تقرير','muted');b.addWidget(self.recycling_status)
        self.recycling_table=table(['الدفعة','الكمية','تصنيف الهاتف','التقييم']);b.addWidget(self.recycling_table);v.addWidget(box);v.addStretch()

    def validate_activation(self):
        try:
            activation=parse_activation(self.activation_input.text())
            summary=activation.summary()
            self.activation_status.setText('الصيغة صالحة • SM-DP+: '+summary['smdp_address']+' • معرّف التفعيل: '+summary['matching_id']+' • رمز تأكيد: '+('مطلوب' if summary['confirmation_required'] else 'غير مطلوب')+' • لم يُختبر التفعيل')
            return activation
        except IntegrationError as error:
            self.activation_status.setText(str(error));return None

    def clear_activation(self):
        self.activation_input.clear();self.activation_reveal.setChecked(False)
        self.activation_status.setText('مُسح الكود من حقول الجلسة — لا يُحفظ تلقائيًا')

    def show_activation_qr(self):
        activation=self.validate_activation()
        if activation is None:return
        if not self._confirm('عرض كود سري','أوافق على عرض كود التفعيل الذي أملكه لنقله إلى هاتفي. يمكن لمن يرى QR استخدام الكود.'):return
        try:payload=qr_png(activation)
        except IntegrationError as error:self.activation_status.setText(str(error));return
        dialog=QDialog(self);dialog.setWindowTitle('نقل آمن محلي إلى NEXVARY SIM Manager')
        layout=QVBoxLayout(dialog);layout.addWidget(label('امسح QR بتطبيق الهاتف. لا تلتقط لقطة شاشة تحتويه.','gold'))
        image=QPixmap();image.loadFromData(payload,'PNG')
        screen=self.screen().availableGeometry();side=max(180,min(460,screen.height()-220,screen.width()-100))
        preview=QLabel();preview.setAlignment(Qt.AlignCenter);preview.setPixmap(image.scaled(side,side,Qt.KeepAspectRatio,Qt.FastTransformation));layout.addWidget(preview)
        layout.addWidget(button('إغلاق ومسح الكود',dialog.accept,'back'))
        dialog.exec();preview.clear();dialog.deleteLater();self.clear_activation()

    def import_activation_qr(self):
        path,_=QFileDialog.getOpenFileName(self,'استيراد QR محلي','','Images (*.png *.jpg *.jpeg *.bmp *.webp)')
        if not path:return
        try:
            activation=read_qr(path);self.activation_input.setText(activation.qr_payload());self.activation_reveal.setChecked(False);self.validate_activation()
        except (IntegrationError,OSError) as error:
            self.activation_status.setText(str(error) if isinstance(error,IntegrationError) else 'تعذر فتح الصورة المحلية')

    def import_recycling_report(self):
        path,_=QFileDialog.getOpenFileName(self,'تقرير تطبيق الهاتف','','CSV (*.csv)')
        if not path:return
        try:
            data=read_recycling_csv(path)
            rows(self.recycling_table,[(r['batch'],r['quantity'],r['classification'],r['condition_score']) for r in data])
            self.recycling_status.setText('تم استيراد '+str(len(data))+' دفعة من تقرير الهاتف — لم تُثبت على أجهزة Windows')
        except (IntegrationError,OSError) as error:
            self.recycling_status.setText(str(error) if isinstance(error,IntegrationError) else 'تعذر فتح التقرير المحلي')

    def _build_reports(self):
        v=self._heading('reports','تقرير الجهاز','تقرير أحدث فحص للجهاز المختار. لا يتضمن محتوى الرسائل أو أسرار المصادقة.')
        self._actions(v,[('تصدير JSON',lambda:self.export_report('json'),'reports',True),('تصدير CSV',lambda:self.export_report('csv'),'reports',False),('تقرير اكتشاف USB',self.export_usb,'devices',False)])
        self.report_table=table(['الفحص','الحالة','النتيجة']);v.addWidget(self.report_table);v.addStretch()

    def _build_about(self):
        v=self._heading('about','النظام والتوافق','ملفات الأدلة لا تعني دعم كل وظائف الجهاز. نتائج المحاكاة منفصلة عن الاختبارات الميدانية.')
        box,b=panel();b.addWidget(label('NEXVARY USB Studio '+__version__,'title'))
        for name,profile in load_profiles().items():
            b.addWidget(label(name+' • '+profile['sim_usim_capability'],'gold'))
            b.addWidget(label(profile['last_verified_evidence']['classification'],'muted'))
        b.addWidget(label('ModemUsimBackend: منفذ AKA محلي بالموافقة والتفويض؛ لا خدمة APDU عامة. تشغيله مع WiFi-Call والشبكة يحتاج أدلة أجهزة ومشغل.','muted'))
        v.addWidget(box);self._actions(v,[('فحص قارئات PC/SC',self.read_pcsc,'sim',True),('SELECT عبر PC/SC',self.pcsc_select,'sim',False),('محاكاة منفصلة',self.show_demo,'scan',False)]);v.addStretch()

    def _require_port(self):
        if not self.selected:
            QMessageBox.information(self,'اختر الجهاز','اختر بطاقة الجهاز من مركز الفلاشات أولًا.');self.show('devices');return False
        return True
    def _with_port(self,title,fn,callback):
        if not self._require_port():return
        device=self.selected;known=self.active_port
        def work():
            port=known or discover_at(device,self.preferences)[0]
            return port,fn(port)
        def done(value):
            self.active_port,result=value
            self.connection_label.setText(device.title+' • منفذ AT المثبت: '+self.active_port)
            callback(result)
        self._job(title,work,done)

    def _job(self,title,fn,callback):
        if self.busy:return
        self.busy=True;self.status_label.setText('جارٍ التنفيذ: '+title)
        def worker():
            try:self.jobs.put((title,callback,fn(),None))
            except Exception as e:
                safe=str(e) if isinstance(e,LabError) else 'تعذر إكمال العملية؛ افحص اتصال الجهاز والتعريف.'
                self.jobs.put((title,callback,None,safe))
        threading.Thread(target=worker,daemon=True).start()
    def _drain(self):
        try:title,callback,result,error=self.jobs.get_nowait()
        except queue.Empty:return
        self.busy=False
        if error:
            self.status_label.setText(error)
            if self._guided_probe:
                self._guided_probe=False;self.guide_error.setText(error+' لا ننتقل لنتيجة ناجحة؛ يمكنك إعادة الفحص يدويًا.');self._guide_update()
            return
        try:callback(result);self.status_label.setText('اكتمل: '+title)
        except Exception:self.status_label.setText('تعذر عرض النتيجة؛ لا تُعتبر نجاحًا.')
    def closeEvent(self,event):
        self.clear_activation()
        if self.busy:
            QMessageBox.information(self,'عملية جارية','انتظر انتهاء العملية قبل إغلاق البرنامج.');event.ignore()
        else:super().closeEvent(event)
    def refresh(self):
        self._job('اكتشاف USB وCOM',detect,self.display_inventory)
    def _populate_readings(self,readings):
        rows(self.sim_table,[(r.name,r.status,r.value+' — '+r.note) for r in readings])
        rows(self.report_table,[(r.name,r.status,r.value) for r in readings])
    def run_probe(self):
        def done(report):
            self.report=report;self.reports[self.selected.key]=report;self._populate_readings(report.readings)
            values={r.name:r for r in report.readings}
            connection=values['Connection'].status=='OK';ready='READY' in values['SIM status'].value
            self.card_label.setText(('تم الاتصال بالمودم بنجاح' if connection else 'لم يثبت الاتصال بالمودم')+
                ('، الشريحة جاهزة' if ready else '، راجع حالة الشريحة')+'؛ الوصول إلى APDU يحتاج اختبارًا مستقلًا.')
            self._render_cards()
            if self._guided_probe:
                self._guided_probe=False;self.guide_stage=3 if connection else 2
                self.guide_error.setText('' if connection else 'لم يثبت الاتصال؛ راجع التوصيل والبرنامج الذي قد يستخدم المنفذ ثم أعد الفحص.')
                self._guide_update()
                if self.current_page=='guide':self.show('guide')
            else:self.show('sim')
        self._with_port('فحص المودم والشريحة',probe,done)
    def check_ef(self):
        if not self._require_port() or not self._confirm('قراءة الشريحة','تأكيد ملكية الشريحة والموافقة على قراءة EF-ICCID دون عرض الرقم الكامل؟'):return
        self._with_port('EF-ICCID',lambda p:self._session(p,lambda s:s.sim_file_check()),self._show_reading)
    def check_apdu(self):
        if not self._require_port() or not self._confirm('اختبار APDU','توافق على إرسال SELECT MF ثابت للقراءة فقط؟ لا يثبت AKA.'):return
        self._with_port('SELECT MF',select_master_file,self._show_reading)
    def check_applications(self):
        from .usim_core import NexvaryUsimCore
        if not self._require_port() or not self._confirm('تطبيقات SIM','توافق على قراءة EF_DIR واختبار SELECT للتطبيقات المعلنة؟ لا تُرسل مصادقة أو أوامر تعديل.'):
            return
        def done(rr):
            readings=list(self.report.readings) if self.report else []
            readings=[x for x in readings if x.name not in ('SIM application','SIM applications','USIM access','ISIM access','USIM AKA')]+rr
            if self.report:self.report.readings=readings
            else:
                from datetime import datetime, timezone
                self.report=Report('NEXVARY USB Studio',__version__,datetime.now(timezone.utc).isoformat(),self.active_port,False,readings)
                self.reports[self.selected.key]=self.report
            self._populate_readings(readings)
            self.card_label.setText('دليل التطبيقات لا يثبت المصادقة؛ راجع النتائج أدناه')
        self._with_port('NEXVARY USIM Core',lambda p:NexvaryUsimCore(p).inspect(consent=True),done)
    def _show_reading(self,r):
        self.card_label.setText(r.value+' — '+r.note)
        readings=list(self.report.readings) if self.report else []
        readings=[x for x in readings if x.name!=r.name]+[r]
        if self.report:self.report.readings=readings
        else:
            from datetime import datetime, timezone
            self.report=Report('NEXVARY USB Studio',__version__,datetime.now(timezone.utc).isoformat(),self.active_port,False,readings)
            self.reports[self.selected.key]=self.report
        self._populate_readings(readings);self._render_cards();self.show('sim')
    def _session(self,port,fn):
        with ATSession(port) as s:return fn(s)
    def _confirm(self,title,text):
        return QMessageBox.question(self,title,text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
    def read_sms(self):
        if not self._require_port() or not self._confirm('خصوصية الرسائل','توافق على قراءة الرسائل وعرضها محليًا؟'):return
        def done(items):
            rows(self.sms_table,[(x['index'],x['sender'],x['status'],x['preview']) for x in items]);self.sms_status.setText(f'{len(items)} رسالة مقروءة محليًا')
        self._with_port('قراءة SMS',lambda p:self._session(p,lambda s:s.inbox()),done)
    def read_text_sms(self):
        self._with_port('قراءة Text',lambda p:self._session(p,lambda s:s.text_inbox()),lambda items:rows(self.sms_table,[(x['index'],x['sender'],x['status'],x['preview']) for x in items]))
    def data_inventory(self):
        self._job('واجهات البيانات',lambda:CellularManager().inventory(),self.data_status.setText)
    def data_profiles(self):
        interface=self.data_interface.text().strip()
        ras=self.data_backend.currentIndex()==1
        self._job('ملفات البيانات',lambda:'\n'.join(RasDataManager().profiles()) if ras else CellularManager().profiles(interface),self.data_status.setText)
    def data_change(self,connect):
        interface=self.data_interface.text().strip();profile=self.data_profile.text().strip()
        if not self._confirm('اتصال البيانات',f"{'تشغيل' if connect else 'إيقاف'} اتصال الواجهة {interface} باستخدام {profile}؟ قد تُحتسب رسوم."):return
        ras=self.data_backend.currentIndex()==1
        self._job('اتصال البيانات',lambda:RasDataManager().change(profile,connect,True) if ras else CellularManager().change(interface,profile,connect,True),self.data_status.setText)
    def pcsc_select(self):
        def choose(names):
            if not names:QMessageBox.information(self,'PC/SC','لا قارئات متاحة.');return
            dialog=QDialog(self);dialog.setWindowTitle('اختيار قارئ PC/SC');v=QVBoxLayout(dialog);combo=QComboBox();combo.addItems(names);v.addWidget(combo)
            def execute():
                reader=combo.currentText()
                if not self._confirm('SELECT MF',f'اختبار قراءة SELECT MF على {reader}؟ لا يثبت AKA.'):return
                dialog.accept();self._job('PC/SC SELECT',lambda:pcsc_run(reader,True),lambda result:QMessageBox.information(self,'PC/SC',result))
            v.addWidget(button('اختبار SELECT',execute,'sim'));v.addWidget(button('رجوع',dialog.reject,'back'));dialog.exec()
        self._job('PC/SC',pcsc_run,choose)
    def send_sms(self):
        if not self._require_port():return
        number=self.number_input.text().strip();body=self.sms_input.toPlainText();ucs2=self.ucs2.isChecked()
        if not self._confirm('تأكيد إرسال رسالة واحدة',f'إرسال إلى {number}\n{body}\nقد تُحتسب رسوم. '+('UCS2 غير مثبت على الجهاز.' if ucs2 else '')):return
        def send(s):return s.send_ucs2_sms(number,body,True,True) if ucs2 else s.send_sms(number,body,True)
        self._with_port('إرسال SMS',lambda p:self._session(p,send),lambda result:self.sms_status.setText(result))
    def read_network(self):
        self._with_port('حالة الشبكة',lambda p:self._session(p,lambda s:s.network_info()),lambda rr:rows(self.network_table,[(r.name,r.status,r.value) for r in rr]))
    def set_apn(self):
        if not self._require_port():return
        cid=self.cid.value();apn=self.apn.text().strip()
        if not self._confirm('تعديل APN',f'تغيير السياق {cid} إلى {apn}؟ لا يتم تشغيل اتصال بيانات.'):return
        self._with_port('حفظ APN',lambda p:self._session(p,lambda s:s.set_apn(cid,apn,True)),lambda result:QMessageBox.information(self,'APN',result))
    def read_pcsc(self):
        self._job('PC/SC',pcsc_run,lambda data:QMessageBox.information(self,'PC/SC','\n'.join(data) or 'لا قارئات متاحة'))

    def show_demo(self):
        def done(r):
            self.selected=None;self.active_port=None;self.report=r;self._populate_readings(r.readings)
            self.connection_label.setText('محاكاة فقط — ليست نتيجة جهاز حقيقي');self.card_label.setText('بيانات اصطناعية؛ لا تثبت التوافق');self.show('sim')
        self._job('محاكاة منفصلة',demo,done)
    def advanced_details(self):
        if not self.selected:return
        d=self.selected;dialog=QDialog(self);dialog.setWindowTitle('واجهات الجهاز — Advanced Details');dialog.resize(760,540)
        v=QVBoxLayout(dialog);v.addWidget(label(d.title,'title'));v.addWidget(label(d.evidence,'muted'))
        t=table(['الواجهة','النوع','USB ID','Driver','الحالة']);rows(t,[(x.name,x.device_class,x.usb_id,x.driver or 'غير متاح',x.mode) for x in d.interfaces]);v.addWidget(t)
        combo=QComboBox();combo.setLayoutDirection(Qt.LeftToRight)
        for p in d.ports:combo.addItem(p.device+' / '+port_role(p),p.device)
        v.addWidget(combo)
        def explicit():
            port=combo.currentData()
            if not port:return
            if not self._confirm('اختبار منفذ مختار',f'اختبار AT محدود على {port}؟ منفذ Diagnostics لا يُعتبر AT قبل نجاح الاختبار.'):return
            chosen=next(p for p in d.ports if p.device==port)
            from .grouping import ModemDevice
            single=ModemDevice(d.key,d.title,d.interfaces,[chosen],d.evidence)
            dialog.accept()
            def done(value):self.active_port=value[0];self.connection_label.setText(d.title+' • منفذ AT المثبت: '+value[0])
            self._job('اختبار AT مختار',lambda:discover_at(single,self.preferences,include_diagnostics=True),done)
        b=button('اختبار AT للمنفذ المختار',explicit,'scan');b.setEnabled(bool(d.ports));v.addWidget(b)
        v.addWidget(button('رجوع',dialog.accept,'back'));dialog.exec()
    def export_report(self,ext):
        if self.report is None:QMessageBox.information(self,'لا نتائج','افحص الجهاز أولًا.');return
        self._save(to_csv(self.report) if ext=='csv' else to_json(self.report),ext)
    def export_usb(self):
        if not self.inventory:return
        self._save(to_diagnostic_json(self.inventory),'json')
    def _save(self,text,ext):
        filename,_=QFileDialog.getSaveFileName(self,'حفظ تقرير منقح','device-report.'+ext,f'{ext.upper()} (*.{ext})')
        if not filename:return
        try:
            with open(filename,'w',encoding='utf-8',newline='') as stream:stream.write(text)
            self.status_label.setText('تم حفظ التقرير المنقح')
        except OSError:QMessageBox.warning(self,'تعذر الحفظ','تعذر إنشاء الملف.')

def main():
    import sys
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('NEXVARY USB Studio');app.setOrganizationName('NEXVARY')
    app.setLayoutDirection(Qt.RightToLeft)
    import os
    marker=os.environ.get('NEXVARY_PACKAGE_SMOKE')
    ui=Workstation(auto_refresh=not bool(marker));ui.show()
    if marker:
        def smoke():
            for kind in ICON_KINDS:
                icon(kind)
            opened=[]
            for key in ui.pages:
                ui.show(key);app.processEvents();opened.append(key)
            try:
                pcsc_run()
                pcsc_check='native inventory completed'
            except LabError as exc:
                if 'مهلة' in str(exc) or 'worker unavailable' in str(exc):raise
                pcsc_check='native service unavailable; child returned safely'
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                payload=parse_activation('LPA:1$example.invalid$SYNTHETIC-PACKAGE')
                qr_path=Path(directory)/'synthetic-qr.png';qr_path.write_bytes(qr_png(payload))
                if read_qr(qr_path).qr_payload()!=payload.qr_payload():raise RuntimeError('Packaged QR roundtrip failed')
                csv_path=Path(directory)/'synthetic-report.csv'
                csv_path.write_text('batch,quantity,classification,condition_score\n1,2,LAB_REUSE,80\n',encoding='utf-8')
                if len(read_recycling_csv(csv_path))!=1:raise RuntimeError('Packaged CSV failed')
            Path(marker).write_text(json.dumps({'esim_contract':'synthetic QR and CSV passed','pages':opened,'version':__version__,'pcsc_child':pcsc_check,'color_icons':list(ICON_KINDS)}),encoding='utf-8')
            ui.close()
            app.quit()
        QTimer.singleShot(1500,smoke)
    result=app.exec()
    ui.close();ui.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    return result

App=Workstation
