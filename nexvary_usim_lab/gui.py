"""RTL-aware Tk desktop UI for safe USB-USIM inventory."""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import LabError, demo, pcsc_readers, ports, probe, select_master_file, to_csv, to_json
from .catalog import identification_hint

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
        self.root.geometry("1030x710")
        self.root.minsize(780, 560)
        self.root.configure(bg=BG)
        self.devices = []
        self.report = None
        self.busy = False
        self.status = tk.StringVar(value="جاهز — لم يتم الاتصال بأي جهاز")
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

        self._label(devices, "الأجهزة / منافذ COM", 13, bold=True).pack(fill="x", pady=(0, 10))
        self.ports_box = tk.Listbox(devices, bg=FIELD, fg=FG, selectbackground="#276078",
                                    selectforeground="white", borderwidth=0,
                                    font=("Consolas", 10), activestyle="none", height=15,
                                    exportselection=False)
        self.ports_box.pack(fill="both", expand=True)
        self._label(devices, "اختر منفذ AT الخاص بالمودم، وليس منفذ التخزين.", 9, SOFT).pack(fill="x", pady=(10, 0))
        self._label(devices, "قد تظهر للفلاشة أكثر من واجهة COM.", 9, SOFT).pack(fill="x")

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
        ttk.Scrollbar(frame, command=self.table.yview, orient="vertical",
                      style="N.Vertical.TScrollbar").pack(side="right", fill="y")
        self.table.configure(yscrollcommand=lambda first, last: None)
        footer = tk.Frame(self.root, bg=BG, padx=22, pady=13)
        footer.pack(fill="x")
        self._label(footer, "التوافق مع AKA / PCSC / ePDG / IMS غير مثبت حتى إجراء اختبارات حقيقية.", 9, SOFT).pack(side="right")
        tk.Label(footer, textvariable=self.status, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10)).pack(side="left")

    def refresh(self):
        if self.busy: return
        try:
            self.devices = ports()
        except LabError as exc:
            self.devices = []
            self.status.set(str(exc))
        self.ports_box.delete(0, "end")
        for item in self.devices:
            self.ports_box.insert("end", f"{item.device} | {identification_hint(item.description, item.manufacturer, item.vid)}")
        if self.devices:
            self.ports_box.selection_set(0)
            self.status.set(f"تم اكتشاف {len(self.devices)} منفذ — ليست كلها بالضرورة مودمات")
        else:
            self.status.set("لا توجد منافذ متاحة — تحقق من التعريفات أو جرّب الوضع التجريبي")

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
