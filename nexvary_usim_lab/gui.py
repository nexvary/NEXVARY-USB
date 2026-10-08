"""RTL-aware Tk desktop UI for safe USB-USIM inventory."""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import LabError, demo, pcsc_readers, ports, probe, select_master_file, to_csv, to_json
from .catalog import identification_hint
from .discovery import detect, to_diagnostic_json
import sys
import os

BG = "#0C1319"
PANEL = "#17232E"
FIELD = "#223440"
FG = "#EDF4F8"
SOFT = "#AABDC8"
ACCENT = "#49D3B0"
BLUE = "#6AABD9"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("NEXVARY | USB-USIM Lab")
        self.root.geometry("1150x790")
        self.root.minsize(900, 640)
        self.root.configure(bg=BG)
        self.devices = []
        self.usb_devices = []
        self.inventory = None
        self.report = None
        self.busy = False
        self.status = tk.StringVar(value="جاهز — لم يتم الاتصال بأي جهاز")
        self.device_status = tk.StringVar(value="جارٍ اكتشاف أجهزة USB وCOM...")
        self.usb_advice = tk.StringVar(value="سنعرض هنا حالة تعريف الفلاشة حتى لو لم يظهر منفذ COM.")
        self._styles()
        self._layout()
        self.refresh()

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("N.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=31, bordercolor=FIELD, font=("Segoe UI", 10))
        style.configure("N.Treeview.Heading", background=FIELD, foreground=FG,
                        borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("N.Treeview", background=[("selected", "#20546A")],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("N.Vertical.TScrollbar", background=FIELD, troughcolor=BG)

    def _label(self, parent, text, size=11, color=FG, bold=False):
        return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        anchor="e", justify="right")

    def _button(self, parent, text, action, strong=False):
        return tk.Button(parent, text=text, command=action, cursor="hand2",
                         font=("Segoe UI", 10, "bold"), padx=18, pady=9,
                         relief="flat", activebackground="#25596A",
                         bg=ACCENT if strong else FIELD,
                         fg=BG if strong else FG)

    def _layout(self):
        header = tk.Frame(self.root, bg=BG, padx=22, pady=16)
        header.pack(fill="x")
        tk.Label(header, text="NEXVARY", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 19, "bold")).pack(side="left")
        title = tk.Frame(header, bg=BG)
        title.pack(side="right")
        self._label(title, "مختبر فلاشات الإنترنت وشرائح USIM", 18, bold=True).pack(anchor="e")
        self._label(title, "تشخيص محلي آمن — لا يجري مصادقة AKA ولا اتصالات بالشبكة", 10, SOFT).pack(anchor="e")

        toolbar = tk.Frame(self.root, bg=BG, padx=22)
        toolbar.pack(fill="x", pady=(0, 12))
        self._button(toolbar, "تجربة بدون جهاز", self.show_demo).pack(side="left", padx=(0, 8))
        self._button(toolbar, "تصدير التقرير", self.export).pack(side="left")
        self._button(toolbar, "تقرير USB", self.export_usb).pack(side="left", padx=(8, 0))
        self._button(toolbar, "اختبار APDU", self.apdu_check).pack(side="left", padx=(8, 0))
        self._button(toolbar, "فحص الفلاشة المحددة", self.inspect, strong=True).pack(side="right")
        self._button(toolbar, "تحديث الأجهزة", self.refresh).pack(side="right", padx=(0, 8))

        body = tk.PanedWindow(self.root, orient="horizontal", bg=BG, bd=0,
                              sashwidth=8, sashrelief="flat")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 9))
        devices = tk.Frame(body, bg=PANEL, padx=13, pady=13)
        results = tk.Frame(body, bg=PANEL, padx=13, pady=13)
        body.add(results, stretch="always", minsize=370)
        body.add(devices, stretch="never", minsize=270, width=310)

        self._label(devices, "الأجهزة المكتشفة عبر Windows USB", 12, bold=True).pack(fill="x", pady=(0, 6))
        tk.Label(devices, textvariable=self.device_status, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 10, "bold"), anchor="e", justify="right",
                 wraplength=305).pack(fill="x", pady=(0, 6))
        self.usb_box = tk.Listbox(devices, bg=FIELD, fg=FG, selectbackground="#276078",
                                  borderwidth=0, font=("Segoe UI", 10), height=7,
                                  activestyle="none", exportselection=False)
        self.usb_box.pack(fill="x", pady=(0, 6))
        self.usb_box.bind("<<ListboxSelect>>", self.on_usb_select)
        tk.Label(devices, textvariable=self.usb_advice, bg=PANEL, fg=SOFT,
                 font=("Segoe UI", 9), anchor="e", justify="right",
                 wraplength=302).pack(fill="x", pady=(0, 14))
        self._label(devices, "منافذ COM الجاهزة للاختبار", 12, bold=True).pack(fill="x", pady=(0, 9))
        self.ports_box = tk.Listbox(devices, bg=FIELD, fg=FG, selectbackground="#276078",
                                    selectforeground="white", borderwidth=0,
                                    font=("Consolas", 10), activestyle="none", height=8,
                                    exportselection=False)
        self.ports_box.pack(fill="both", expand=True)
        self._label(devices, "لا تختبر جهاز تخزين USB كمنفذ AT.", 9, SOFT).pack(fill="x", pady=(10, 0))
        self._label(devices, "إذا ظهرت USB فقط، احفظ تقرير USB وأرسله للفحص.", 9, SOFT).pack(fill="x")

        self._label(results, "نتائج الاختبارات", 13, bold=True).pack(fill="x", pady=(0, 10))
        frame = tk.Frame(results, bg=PANEL)
        frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(frame, columns=("status", "result", "name"),
                                  show="headings", style="N.Treeview")
        for key, label, width in (("name", "الفحص", 125),
                                  ("result", "النتيجة المنقحة", 260),
                                  ("status", "الحالة", 105)):
            self.table.heading(key, text=label, anchor="e")
            self.table.column(key, width=width, anchor="e", stretch=(key == "result"))
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, command=self.table.yview, orient="vertical",
                                  style="N.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        footer = tk.Frame(self.root, bg=BG, padx=22, pady=13)
        footer.pack(fill="x")
        self._label(footer, "التوافق مع AKA / PCSC / ePDG / IMS غير مثبت حتى إجراء اختبارات حقيقية.", 9, SOFT).pack(side="right")
        tk.Label(footer, textvariable=self.status, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10)).pack(side="left")

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.device_status.set("جارٍ فحص USB وCOM بدون تعديل تعريفات Windows...")
        self.status.set("يتم البحث عن الجهاز عبر Windows PnP والمنافذ التسلسلية")
        def worker():
            try:
                result = detect()
                self.root.after(0, lambda: self._refresh_done(result, None))
            except Exception:
                self.root.after(0, lambda: self._refresh_done(None, "فشل تشخيص USB. افتح إدارة الأجهزة للتحقق من التعريف."))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_done(self, snapshot, error):
        self.busy = False
        self.ports_box.delete(0, "end")
        self.usb_box.delete(0, "end")
        self.devices = []
        self.usb_devices = []
        self.inventory = snapshot
        if error:
            self.device_status.set("لم يكتمل الفحص")
            self.usb_advice.set(error)
            self.status.set(error)
            return
        self.devices = snapshot.serial_ports
        self.usb_devices = snapshot.devices
        for item in snapshot.devices:
            self.usb_box.insert("end", f"{item.name[:42]} | {item.usb_id} | {item.mode}")
        for item in self.devices:
            self.ports_box.insert("end", f"{item.device} | {identification_hint(item.description, item.manufacturer, item.vid)}")
        if self.usb_devices:
            self.usb_box.selection_set(0)
            self.on_usb_select()
        else:
            self.usb_advice.set("لا تظهر واجهات Huawei/ZTE في PnP. افصل وأعد توصيل الفلاشة، ثم تحقق من Device Manager.")
        if self.devices:
            self.ports_box.selection_set(0)
        self.device_status.set(snapshot.message)
        self.status.set(f"واجهات USB: {len(snapshot.devices)} | منافذ COM: {len(snapshot.serial_ports)} | {snapshot.diagnostic}")
        if not self.devices:
            for row in self.table.get_children():
                self.table.delete(row)
            self.table.insert("", "end", values=("NO_COM", "افتح تقرير USB أو Device Manager لمعرفة السبب", "كشف المنافذ"))
            self.report = None

    def on_usb_select(self, *_):
        selected = self.usb_box.curselection()
        if not selected or selected[0] >= len(self.usb_devices):
            return
        device = self.usb_devices[selected[0]]
        self.usb_advice.set(device.advice)
        if device.com_port:
            for index, port in enumerate(self.devices):
                if port.device.upper() == device.com_port:
                    self.ports_box.selection_clear(0, "end")
                    self.ports_box.selection_set(index)
                    self.ports_box.see(index)
                    break

    def export_usb(self):
        if not self.inventory:
            messagebox.showinfo("NEXVARY", "اضغط تحديث الأجهزة وانتظر اكتمال التشخيص.")
            return
        path = filedialog.asksaveasfilename(title="حفظ تشخيص USB المنقح",
                                            defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "x", encoding="utf-8", newline="") as handle:
                handle.write(to_diagnostic_json(self.inventory))
            self.status.set("حُفظ تقرير USB بدون أرقام IMEI أو بيانات InstanceId الكاملة.")
        except FileExistsError:
            messagebox.showwarning("NEXVARY", "الملف موجود بالفعل؛ اختر اسمًا جديدًا.")
        except OSError:
            messagebox.showerror("NEXVARY", "تعذر حفظ التقرير.")

    def _show_report(self, report):
        self.report = report
        for row in self.table.get_children():
            self.table.delete(row)
        for result in report.readings:
            self.table.insert("", "end", values=(result.status, result.value, result.name))
        self.status.set("بيانات تجريبية فقط" if report.simulated
                        else f"اكتمل الفحص المحلي: {report.device} — النتائج لا تثبت AKA")

    def show_demo(self):
        if not self.busy:
            self._show_report(demo())

    def inspect(self):
        if self.busy: return
        indexes = self.ports_box.curselection()
        if not indexes:
            messagebox.showinfo("NEXVARY", "اختر منفذ USB/COM من قائمة الأجهزة أولًا.")
            return
        selected = self.devices[indexes[0]].device
        self.busy = True
        self.status.set("جارٍ فحص المنفذ... لن نرسل أوامر تعديل إلى الشريحة")
        def worker():
            try:
                answer = probe(selected)
                self.root.after(0, lambda: self._finish(answer, None))
            except Exception:
                self.root.after(0, lambda: self._finish(None, "تعذر إكمال الفحص. تحقق من منفذ AT والتعريفات."))
        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, report, error):
        self.busy = False
        if error:
            self.status.set(error)
        else:
            self._show_report(report)

    def apdu_check(self):
        if self.busy: return
        indexes = self.ports_box.curselection()
        if not indexes:
            messagebox.showinfo("NEXVARY", "اختر منفذ AT أولًا.")
            return
        agreed = messagebox.askyesno(
            "اختبار البطاقة",
            "هل أنت مالك الشريحة أو مخول لاختبارها؟\n"
            "سيرسل البرنامج أمر SELECT MF ثابتًا لتغيير الملف المحدد مؤقتًا، "
            "دون قراءة الأسرار أو تعديل بيانات الشريحة. هل تتابع؟")
        if not agreed: return
        selected = self.devices[indexes[0]].device
        self.busy = True
        self.status.set("جارٍ اختبار APDU محلي محدد...")
        def worker():
            try:
                result = select_master_file(selected)
                self.root.after(0, lambda: self._apdu_finish(result, None))
            except LabError as exc:
                msg = str(exc)
                self.root.after(0, lambda: self._apdu_finish(None, msg))
            except Exception:
                self.root.after(0, lambda: self._apdu_finish(None, "APDU test unavailable"))
        threading.Thread(target=worker, daemon=True).start()

    def _apdu_finish(self, result, error):
        self.busy = False
        if error:
            self.status.set(error)
        else:
            self.status.set(f"اختبار SELECT MF: {result.status} / {result.value} — لا يثبت AKA")
            self.table.insert("", 0, values=(result.status, result.value, result.name))

    def export(self):
        if self.report is None:
            messagebox.showinfo("NEXVARY", "نفذ فحصًا أو افتح الوضع التجريبي أولًا.")
            return
        path = filedialog.asksaveasfilename(title="حفظ تقرير منقح",
                                            defaultextension=".json",
                                            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path: return
        try:
            content = to_csv(self.report) if path.lower().endswith(".csv") else to_json(self.report)
            with open(path, "x", encoding="utf-8", newline="") as handle:
                handle.write(content)
            self.status.set("تم حفظ تقرير منقح بدون أرقام الشريحة الكاملة")
        except FileExistsError:
            messagebox.showwarning("NEXVARY", "الملف موجود بالفعل؛ اختر اسمًا جديدًا.")
        except OSError:
            messagebox.showerror("NEXVARY", "تعذر كتابة الملف.")

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
