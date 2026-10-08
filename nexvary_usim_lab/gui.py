"""NEXVARY USB Desktop — Arabic RTL integrated Windows/Linux workstation.

Device discovery, AT/SIM diagnostics, limited on-card checks, local SMS,
PC/SC inventory and redacted evidence — without arbitrary modem commands.
"""
from __future__ import annotations

from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import demo, probe, select_master_file, pcsc_readers, to_json, to_csv
from .catalog import identification_hint
from .discovery import detect, to_diagnostic_json
from .device_operations import ATSession
from . import __version__

DARK="#0B1420"
NAV="#101E2C"
PANEL="#182A3B"
FIELD="#20364A"
EDGE="#375165"
FG="#EFF7FD"
MUTED="#B0C1CE"
CYAN="#56D8ED"
GOLD="#F5C968"
GREEN="#67DEB0"
RED="#FB858A"
BLUE="#7FA8FF"
FON="Segoe UI"

class Workstation:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"NEXVARY USB • Modem & USIM Studio {__version__}")
        root.geometry("1250x800")
        root.minsize(990, 670)
        root.configure(bg=DARK)
        self.report = None
        self.inventory = None
        self.ports = []
        self.active_port = None
        self.busy = False
        self.current_page = "devices"
        self.status_var = tk.StringVar(value="جاهز للفحص • لم يبدأ أي اختبار للأجهزة")
        self.connection_var = tk.StringVar(value="لم يتم اختيار فلاشة")
        self.detection_var = tk.StringVar(value="فحص الأجهزة لم يبدأ")
        self.card_var = tk.StringVar(value="شريحة SIM: لم تُفحص")
        self.sms_status = tk.StringVar(value="الرسائل محلية ولا تُرسل تلقائيًا")
        self._init_style()
        self._compose()
        self.refresh()

    def _init_style(self):
        s=ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("N.Treeview",background=FIELD,fieldbackground=FIELD,foreground=FG,
                    rowheight=32,borderwidth=0,font=(FON,10))
        s.configure("N.Treeview.Heading",background=PANEL,foreground=CYAN,
                    font=(FON,10,"bold"),padding=(8,9),borderwidth=0)
        s.map("N.Treeview",background=[("selected","#2B6172")],foreground=[("selected","#FFFFFF")])
        s.configure("N.Vertical.TScrollbar",background=EDGE, troughcolor=NAV)

    def _label(self,parent,txt,size=11,color=FG,bold=False,wrap=0):
        return tk.Label(parent,text=txt,bg=parent.cget("bg"),fg=color,font=(FON,size,"bold" if bold else "normal"),
                        anchor="e",justify="right",wraplength=wrap)

    def _btn(self,parent,text,callback,accent=False,width=None):
        return tk.Button(parent,text=text,command=callback,bg=CYAN if accent else FIELD,
                         fg=DARK if accent else FG,activebackground=GOLD,
                         font=(FON,10,"bold"),relief="flat",bd=0,padx=15,pady=11,
                         cursor="hand2",width=width,highlightthickness=0)

    def _panel(self,parent,padx=16,pady=13):
        return tk.Frame(parent,bg=PANEL,padx=padx,pady=pady)

    def _heading(self,parent,title,desc):
        self._label(parent,title,20,FG,True).pack(anchor="e")
        self._label(parent,desc,10,MUTED,wrap=850).pack(anchor="e",pady=(2,17))

    def _tree(self,parent,cols):
        holder=tk.Frame(parent,bg=PANEL)
        tree=ttk.Treeview(holder,columns=[x[0] for x in cols],show="headings",style="N.Treeview")
        for key,title,size in cols:
            tree.heading(key,text=title,anchor="e")
            tree.column(key,width=size,minwidth=75,anchor="e",stretch=True)
        scrollbar=ttk.Scrollbar(holder,orient="vertical",command=tree.yview,style="N.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y")
        tree.pack(side="left",fill="both",expand=True)
        return holder,tree

    def _icon(self,parent,kind,color):
        icon=tk.Canvas(parent,width=34,height=34,bg=NAV,highlightthickness=0)
        def line(*points,**kw):icon.create_line(*points,fill=color,width=2.5,capstyle="round",joinstyle="round",**kw)
        if kind=="devices":
            icon.create_rectangle(7,7,28,23,outline=color,width=2)
            line(18,24,18,28);line(12,29,24,29)
        elif kind=="sim":
            line(9,5,23,5,28,10,28,29,8,29,8,6,9,5)
            icon.create_rectangle(13,14,23,23,outline=color,width=1.8)
        elif kind=="sms":
            icon.create_rectangle(5,7,29,23,outline=color,width=2)
            line(8,24,8,30,15,24);line(11,13,24,13);line(11,18,19,18)
        elif kind=="reports":
            icon.create_rectangle(8,4,27,30,outline=color,width=2)
            line(12,12,23,12);line(12,18,23,18);line(12,24,20,24)
        else:
            icon.create_oval(9,9,26,26,outline=color,width=2)
            line(18,6,18,1);line(18,28,18,33);line(6,18,1,18);line(29,18,34,18)
        return icon

    def _compose(self):
        header=tk.Frame(self.root,bg=DARK,padx=20,pady=12)
        header.pack(fill="x")
        mark=tk.Frame(header,bg=DARK)
        mark.pack(side="left")
        tk.Label(mark,text="NEXVARY",bg=DARK,fg=CYAN,font=(FON,22,"bold")).pack(side="left")
        tk.Label(mark,text=f"  USB STUDIO  |  {__version__}",bg=DARK,fg=MUTED,font=(FON,10)).pack(side="left")
        headline=tk.Frame(header,bg=DARK)
        headline.pack(side="right")
        self._label(headline,"منصة إدارة فلاشات USB وشرائح SIM",16,FG,True).pack(anchor="e")
        self._label(headline,"Windows / Linux   •   فحص أجهزة حقيقية   •   تقارير آمنة",9,MUTED).pack(anchor="e")
        main=tk.Frame(self.root,bg=DARK)
        main.pack(fill="both",expand=True,padx=14,pady=(0,8))
        self.sidebar=tk.Frame(main,bg=NAV,width=237,padx=10,pady=18)
        self.sidebar.pack(side="right",fill="y",padx=(9,0))
        self.sidebar.pack_propagate(False)
        self._label(self.sidebar,"الأقسام الرئيسية",12,CYAN,True).pack(anchor="e",pady=(0,13))
        self.nav={}
        menu=[("devices","الأجهزة والفلاشات",CYAN),("sim","الشريحة و APDU",GREEN),
              ("sms","إدارة الرسائل SMS",GOLD),("reports","النتائج والتقارير",BLUE),
              ("about","النظام والتوافق",MUTED)]
        for key,title,color in menu:
            item=tk.Frame(self.sidebar,bg=NAV,height=54)
            item.pack(fill="x",pady=4)
            item.pack_propagate(False)
            icon=self._icon(item,key,color);icon.pack(side="right",padx=(4,7))
            b=tk.Button(item,text=title,command=lambda page=key:self.show(page),
                        fg=FG,bg=NAV,activebackground=FIELD,activeforeground=CYAN,
                        relief="flat",anchor="e",font=(FON,11,"bold"),cursor="hand2",bd=0)
            b.pack(side="right",fill="both",expand=True)
            self.nav[key]=(item,b)
        tk.Frame(self.sidebar,bg=NAV).pack(fill="both",expand=True)
        self._label(self.sidebar,"لا نسخ مفاتيح SIM ولا تجاوز صلاحيات الشبكة",9,MUTED,wrap=208).pack(side="bottom",anchor="e")
        self.content=tk.Frame(main,bg=DARK)
        self.content.pack(side="left",fill="both",expand=True)
        self.pages={}
        for key in ("devices","sim","sms","reports","about"):
            page=tk.Frame(self.content,bg=DARK,padx=7,pady=6)
            self.pages[key]=page
        self._build_devices()
        self._build_sim()
        self._build_sms()
        self._build_reports()
        self._build_about()
        footer=tk.Frame(self.root,bg=NAV,padx=16,pady=8)
        footer.pack(fill="x")
        tk.Label(footer,text="●",bg=NAV,fg=GREEN,font=(FON,11)).pack(side="right",padx=(3,9))
        tk.Label(footer,textvariable=self.status_var,bg=NAV,fg=FG,font=(FON,10),
                 justify="right",anchor="e").pack(side="right",fill="x",expand=True)
        self.show("devices")

    def show(self,key):
        self.current_page=key
        for name,page in self.pages.items():
            page.pack_forget()
            self.nav[name][0].configure(bg=FIELD if name==key else NAV)
            self.nav[name][1].configure(bg=FIELD if name==key else NAV,fg=CYAN if name==key else FG)
        self.pages[key].pack(fill="both",expand=True)

    def _actions(self,parent,*buttons):
        tools=tk.Frame(parent,bg=DARK)
        tools.pack(fill="x",pady=(0,14))
        for name,fn,accent in buttons:
            self._btn(tools,name,fn,accent).pack(side="right",padx=(6,0))
        return tools

    def _build_devices(self):
        page=self.pages["devices"]
        self._heading(page,"مركز إدارة مودمات USB","اكتشاف أجهزة Huawei وZTE ومنافذ COM وربط كل منفذ بالمودم؛ دون تغيير Firmware أو تعريفات النظام")
        self._actions(page,("تحديث الأجهزة",self.refresh,True),
                      ("فحص منفذ AT",self.run_probe,False),
                      ("تجربة محاكاة",self.show_demo,False))
        strip=self._panel(page,pady=11)
        strip.pack(fill="x",pady=(0,12))
        self._label(strip,"حالة الاكتشاف",11,CYAN,True).pack(side="right",padx=14)
        self._label(strip,"",10).destroy()
        tk.Label(strip,textvariable=self.detection_var,bg=PANEL,fg=FG,
                 font=(FON,10),anchor="e",justify="right",wraplength=650).pack(side="right",fill="x",expand=True)
        usb=self._panel(page)
        usb.pack(fill="both",expand=True,pady=(0,11))
        self._label(usb,"واجهات USB المكتشفة عبر Windows PnP",12,FG,True).pack(anchor="e",pady=(0,8))
        holder,self.usb_table=self._tree(usb,[("mode","الحالة",132),("id","USB VID:PID",125),
                                               ("class","النوع",100),("name","اسم الجهاز",360)])
        holder.pack(fill="both",expand=True)
        port_area=self._panel(page,pady=11)
        port_area.pack(fill="both",expand=True)
        self._label(port_area,"منافذ AT / COM — اختر منفذ المودم",12,FG,True).pack(anchor="e",pady=(0,8))
        holder,self.port_table=self._tree(port_area,[("device","المنفذ",90),("hint","التعريف",320),
                                                     ("description","الوصف",330)])
        holder.pack(fill="both",expand=True)
        self.port_table.bind("<<TreeviewSelect>>",self._select_port)
        tk.Label(port_area,textvariable=self.connection_var,bg=PANEL,fg=GREEN,
                 font=(FON,10),anchor="e").pack(fill="x",pady=(8,0))

    def _build_sim(self):
        page=self.pages["sim"]
        self._heading(page,"فحص الشريحة وملفات USIM","عمليات ثابتة للقراءة فقط؛ لا تغيير PIN ولا استخراج مفاتيح المصادقة ولا تجاوز قيود المشغل")
        self._actions(page,("الفحص الشامل للمودم",self.run_probe,True),
                      ("فحص EF-ICCID",self.check_ef,False),
                      ("SELECT MF عبر APDU",self.check_apdu,False))
        info=self._panel(page)
        info.pack(fill="x",pady=(0,12))
        tk.Label(info,textvariable=self.connection_var,fg=CYAN,bg=PANEL,
                 font=(FON,12,"bold"),anchor="e").pack(fill="x",pady=5)
        tk.Label(info,textvariable=self.card_var,fg=GREEN,bg=PANEL,
                 font=(FON,11),anchor="e").pack(fill="x",pady=5)
        results=self._panel(page)
        results.pack(fill="both",expand=True)
        self._label(results,"فحوصات الجهاز والشريحة",13,FG,True).pack(anchor="e",pady=(0,10))
        holder,self.sim_table=self._tree(results,[("status","الحالة",130),("value","النتيجة الآمنة",460),
                                                   ("name","الفحص",200)])
        holder.pack(fill="both",expand=True)
        self._label(results,"نجاح AT+CSIM=? لا يعني نجاح APDU أو AKA. إثبات SIM-AKA يحتاج تحديًا مصرحًا من الشبكة.",9,MUTED,wrap=780).pack(anchor="e",pady=(12,0))

    def _build_sms(self):
        page=self.pages["sms"]
        self._heading(page,"إدارة رسائل SMS","قراءة الرسائل المحلية وإرسال رسالة يطلبها المستخدم صراحة؛ دون إرسال جماعي أو تلقائي")
        box=self._panel(page)
        box.pack(fill="x",pady=(0,12))
        self._label(box,"رقم الهاتف الدولي (مثال: +201XXXXXXXXX)",10,FG,True).pack(anchor="e",pady=(0,5))
        self.number_input=tk.Entry(box,bg=FIELD,fg=FG,insertbackground=CYAN,
                                    font=(FON,12),relief="flat",justify="right")
        self.number_input.pack(fill="x",ipady=9,pady=(0,12))
        self._label(box,"نص الرسالة (حاليًا أحرف إنجليزية قابلة للطباعة، حتى 160 حرفًا)",10,FG,True).pack(anchor="e",pady=(0,5))
        self.sms_input=tk.Text(box,bg=FIELD,fg=FG,insertbackground=CYAN,
                               font=(FON,11),height=4,relief="flat",wrap="word")
        self.sms_input.pack(fill="x",pady=(0,12))
        self._actions(box,("إرسال رسالة بموافقتي",self.send_sms,True),
                      ("قراءة الرسائل المستلمة",self.read_sms,False))
        tk.Label(box,textvariable=self.sms_status,bg=PANEL,fg=GOLD,
                 font=(FON,10),anchor="e").pack(fill="x")
        history=self._panel(page)
        history.pack(fill="both",expand=True)
        self._label(history,"صندوق الرسائل المحلي — لا يُصدّر محتواه تلقائيًا",12,FG,True).pack(anchor="e",pady=(0,9))
        holder,self.sms_table=self._tree(history,[("idx","رقم",65),("from","المرسل (منقح)",180),
                                                   ("status","الحالة",135),("body","معاينة محلية",360)])
        holder.pack(fill="both",expand=True)

    def _build_reports(self):
        page=self.pages["reports"]
        self._heading(page,"سجل الفحوصات والتقارير","ملفات JSON وCSV تخفي أرقام الشرائح؛ يمكنك إرسالها للدعم الفني دون كشف مفاتيح SIM")
        self._actions(page,("تصدير فحص المودم JSON",lambda:self.export_report("json"),True),
                      ("تصدير CSV",lambda:self.export_report("csv"),False),
                      ("تقرير USB",self.export_usb,False))
        content=self._panel(page)
        content.pack(fill="both",expand=True)
        self._label(content,"نتائج أحدث فحص",13,FG,True).pack(anchor="e",pady=(0,10))
        holder,self.report_table=self._tree(content,[("name","الفحص",165),("status","الحالة",145),
                                                     ("value","النتيجة",460)])
        holder.pack(fill="both",expand=True)
        self._label(content,"قراءة رسائل SMS لا تدخل في هذه التقارير. لا تحفظ تحديات AKA أو Ki/OPc.",10,MUTED).pack(anchor="e",pady=12)

    def _build_about(self):
        page=self.pages["about"]
        self._heading(page,"معلومات النظام والتوافق","لوحة مختبر USB مستقلة عن Gateway حتى يثبت التوافق مع الشريحة والمشغل")
        box=self._panel(page,pady=22)
        box.pack(fill="x",pady=(0,13))
        for line in (
            f"الإصدار: {__version__}",
            "الأجهزة: Huawei E153 / Huawei K3770 / ZTE MF190S — ملفات أولية قابلة للتوسعة",
            "تم إثبات الاتصال مع K3770 واكتشاف SIM عبر AT في الاختبار الميداني، وليس بعد دعم SIM-AKA.",
            "Windows 10/11 وLinux — تشخيص متعدد المنافذ وفحوصات مستقلة.",
            "لا يتم إرسال بيانات الأجهزة أو محتوى الشريحة إلى خادم خارجي.",
            "اختبار المصادقة مع NEXVARY-WiFi-Call ما زال غير مثبت.",
        ):
            self._label(box,line,11,FG if "الإصدار" not in line else CYAN,wrap=850).pack(anchor="e",pady=8)
        actions=self._panel(page)
        actions.pack(fill="x")
        self._btn(actions,"فحص قارئات PC/SC",self.read_pcsc,False).pack(side="right")
        self._btn(actions,"إعادة اكتشاف USB",self.refresh,True).pack(side="right",padx=8)

    def _select_port(self,*_):
        selected=self.port_table.selection()
        if not selected: return
        values=self.port_table.item(selected[0],"values")
        if values:
            self.active_port=str(values[0])
            self.connection_var.set(f"المنفذ المحدد: {self.active_port} — جاهز لاختبار AT")

    def _require_port(self):
        if not self.active_port:
            messagebox.showinfo("اختر الفلاشة","اذهب إلى الأجهزة والفلاشات واختر منفذ COM أولًا.")
            self.show("devices")
            return None
        return self.active_port

    def _job(self,title,fn,callback):
        if self.busy:
            messagebox.showinfo("مشغول","هناك عملية جارية، انتظر اكتمالها.")
            return
        self.busy=True
        self.status_var.set("جارٍ التنفيذ: "+title)
        def worker():
            try:
                result=fn()
                self.root.after(0,lambda:self._finish_job(title,callback,result,None))
            except Exception as exc:
                # User-visible generic sanitized errors. Do not display raw SIM/APDU.
                safe=str(exc) if type(exc).__name__=="LabError" else "فشل التعامل مع المودم أو انقطع الاتصال."
                self.root.after(0,lambda msg=safe:self._finish_job(title,callback,None,msg))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_job(self,title,callback,result,error):
        self.busy=False
        if error:
            self.status_var.set("تعذّر "+title+": "+error)
            if self.current_page=="sms": self.sms_status.set(error)
            return
        try: callback(result)
        except Exception:
            self.status_var.set("اكتملت العملية لكن حدث خلل في عرض النتائج.")
            return
        self.status_var.set("اكتمل: "+title)

    def refresh(self):
        def display(data):
            self.inventory=data
            for t in (self.usb_table,self.port_table):
                for old in t.get_children():t.delete(old)
            for device in data.devices:
                self.usb_table.insert("","end",values=(device.mode,device.usb_id,
                                                       device.device_class,device.name))
            self.ports=data.serial_ports
            values={x.device for x in self.ports}
            if self.active_port not in values:
                self.active_port=None
            for port in self.ports:
                self.port_table.insert("","end",values=(port.device,
                    identification_hint(port.description,port.manufacturer,port.vid),port.description))
            if self.active_port:
                for row in self.port_table.get_children():
                    if self.port_table.item(row,"values")[0]==self.active_port:
                        self.port_table.selection_set(row);self.port_table.see(row);break
            elif len(self.ports)==1:
                rows=self.port_table.get_children()
                self.port_table.selection_set(rows[0])
                self._select_port()
            self.detection_var.set(data.message+f" | أجهزة USB: {len(data.devices)}, منافذ COM: {len(self.ports)}")
            self.connection_var.set(f"المنفذ المحدد: {self.active_port}" if self.active_port else "اختر منفذ COM من القائمة")
        self._job("اكتشاف USB وCOM",detect,display)

    def _populate_readings(self,readings):
        for table in (self.sim_table,self.report_table):
            for row in table.get_children():table.delete(row)
        for item in readings:
            self.sim_table.insert("","end",values=(item.status,item.value,item.name))
            self.report_table.insert("","end",values=(item.name,item.status,item.value))

    def run_probe(self):
        port=self._require_port()
        if port is None:return
        def finish(r):
            self.report=r
            self._populate_readings(r.readings)
            self.card_var.set("الشريحة: "+next((v.value for v in r.readings if v.name=="SIM status"),"غير معروف"))
            self.show("sim")
        self._job("فحص AT وSIM على "+port,lambda:probe(port),finish)

    def show_demo(self):
        def finish(r):
            self.report=r
            self._populate_readings(r.readings)
            self.card_var.set("محاكاة فقط — لا توجد شريحة فعلية")
            self.show("sim")
            messagebox.showinfo("بيانات تجريبية","نتائج Demo فقط، لا تُستخدم لإثبات توافق الأجهزة.")
        self._job("محاكاة غير متصلة بالأجهزة",demo,finish)

    def check_ef(self):
        port=self._require_port()
        if port is None:return
        if not messagebox.askyesno("قراءة ملف SIM","هل تملك الشريحة وتوافق على فحص قراءة EF-ICCID دون عرض الرقم الكامل؟"):
            return
        def do():
            with ATSession(port) as s:return s.sim_file_check()
        def finish(result):
            self.sim_table.insert("","end",values=(result.status,result.value,result.name))
            self.card_var.set(f"قراءة EF-ICCID: {result.status} — {result.value}")
        self._job("فحص ملف الشريحة",do,finish)

    def check_apdu(self):
        port=self._require_port()
        if port is None:return
        if not messagebox.askyesno("اختبار APDU للبطاقة","تأكيد ملكية الشريحة والموافقة على إرسال SELECT MF ثابت إلى البطاقة؟\nلا يُثبت هذا اختبار AKA."):
            return
        def finish(r):
            self.sim_table.insert("","end",values=(r.status,r.value,r.name))
            self.card_var.set(f"APDU: {r.status} — {r.value}; {r.note}")
            self.show("sim")
        self._job("اختبار APDU",lambda:select_master_file(port),finish)

    def read_sms(self):
        port=self._require_port()
        if port is None:return
        if not messagebox.askyesno("خصوصية الرسائل","هل توافق على قراءة الرسائل الموجودة على الشريحة/المودم وعرضها محليًا؟"):
            return
        def do():
            with ATSession(port) as s:return s.inbox()
        def finish(records):
            for row in self.sms_table.get_children():self.sms_table.delete(row)
            for x in records:
                self.sms_table.insert("","end",values=(x["index"],x["sender"],x["status"],x["preview"]))
            self.sms_status.set(f"عدد السجلات المقروءة: {len(records)} (قراءة محلية فقط)")
        self._job("قراءة صندوق SMS",do,finish)

    def send_sms(self):
        port=self._require_port()
        if port is None:return
        number=self.number_input.get().strip()
        msg=self.sms_input.get("1.0","end-1c")
        if not messagebox.askyesno("تأكيد إرسال SMS",
            "هل تريد إرسال رسالة واحدة الآن إلى الرقم الذي أدخلته؟\n"
            "قد تترتب رسوم من شركة الاتصالات. لا تعاود الإرسال عند مهلة دون التحقق."):
            return
        def do():
            with ATSession(port) as s:return s.send_sms(number,msg,confirmed=True)
        def finish(result):
            self.sms_status.set(result)
        self._job("إرسال SMS واحدة",do,finish)

    def read_pcsc(self):
        def done(data):
            installed,names=data
            messagebox.showinfo("قارئات PC/SC",
                ("المكتبة موجودة" if installed else "المكتبة الاختيارية غير مثبتة")+
                "\nالقارئات: "+(", ".join(names) if names else "لا توجد قارئات"))
        self._job("فحص PC/SC",pcsc_readers,done)

    def export_report(self,ext):
        if self.report is None:
            messagebox.showinfo("لا توجد نتائج","نفذ فحص مودم أو افتح المحاكاة أولًا.")
            return
        filename=filedialog.asksaveasfilename(defaultextension="."+ext,filetypes=[(ext.upper(),"*."+ext)])
        if not filename:return
        try:
            output=to_csv(self.report) if ext=="csv" else to_json(self.report)
            with open(filename,"x",encoding="utf-8",newline="") as f:f.write(output)
            self.status_var.set("تم حفظ تقرير الفحص المنقح")
        except FileExistsError:
            messagebox.showwarning("موجود بالفعل","اختر اسم ملف آخر.")
        except OSError:
            messagebox.showerror("تعذر الحفظ","تعذر إنشاء ملف التقرير.")

    def export_usb(self):
        if not self.inventory:
            messagebox.showinfo("لا توجد بيانات","اضغط تحديث الأجهزة أولًا.")
            return
        name=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if not name:return
        try:
            with open(name,"x",encoding="utf-8") as f:f.write(to_diagnostic_json(self.inventory))
            self.status_var.set("تم حفظ بيانات اكتشاف USB المنقحة")
        except FileExistsError:
            messagebox.showwarning("موجود بالفعل","اختر اسم ملف آخر.")
        except OSError:
            messagebox.showerror("تعذر الحفظ","تعذر إنشاء التقرير.")

def main():
    root=tk.Tk()
    Workstation(root)
    root.mainloop()

App=Workstation  # compatibility with former source imports
