from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk


DEFAULT_ROOT = Path(r"C:\Users")


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
    for root, dirs, files in os.walk(directory, topdown=True, followlinks=False, onerror=lambda _error: None):
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


class FolderSizeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("User Folder Sizes")
        self.root.geometry("900x560")
        self.root.minsize(720, 420)

        self.current_path = DEFAULT_ROOT
        self.scan_token = 0
        self.scan_queue: queue.Queue[tuple[str, dict[str, object]]] = queue.Queue()
        self.item_paths: dict[str, Path] = {}
        self.item_sizes: dict[str, int] = {}

        self._build_ui()
        self.root.after(100, self._process_scan_queue)
        self.navigate_to(DEFAULT_ROOT)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(self.root, padding=(16, 16, 16, 8))
        top_frame.grid(row=0, column=0, sticky="nsew")
        top_frame.columnconfigure(1, weight=1)

        self.back_button = ttk.Button(top_frame, text="Back", command=self.go_back)
        self.back_button.grid(row=0, column=0, padx=(0, 12))

        self.path_var = tk.StringVar(value=str(DEFAULT_ROOT))
        path_label = ttk.Label(top_frame, textvariable=self.path_var, font=("Segoe UI", 11, "bold"))
        path_label.grid(row=0, column=1, sticky="w")

        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(top_frame, textvariable=self.status_var)
        status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        table_frame = ttk.Frame(self.root, padding=(16, 8, 16, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("folder", "size", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.tree.heading("folder", text="Folder")
        self.tree.heading("size", text="Size")
        self.tree.heading("status", text="Status")
        self.tree.column("folder", width=420, anchor="w")
        self.tree.column("size", width=140, anchor="e")
        self.tree.column("status", width=220, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self.open_selected_folder)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        bottom_frame = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        bottom_frame.grid(row=2, column=0, sticky="ew")
        bottom_frame.columnconfigure(0, weight=1)

        help_text = "Double-click a folder to calculate its child folders."
        help_label = ttk.Label(bottom_frame, text=help_text)
        help_label.grid(row=0, column=0, sticky="w")

        refresh_button = ttk.Button(bottom_frame, text="Refresh", command=lambda: self.navigate_to(self.current_path))
        refresh_button.grid(row=0, column=1)

    def navigate_to(self, path: Path) -> None:
        if not path.exists() or not path.is_dir():
            self.status_var.set(f"Directory not found: {path}")
            return

        self.current_path = path
        self.path_var.set(str(path))
        self.back_button.state(["!disabled"] if path != DEFAULT_ROOT else ["disabled"])
        self.scan_token += 1
        token = self.scan_token

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_paths.clear()
        self.item_sizes.clear()

        self.status_var.set(f"Scanning {path} ...")
        worker = threading.Thread(target=self._scan_directory, args=(path, token), daemon=True)
        worker.start()

    def go_back(self) -> None:
        if self.current_path == DEFAULT_ROOT:
            return
        parent = self.current_path.parent
        if len(str(parent)) < len(str(DEFAULT_ROOT)):
            parent = DEFAULT_ROOT
        self.navigate_to(parent)

    def open_selected_folder(self, _event: object | None = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        selected_item = selection[0]
        target_path = self.item_paths.get(selected_item)
        if target_path is None:
            return
        self.navigate_to(target_path)

    def _scan_directory(self, path: Path, token: int) -> None:
        try:
            subdirectories = sorted(
                [entry for entry in path.iterdir() if entry.is_dir()],
                key=lambda entry: entry.name.lower(),
            )
        except OSError as error:
            self.scan_queue.put(("error", {"token": token, "message": str(error)}))
            return

        if not subdirectories:
            self.scan_queue.put(("complete", {"token": token, "count": 0}))
            return

        for index, directory in enumerate(subdirectories, start=1):
            if token != self.scan_token:
                return
            status_text = f"Scanning {directory.name} ({index}/{len(subdirectories)})"
            self.scan_queue.put(("progress", {"token": token, "message": status_text}))
            size_bytes = get_directory_size(directory)
            self.scan_queue.put(
                (
                    "result",
                    {
                        "token": token,
                        "folder": directory.name,
                        "path": directory,
                        "size_bytes": size_bytes,
                        "size_text": format_size(size_bytes),
                    },
                )
            )

        self.scan_queue.put(("complete", {"token": token, "count": len(subdirectories)}))

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
                item_id = self.tree.insert(
                    "",
                    "end",
                    values=(payload["folder"], payload["size_text"], "Done"),
                )
                self.item_paths[item_id] = Path(str(payload["path"]))
                self.item_sizes[item_id] = int(payload["size_bytes"])
                self._sort_tree()
            elif message_type == "complete":
                count = int(payload["count"])
                if count == 0:
                    self.status_var.set(f"No subdirectories found under {self.current_path}")
                else:
                    self.status_var.set(f"Finished scanning {count} folders under {self.current_path}")
            elif message_type == "error":
                self.status_var.set(f"Scan failed: {payload['message']}")

        self.root.after(120, self._process_scan_queue)

    def _sort_tree(self) -> None:
        items = []
        for item_id in self.tree.get_children(""):
            size_value = self.item_sizes.get(item_id)
            if size_value is None:
                continue
            items.append((size_value, item_id))

        for position, (_, item_id) in enumerate(sorted(items, key=lambda item: item[0], reverse=True)):
            self.tree.move(item_id, "", position)


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("vista")
    FolderSizeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()