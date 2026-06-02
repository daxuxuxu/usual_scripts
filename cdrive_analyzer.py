"""
C 盘空间分析器（傻瓜版）
- 一打开就分析 C 盘，看看空间被什么占用了
- 每一项都用颜色和大白话标注：能不能删
- 安全第一：本工具只查看，永远不会删除任何文件
- 真要清理时，引导你使用 Windows 自带的安全清理工具
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# 起点：整个 C 盘
DEFAULT_ROOT = Path("C:\\")

# ---- 安全分类 ----
# SYSTEM   : 系统占用，不要删
# CLEANABLE: 可以安全清理
# PERSONAL : 你的个人文件，自己判断
# OTHER    : 其他，谨慎处理
CATEGORY_SYSTEM = "SYSTEM"
CATEGORY_CLEANABLE = "CLEANABLE"
CATEGORY_PERSONAL = "PERSONAL"
CATEGORY_OTHER = "OTHER"

CATEGORY_LABEL = {
    CATEGORY_SYSTEM: "系统占用 · 不要删",
    CATEGORY_CLEANABLE: "可以清理",
    CATEGORY_PERSONAL: "你的文件 · 自行判断",
    CATEGORY_OTHER: "其他 · 谨慎",
}

# Treeview 行颜色
CATEGORY_COLOR = {
    CATEGORY_SYSTEM: "#ffe0e0",     # 浅红：危险，别动
    CATEGORY_CLEANABLE: "#e1f5e1",  # 浅绿：可清理
    CATEGORY_PERSONAL: "#e2eefc",   # 浅蓝：个人文件
    CATEGORY_OTHER: "#f2f2f2",      # 浅灰：其他
}


def format_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def get_directory_size(directory: Path) -> int:
    total_size = 0
    for root, dirs, files in os.walk(directory, topdown=True, followlinks=False, onerror=lambda _e: None):
        dirs[:] = [name for name in dirs if not Path(root, name).is_symlink()]
        for file_name in files:
            file_path = Path(root, file_name)
            try:
                if file_path.is_symlink():
                    continue
                total_size += file_path.stat().st_size
            except OSError:
                continue
    return total_size


def classify(path: Path, name: str, is_file: bool) -> tuple[str, str]:
    """返回 (分类, 一句话建议)。"""
    lower_name = name.lower()
    lower_path = str(path).lower()

    # 1) 特殊的系统大文件（C 盘根目录常见的"内存黑洞"）
    if lower_name == "hiberfil.sys":
        return CATEGORY_SYSTEM, (
            "休眠文件，大小约等于你的内存。如果你从不用‘休眠’功能，"
            "可以用管理员身份运行命令 powercfg /h off 安全释放这块空间。"
        )
    if lower_name == "pagefile.sys":
        return CATEGORY_SYSTEM, "虚拟内存文件，由 Windows 自动管理，请不要删除。"
    if lower_name == "swapfile.sys":
        return CATEGORY_SYSTEM, "系统交换文件，由 Windows 自动管理，请不要删除。"
    if lower_name in ("dumpstack.log", "dumpstack.log.tmp"):
        return CATEGORY_SYSTEM, "系统日志文件，由 Windows 管理，建议不要手动删除。"

    # 2) 可以安全清理的目录（垃圾/缓存/更新残留）
    cleanable_markers = [
        r"\appdata\local\temp",
        r"\windows\temp",
        r"\windows\softwaredistribution\download",
        r"\windows\prefetch",
        r"\appdata\local\microsoft\windows\inetcache",
        r"\appdata\local\microsoft\windows\explorer",
        r"\inetcache",
    ]
    if lower_name == "temp" or lower_path.endswith(r"\temp"):
        return CATEGORY_CLEANABLE, "临时文件夹，里面一般是垃圾文件，可用‘磁盘清理’安全清除。"
    if "$recycle.bin" in lower_path:
        return CATEGORY_CLEANABLE, "回收站。直接清空回收站即可释放空间。"
    for marker in cleanable_markers:
        if marker in lower_path:
            return CATEGORY_CLEANABLE, "缓存/更新残留，可用 Windows‘磁盘清理’安全清除。"

    # 3) 系统关键目录（不要手动删）
    if lower_name == "windows" or r"\windows\winsxs" in lower_path:
        if r"\windows\winsxs" in lower_path:
            return CATEGORY_SYSTEM, (
                "Windows 组件库（WinSxS）。看着很大但请勿手动删除，"
                "可用‘磁盘清理’或 DISM 命令安全清理。"
            )
        return CATEGORY_SYSTEM, "Windows 系统核心文件夹，删除会导致系统无法启动，绝对不要动。"
    if lower_name in ("program files", "program files (x86)"):
        return CATEGORY_SYSTEM, "已安装软件的程序文件。要清理请到‘设置→应用’里正常卸载软件。"
    if lower_name == "programdata":
        return CATEGORY_SYSTEM, "软件的公共数据，多为程序运行所需，不建议手动删除。"
    if lower_name in ("system volume information", "recovery", "$windows.~bt", "$windows.~ws", "perflogs", "msocache"):
        return CATEGORY_SYSTEM, "系统保留文件夹，请不要手动删除。"
    if r"\windows\installer" in lower_path:
        return CATEGORY_SYSTEM, "软件安装缓存，删除会导致软件无法更新/卸载，不要手动删。"

    # 4) 你的个人文件
    personal_folders = (
        "desktop", "documents", "downloads", "pictures",
        "videos", "music", "favorites", "onedrive", "contacts",
        "桌面", "文档", "下载", "图片", "视频", "音乐",
    )
    if lower_path.startswith("c:\\users"):
        if lower_name in personal_folders:
            return CATEGORY_PERSONAL, "你自己的文件。可以打开看看，把不需要的大文件自行删除或转移到其他盘。"
        if lower_name == "users":
            return CATEGORY_PERSONAL, "所有用户的个人文件夹。大多是你自己的资料，双击进去看看占用最大的是什么。"
        return CATEGORY_PERSONAL, "用户数据。请自行判断是否需要，删除前先确认不是软件配置。"

    # 5) 其他
    if is_file:
        return CATEGORY_OTHER, "普通文件。请自行确认用途后再决定是否删除。"
    return CATEGORY_OTHER, "用途不明的文件夹，删除前请先确认，拿不准就别动。"


class CDriveAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("C 盘空间分析器（安全版 · 只查看不删除）")
        self.root.geometry("1000x640")
        self.root.minsize(820, 520)

        self.current_path = DEFAULT_ROOT
        self.scan_token = 0
        self.scan_queue: queue.Queue[tuple[str, dict[str, object]]] = queue.Queue()
        self.item_paths: dict[str, Path] = {}
        self.item_sizes: dict[str, int] = {}
        self.item_advice: dict[str, str] = {}
        self.item_is_file: dict[str, bool] = {}
        self._scanning = False
        self._spinner_index = 0

        self._build_ui()
        self.root.after(100, self._process_scan_queue)
        self.navigate_to(DEFAULT_ROOT)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # 顶部：标题 + 安全提示
        header = ttk.Frame(self.root, padding=(16, 14, 16, 6))
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="C 盘空间分析器", font=("Microsoft YaHei", 15, "bold"))
        title.grid(row=0, column=0, sticky="w")

        safe_tip = ttk.Label(
            header,
            text="安全提示：本工具只帮你查看空间占用，绝不会删除任何文件。颜色越红越不能动。",
            foreground="#b00000",
            font=("Microsoft YaHei", 10),
        )
        safe_tip.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.disk_var = tk.StringVar(value="正在读取磁盘信息...")
        disk_label = ttk.Label(header, textvariable=self.disk_var, font=("Microsoft YaHei", 10, "bold"))
        disk_label.grid(row=2, column=0, sticky="w", pady=(6, 0))

        # 工具条：路径 + 返回/刷新
        toolbar = ttk.Frame(self.root, padding=(16, 4, 16, 6))
        toolbar.grid(row=1, column=0, sticky="nsew")
        toolbar.columnconfigure(2, weight=1)

        self.back_button = ttk.Button(toolbar, text="← 返回上一级", command=self.go_back)
        self.back_button.grid(row=0, column=0, padx=(0, 8))

        refresh_button = ttk.Button(toolbar, text="刷新", command=lambda: self.navigate_to(self.current_path))
        refresh_button.grid(row=0, column=1, padx=(0, 12))

        self.path_var = tk.StringVar(value=str(DEFAULT_ROOT))
        path_label = ttk.Label(toolbar, textvariable=self.path_var, font=("Consolas", 11))
        path_label.grid(row=0, column=2, sticky="w")

        # 中间：表格
        table_frame = ttk.Frame(self.root, padding=(16, 4, 16, 6))
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("name", "size", "percent", "category", "advice")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.tree.heading("name", text="名称")
        self.tree.heading("size", text="大小")
        self.tree.heading("percent", text="占比（越长越大）")
        self.tree.heading("category", text="能不能删")
        self.tree.heading("advice", text="说明 / 建议")
        self.tree.column("name", width=210, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("percent", width=180, anchor="w")
        self.tree.column("category", width=140, anchor="w")
        self.tree.column("advice", width=380, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self.open_selected_folder)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        for category, color in CATEGORY_COLOR.items():
            self.tree.tag_configure(category, background=color)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 选中项的详细建议
        self.detail_var = tk.StringVar(value="点一下某一行，这里会显示它是什么、能不能删。")
        detail_label = ttk.Label(
            self.root,
            textvariable=self.detail_var,
            padding=(16, 6),
            font=("Microsoft YaHei", 10),
            wraplength=960,
            justify="left",
        )
        detail_label.grid(row=3, column=0, sticky="nsew")

        # 状态栏：醒目的分析进度横幅（扫描时橙黄闪动，完成后变绿）
        self.status_bar = tk.Frame(self.root, bg="#d4edda")
        self.status_bar.grid(row=4, column=0, sticky="nsew")
        self.status_bar.columnconfigure(1, weight=1)

        self.spinner_label = tk.Label(
            self.status_bar, text="✓", bg="#d4edda", fg="#155724",
            font=("Microsoft YaHei", 14, "bold"), width=3,
        )
        self.spinner_label.grid(row=0, column=0, padx=(12, 6), pady=10)

        self.status_var = tk.StringVar(value="准备就绪")
        self.status_label = tk.Label(
            self.status_bar, textvariable=self.status_var, bg="#d4edda", fg="#155724",
            font=("Microsoft YaHei", 12, "bold"), anchor="w", justify="left",
        )
        self.status_label.grid(row=0, column=1, sticky="ew", pady=10)

        self.progress = ttk.Progressbar(self.status_bar, mode="indeterminate", length=220)
        self.progress.grid(row=0, column=2, padx=(6, 12), pady=10)

        # 底部：安全清理引导按钮（都是调用 Windows 自带工具）
        bottom = ttk.Frame(self.root, padding=(16, 6, 16, 14))
        bottom.grid(row=5, column=0, sticky="nsew")

        ttk.Label(bottom, text="想清理？请用 Windows 自带的安全工具：", font=("Microsoft YaHei", 10)).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )

        ttk.Button(bottom, text="打开 存储设置", command=self.open_storage_settings).grid(row=1, column=0, padx=(0, 8))
        ttk.Button(bottom, text="打开 磁盘清理", command=self.open_disk_cleanup).grid(row=1, column=1, padx=(0, 8))
        ttk.Button(bottom, text="在资源管理器中打开当前文件夹", command=self.open_in_explorer).grid(row=1, column=2, padx=(0, 8))

    # ---- 磁盘总览 ----
    def update_disk_overview(self) -> None:
        try:
            usage = shutil.disk_usage("C:\\")
            used = usage.total - usage.free
            text = (
                f"C 盘总容量 {format_size(usage.total)}  |  "
                f"已用 {format_size(used)}  |  可用 {format_size(usage.free)}"
            )
            self.disk_var.set(text)
        except OSError:
            self.disk_var.set("无法读取磁盘信息")

    # ---- 导航 ----
    def navigate_to(self, path: Path) -> None:
        if not path.exists() or not path.is_dir():
            self.status_var.set(f"找不到目录：{path}")
            return

        self.update_disk_overview()
        self.current_path = path
        self.path_var.set(str(path))
        self.back_button.state(["disabled"] if self._is_root(path) else ["!disabled"])
        self.scan_token += 1
        token = self.scan_token

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_paths.clear()
        self.item_sizes.clear()
        self.item_advice.clear()
        self.item_is_file.clear()
        self.detail_var.set("点一下某一行，这里会显示它是什么、能不能删。")

        self._start_scanning_ui(f"正在分析 {path} ，请稍候（大文件夹需要一点时间）...")
        worker = threading.Thread(target=self._scan_directory, args=(path, token), daemon=True)
        worker.start()

    # ---- 醒目的扫描状态 ----
    def _start_scanning_ui(self, message: str) -> None:
        self._scanning = True
        self.status_var.set(message)
        self.status_bar.configure(bg="#ffe08a")
        self.spinner_label.configure(bg="#ffe08a", fg="#8a5a00")
        self.status_label.configure(bg="#ffe08a", fg="#8a5a00")
        try:
            self.progress.grid()
            self.progress.start(12)
        except tk.TclError:
            pass
        self._animate_spinner()

    def _stop_scanning_ui(self, message: str) -> None:
        self._scanning = False
        self.status_var.set(message)
        self.status_bar.configure(bg="#d4edda")
        self.spinner_label.configure(bg="#d4edda", fg="#155724", text="✓")
        self.status_label.configure(bg="#d4edda", fg="#155724")
        try:
            self.progress.stop()
        except tk.TclError:
            pass

    def _animate_spinner(self) -> None:
        if not self._scanning:
            return
        frames = "◐◓◑◒"
        self._spinner_index = (self._spinner_index + 1) % len(frames)
        self.spinner_label.configure(text=frames[self._spinner_index])
        self.root.after(150, self._animate_spinner)

    @staticmethod
    def _is_root(path: Path) -> bool:
        return str(path).rstrip("\\").lower() == "c:"

    def go_back(self) -> None:
        if self._is_root(self.current_path):
            return
        self.navigate_to(self.current_path.parent)

    def open_selected_folder(self, _event: object | None = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = selection[0]
        target = self.item_paths.get(item)
        if target is None:
            return
        if self.item_is_file.get(item, False):
            # 文件：在资源管理器里定位它，绝不删除
            try:
                os.system(f'explorer /select,"{target}"')
            except OSError:
                pass
            return
        self.navigate_to(target)

    def on_select(self, _event: object | None = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = selection[0]
        name = self.tree.set(item, "name")
        category = self.tree.set(item, "category")
        advice = self.item_advice.get(item, "")
        self.detail_var.set(f"【{name}】 {category}\n{advice}")

    # ---- 扫描 ----
    def _scan_directory(self, path: Path, token: int) -> None:
        try:
            entries = list(os.scandir(path))
        except OSError as error:
            self.scan_queue.put(("error", {"token": token, "message": str(error)}))
            return

        if not entries:
            self.scan_queue.put(("complete", {"token": token, "count": 0}))
            return

        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if token != self.scan_token:
                return
            entry_path = Path(entry.path)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False

            self.scan_queue.put(
                ("progress", {"token": token, "message": f"正在分析 {entry.name} ({index}/{total})"})
            )

            if is_dir:
                size_bytes = get_directory_size(entry_path)
                is_file = False
            else:
                try:
                    size_bytes = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size_bytes = 0
                is_file = True

            category, advice = classify(entry_path, entry.name, is_file)
            self.scan_queue.put(
                (
                    "result",
                    {
                        "token": token,
                        "name": entry.name,
                        "path": str(entry_path),
                        "size_bytes": size_bytes,
                        "size_text": format_size(size_bytes),
                        "category": category,
                        "category_text": CATEGORY_LABEL[category],
                        "advice": advice,
                        "is_file": is_file,
                    },
                )
            )

        self.scan_queue.put(("complete", {"token": token, "count": total}))

    def _process_scan_queue(self) -> None:
        while True:
            try:
                message_type, payload = self.scan_queue.get_nowait()
            except queue.Empty:
                break

            token = int(payload["token"])
            if token != self.scan_token:
                continue

            if message_type == "progress":
                self.status_var.set(str(payload["message"]))
            elif message_type == "result":
                category = str(payload["category"])
                item_id = self.tree.insert(
                    "",
                    "end",
                    values=(
                        payload["name"],
                        payload["size_text"],
                        "",
                        payload["category_text"],
                        payload["advice"],
                    ),
                    tags=(category,),
                )
                self.item_paths[item_id] = Path(str(payload["path"]))
                self.item_sizes[item_id] = int(payload["size_bytes"])
                self.item_advice[item_id] = str(payload["advice"])
                self.item_is_file[item_id] = bool(payload["is_file"])
                self._sort_tree()
            elif message_type == "complete":
                count = int(payload["count"])
                if count == 0:
                    self._stop_scanning_ui(f"{self.current_path} 下没有可显示的内容")
                else:
                    self._stop_scanning_ui(
                        f"分析完成：共 {count} 项。颜色越红越不能动；双击文件夹可继续往下看。"
                    )
            elif message_type == "error":
                self._stop_scanning_ui(f"无法读取该目录（可能需要权限）：{payload['message']}")

        self.root.after(120, self._process_scan_queue)

    def _sort_tree(self) -> None:
        items = []
        for item_id in self.tree.get_children(""):
            size_value = self.item_sizes.get(item_id)
            if size_value is None:
                continue
            items.append((size_value, item_id))

        total = sum(size for size, _ in items)
        for position, (size_value, item_id) in enumerate(
            sorted(items, key=lambda pair: pair[0], reverse=True)
        ):
            self.tree.move(item_id, "", position)
            self.tree.set(item_id, "percent", self._make_percent_text(size_value, total))

    @staticmethod
    def _make_percent_text(size_value: int, total: int) -> str:
        if total <= 0:
            return ""
        ratio = size_value / total
        percent = ratio * 100
        filled = int(round(ratio * 10))
        filled = max(0, min(10, filled))
        bar = "█" * filled + "░" * (10 - filled)
        return f"{bar} {percent:.1f}%"

    # ---- 底部：调用 Windows 自带安全工具 ----
    def open_storage_settings(self) -> None:
        try:
            os.startfile("ms-settings:storagesense")
        except OSError:
            messagebox.showinfo("提示", "无法自动打开存储设置，请手动打开：设置 → 系统 → 存储。")

    def open_disk_cleanup(self) -> None:
        try:
            os.startfile("cleanmgr.exe")
        except OSError:
            messagebox.showinfo("提示", "无法自动打开磁盘清理，请在开始菜单搜索‘磁盘清理’。")

    def open_in_explorer(self) -> None:
        try:
            os.startfile(str(self.current_path))
        except OSError:
            messagebox.showinfo("提示", f"无法打开：{self.current_path}")


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    CDriveAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
