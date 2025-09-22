#!/usr/bin/env python3
"""
Oai2Ollama GUI - OpenAI to Ollama API Bridge with GUI
A desktop application that wraps OpenAI-compatible API and exposes Ollama-compatible API
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Menu
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
import json
import os
import sys
import threading
import asyncio
import logging
from datetime import datetime
from pathlib import Path
import queue
import webbrowser
from typing import List, Optional
import subprocess
import signal
import time
import gettext
import builtins

# pip install ttkbootstrap fastapi uvicorn httpx httpx[http2] pydantic pillow pystray

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn
import httpx
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item

# --- 多语言设置 ---
# 将 _ 安装到 builtins, 使其在所有模块中可用
# 默认使用 gettext, LocaleManager 将会覆盖它
builtins._ = gettext.gettext

class LocaleManager:
    """管理应用程序的语言环境"""
    def __init__(self, locale_dir='locales'):
        if getattr(sys, 'frozen', False):
            self.locale_dir = Path(sys._MEIPASS) / locale_dir
        else:
            self.locale_dir = Path(__file__).parent / locale_dir
        
        self.supported_languages = self.get_supported_languages()
        self.current_lang = 'en'

    def get_supported_languages(self) -> dict:
        """扫描locale目录以查找支持的语言"""
        languages = {'en_US': 'English'} # 默认支持英文
        if not self.locale_dir.is_dir():
            return languages
        for lang_dir in self.locale_dir.iterdir():
            if (lang_dir / "LC_MESSAGES" / "messages.mo").exists():
                # 通常需要一个更稳健的方法来获取语言名称，这里我们用目录名
                languages[lang_dir.name] = lang_dir.name.upper() # 示例: ZH, DE
        return languages

    def switch_language(self, lang: str):
        """切换应用程序语言"""
        if lang not in self.supported_languages:
            lang = 'en_US'
        self.current_lang = lang
        try:
            translation = gettext.translation('messages', localedir=str(self.locale_dir), languages=[lang])
            builtins._ = translation.gettext
        except FileNotFoundError:
            # 如果找不到 .mo 文件，则回退到默认的 no-op 翻译
            builtins._ = gettext.gettext
            print(f"Warning: Could not find locale data for language: {lang}")

# 初始化语言管理器
locale_manager = LocaleManager()

# --- 日志和版本 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

VERSION = "1.0.1"
OLLAMA_VERSION = "0.11.4"
ENABLE_TRAY = False

# 全局变量
ENABLE_TRAY = False  # 是否启用系统托盘功能

class Settings:
    """应用配置设置"""
    def __init__(self):
        self.api_key = ""
        self.base_url = ""
        self.capabilities = []
        self.models = []
        self.host = "localhost"
        self.port = 11434
        self.auto_start = False
        self.minimize_to_tray = True
        self.theme = "darkly"
        self.start_minimized = False
        self.language = "en" # 新增语言设置
        # 拦截模型列表配置
        self.intercept_models_enabled = False
        self.intercepted_models = []  # 存储被拦截的模型列表

class Oai2OllamaServer:
    """OpenAI to Ollama API Bridge Server"""

    def __init__(self, settings: Settings, log_callback=None):
        self.settings = settings
        self.log_callback = log_callback
        self.app = FastAPI(title="Oai2Ollama", version=VERSION)
        self.server = None
        self.server_thread = None
        self.is_running = False
        self._setup_routes()

    def log(self, message, level="INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(f"[{level}] {message}")
        logger.log(getattr(logging, level), message)

    def _create_client(self) -> httpx.AsyncClient:
        """创建HTTP客户端"""
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            headers=headers,
            timeout=60,
            http2=True,
            follow_redirects=True
        )

    def _setup_routes(self):
        """设置API路由"""

        @self.app.get("/")
        async def root():
            """根路径"""
            return {
                "service": "Oai2Ollama",
                "version": VERSION,
                "status": "running"
            }

        @self.app.get("/api/tags")
        async def get_models():
            """获取模型列表 (Ollama格式)"""
            if self.settings.intercept_models_enabled:
                self.log("Intercepting /api/tags, returning models from local config.", "INFO")
                enabled_models = [m for m in self.settings.intercepted_models if m.get('enabled', False)]
                ollama_models = [{
                    "name": model["id"],
                    "model": model["id"],
                    "modified_at": datetime.now().isoformat(),
                    "size": 0,
                    "digest": "",
                    "details": {
                        "format": "gguf",
                        "family": "custom",
                        "families": None,
                        "parameter_size": "N/A",
                        "quantization_level": "Q0"
                     }
                } for model in enabled_models]
                return {"models": ollama_models}

            try:
                async with self._create_client() as client:
                    res = await client.get("/models")
                    res.raise_for_status()
                    data = res.json()
                    models_map = {}
                    if "data" in data:
                        for model in data["data"]:
                            model_id = model["id"]
                            models_map[model_id] = {"name": model_id, "model": model_id}
                    for model_name in self.settings.models:
                        models_map[model_name] = {"name": model_name, "model": model_name}
                    return {"models": list(models_map.values())}
            except Exception as e:
                self.log(f"Error fetching models: {e}", "ERROR")
                return {"models": []}

        @self.app.post("/api/show")
        async def show_model(request: Request):
            """显示模型信息"""
            if self.settings.intercept_models_enabled:
                req_data = await request.json()
                model_name = req_data.get("name", "unknown model")
                self.log(f"Intercepting /api/show for model: {model_name}", "INFO")
                found_model = next((m for m in self.settings.intercepted_models if m.get('id') == model_name), None)
                if found_model:
                    return {
                        "model_info": {
                            "general.architecture": "transformer",
                            "general.name": found_model.get("name", model_name),
                        },
                        "details": {"family": found_model.get("owned_by", "custom")},
                        "capabilities": ["completion"] + self.settings.capabilities
                    }
                else:
                    return {
                        "model_info": {"general.architecture": "CausalLM"},
                        "capabilities": ["completion"] + self.settings.capabilities
                    }
            return {
                "model_info": {"general.architecture": "CausalLM"},
                "capabilities": ["completion"] + self.settings.capabilities
            }

        @self.app.get("/v1/models")
        async def list_models():
            """列出模型 (OpenAI格式)"""
            if self.settings.intercept_models_enabled:
                self.log("Intercepting /v1/models, returning models from local config.", "INFO")
                enabled_models = [m for m in self.settings.intercepted_models if m.get('enabled', False)]
                openai_models = [{
                    "id": model["id"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": model.get("owned_by", "user")
                } for model in enabled_models]
                return {"object": "list", "data": openai_models}
            
            try:
                async with self._create_client() as client:
                    res = await client.get("/models")
                    res.raise_for_status()
                    return res.json()
            except Exception as e:
                self.log(f"Error listing models: {e}", "ERROR")
                return {"data": [], "object": "list"}

        @self.app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            """聊天完成端点"""
            try:
                data = await request.json()
                if data.get("stream", False):
                    async def stream():
                        async with self._create_client() as client:
                            async with client.stream("POST", "/chat/completions", json=data) as response:
                                async for chunk in response.aiter_bytes():
                                    yield chunk
                    return StreamingResponse(stream(), media_type="text/event-stream")
                else:
                    async with self._create_client() as client:
                        res = await client.post("/chat/completions", json=data)
                        res.raise_for_status()
                        return res.json()
            except Exception as e:
                self.log(f"Error in chat completions: {e}", "ERROR")
                return {"error": str(e)}, 500

        @self.app.get("/api/version")
        async def ollama_version():
            """Ollama版本信息"""
            return {"version": OLLAMA_VERSION}

    def start(self):
        """启动服务器"""
        if self.is_running:
            return
        self.is_running = True
        self.log(f"Starting server on {self.settings.host}:{self.settings.port}", "INFO")
        self.log(f"Base URL: {self.settings.base_url}", "INFO")
        self.log(f"Capabilities: {self.settings.capabilities}", "INFO")
        self.log(f"Extra models: {self.settings.models}", "INFO")
        def run_server():
            try:
                config = uvicorn.Config(
                    self.app, host=self.settings.host, port=self.settings.port, log_level="info"
                )
                self.server = uvicorn.Server(config)
                self.server.run()
            except Exception as e:
                self.log(f"Server error: {e}", "ERROR")
                self.is_running = False
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

    def stop(self):
        """停止服务器"""
        if not self.is_running:
            return
        self.is_running = False
        self.log("Stopping server...", "INFO")
        if self.server:
            self.server.should_exit = True
            self.server = None
        self.log("Server stopped", "INFO")

class ModelInterceptWindow(tk.Toplevel):
    """模型拦截设置窗口"""
    def __init__(self, parent, settings_manager, on_save_callback):
        super().__init__(parent)
        self.parent = parent
        self.settings = settings_manager
        self.on_save_callback = on_save_callback
        
        self.transient(parent)
        self.update_idletasks()
        win_width, win_height = 900, 700
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        x = parent_x + (parent_width - win_width) // 2
        y = parent_y + (parent_height - win_height) // 2
        self.geometry(f"{win_width}x{win_height}+{x}+{y}")
        self.minsize(800, 500)
        
        self.all_intercepted_models = []
        self.is_filtering = False
        self.filtered_models = []
        
        self.create_ui()
        self.update_ui_texts()
        self.load_intercepted_models()
        
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def create_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=BOTH, expand=True)
        self._create_toolbar(main_frame)
        self._create_model_list_view(main_frame)
        self._create_bottom_buttons(main_frame)
        self._create_context_menu()

    def update_ui_texts(self):
        self.title(_("Intercept Model List Settings"))
        self.list_frame.config(text=_("Model List"))
        self.fetch_btn.config(text=_("🔄 Get Model List"))
        self.add_btn.config(text=_("➕ Add Model"))
        self.delete_btn.config(text=_("🗑️ Delete Selected"))
        self.advanced_edit_btn.config(text=_("📝 Advanced Edit"))
        self.clear_filter_btn.config(text=_("❌ Clear Filter"))
        self.deselect_all_btn.config(text=_("☐ Deselect All"))
        self.select_all_btn.config(text=_("☑️ Select All"))
        self.save_btn.config(text=_("💾 Save"))
        self.cancel_btn.config(text=_("❌ Cancel"))
        
        # Treeview Headings
        self.model_tree.heading("enabled", text=_("Enabled"))
        self.model_tree.heading("model_id", text=_("Model ID"))
        self.model_tree.heading("model_name", text=_("Model Name"))
        self.model_tree.heading("object_type", text=_("Type"))
        self.model_tree.heading("owned_by", text=_("Owner"))
        
        # Context Menu
        self.context_menu.entryconfig(0, label=_("✅ Enable Selected"))
        self.context_menu.entryconfig(1, label=_("❌ Disable Selected"))
        self.context_menu.entryconfig(3, label=_("📝 Copy Model ID"))
        self.context_menu.entryconfig(5, label=_("🗑️ Delete Selected"))

    def _create_toolbar(self, parent):
        toolbar_frame = ttk.Frame(parent)
        toolbar_frame.pack(fill=X, pady=(0, 10))
        self.fetch_btn = ttk.Button(toolbar_frame, command=self.fetch_models_from_api, bootstyle=PRIMARY)
        self.fetch_btn.pack(side=LEFT, padx=(0, 5))
        self.add_btn = ttk.Button(toolbar_frame, command=self.add_custom_model)
        self.add_btn.pack(side=LEFT, padx=(0, 5))
        self.delete_btn = ttk.Button(toolbar_frame, command=self.delete_selected_models, bootstyle=DANGER)
        self.delete_btn.pack(side=LEFT, padx=(0, 5))
        self.advanced_edit_btn = ttk.Button(toolbar_frame, command=self.open_advanced_edit)
        self.advanced_edit_btn.pack(side=LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar_frame, textvariable=self.search_var, width=25)
        search_entry.pack(side=LEFT, padx=(10, 5))
        self.search_var.trace('w', self.on_search_text_changed)
        search_entry.bind("<Return>", lambda event: self.filter_models())
        search_entry.bind("<Escape>", lambda event: self.clear_filter())
        self.clear_filter_btn = ttk.Button(toolbar_frame, command=self.clear_filter)
        self.clear_filter_btn.pack(side=LEFT)
        self.deselect_all_btn = ttk.Button(toolbar_frame, command=self.deselect_all_models)
        self.deselect_all_btn.pack(side=RIGHT)
        self.select_all_btn = ttk.Button(toolbar_frame, command=self.select_all_models)
        self.select_all_btn.pack(side=RIGHT, padx=5)

    def _create_model_list_view(self, parent):
        self.list_frame = ttk.LabelFrame(parent, padding=5)
        self.list_frame.pack(fill=BOTH, expand=True, pady=(0, 10))
        columns = ("enabled", "model_id", "model_name", "object_type", "owned_by")
        self.model_tree = ttk.Treeview(self.list_frame, columns=columns, show="headings", height=15)
        for col in columns: self.model_tree.heading(col, text=col)
        self.model_tree.column("enabled", width=60, minwidth=60, anchor='center')
        self.model_tree.column("model_id", width=200, minwidth=150)
        self.model_tree.column("model_name", width=200, minwidth=150)
        self.model_tree.column("object_type", width=80, minwidth=80)
        self.model_tree.column("owned_by", width=120, minwidth=100)
        scrollbar_y = ttk.Scrollbar(self.list_frame, orient=VERTICAL, command=self.model_tree.yview)
        scrollbar_x = ttk.Scrollbar(self.list_frame, orient=HORIZONTAL, command=self.model_tree.xview)
        self.model_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        self.model_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        self.list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.model_tree.bind("<Double-1>", self.on_model_double_click)
        self.model_tree.bind("<Button-3>", self.show_context_menu)

    def _create_bottom_buttons(self, parent):
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=X)
        self.save_btn = ttk.Button(button_frame, command=self.save_model_intercept_config, bootstyle=SUCCESS)
        self.save_btn.pack(side=RIGHT, padx=(5, 0))
        self.cancel_btn = ttk.Button(button_frame, command=self.destroy)
        self.cancel_btn.pack(side=RIGHT)

    def _create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="", command=self.enable_selected_items)
        self.context_menu.add_command(label="", command=self.disable_selected_items)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="", command=self.copy_selected_model_id)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="", command=self.delete_selected_models)
    
    # ... (rest of the methods for ModelInterceptWindow)
    def refresh_model_tree(self):
        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        models_to_show = self.filtered_models if self.is_filtering else self.all_intercepted_models
        models_to_show.sort(key=lambda x: (not x.get('enabled', False), x.get('id', '')))
        for model in models_to_show:
            self.insert_model_into_tree(model)

    def insert_model_into_tree(self, model_data):
        self.model_tree.insert("", "end", iid=model_data.get('id', ''), values=(
            "✔" if model_data.get("enabled", False) else "✖",
            model_data.get("id", ""),
            model_data.get("name", model_data.get("id", "")),
            model_data.get("object", "model"),
            model_data.get("owned_by", "unknown")
        ))
        
    def load_intercepted_models(self):
        self.all_intercepted_models = [dict(m) for m in self.settings.intercepted_models]
        self.is_filtering, self.filtered_models = False, []
        self.refresh_model_tree()

    def on_search_text_changed(self, *args):
        if hasattr(self, '_filter_timer'): self.after_cancel(self._filter_timer)
        self._filter_timer = self.after(300, self.filter_models)

    def filter_models(self):
        search_term = self.search_var.get().strip().lower()
        if not search_term:
            self.clear_filter()
            return
        self.is_filtering = True
        keywords = [kw.strip() for kw in search_term.split() if kw.strip()]
        self.filtered_models = []
        for model in self.all_intercepted_models:
            model_id, model_name, owned_by = model.get("id", "").lower(), model.get("name", "").lower(), model.get("owned_by", "").lower()
            if all(keyword in model_id or keyword in model_name or keyword in owned_by for keyword in keywords):
                self.filtered_models.append(model)
        self.refresh_model_tree()

    def clear_filter(self):
        self.search_var.set("")
        self.is_filtering, self.filtered_models = False, []
        self.refresh_model_tree()

    def fetch_models_from_api(self):
        if not self.settings.base_url:
            messagebox.showwarning(_("Warning"), _("Please set the Base URL in the main window first"), parent=self)
            return
        loading_window = tk.Toplevel(self)
        loading_window.title(_("Please wait"))
        loading_window.geometry("300x100")
        loading_window.transient(self)
        loading_window.grab_set()
        x, y = self.winfo_x() + (self.winfo_width() - 300) // 2, self.winfo_y() + (self.winfo_height() - 100) // 2
        loading_window.geometry(f"300x100+{x}+{y}")
        ttk.Label(loading_window, text=_("Fetching model list...")).pack(pady=20)
        progress = ttk.Progressbar(loading_window, mode='indeterminate')
        progress.pack(pady=5, padx=20, fill=X)
        progress.start()
        def fetch_in_thread():
            try:
                import httpx
                api_url = self.settings.base_url.rstrip('/') + '/models'
                headers = {"Authorization": f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}
                with httpx.Client(headers=headers, timeout=30) as client:
                    response = client.get(api_url)
                    response.raise_for_status()
                    data = response.json()
                    models = data.get('data', [])
                    self.after(0, lambda: self.update_models_from_api(models))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(_("Error"), _("Failed to fetch model list: {error}").format(error=e), parent=self))
            finally:
                self.after(0, loading_window.destroy)
        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def update_models_from_api(self, api_models):
        existing_models_map = {model['id']: model for model in self.all_intercepted_models}
        api_models_map = {model['id']: model for model in api_models}
        for model_id, api_model in api_models_map.items():
            if model_id in existing_models_map:
                existing_models_map[model_id].update({
                    'name': api_model.get('name', model_id),
                    'object': api_model.get('object', 'model'),
                    'owned_by': api_model.get('owned_by', 'unknown')
                })
            else:
                existing_models_map[model_id] = {
                    'id': model_id, 'name': api_model.get('name', model_id), 'object': api_model.get('object', 'model'),
                    'owned_by': api_model.get('owned_by', 'unknown'), 'enabled': True
                }
        self.all_intercepted_models = list(existing_models_map.values())
        self.clear_filter()
        messagebox.showinfo(_("Success"), _("Sync complete! Found {count} models.").format(count=len(api_models)), parent=self)

    def add_custom_model(self):
        dialog = tk.Toplevel(self)
        dialog.title(_("Add Custom Model"))
        dialog.geometry("400x250"); dialog.transient(self); dialog.grab_set()
        x, y = self.winfo_x() + (self.winfo_width() - 400) // 2, self.winfo_y() + (self.winfo_height() - 250) // 2
        dialog.geometry(f"400x250+{x}+{y}")
        frame = ttk.Frame(dialog, padding=20); frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text=_("Model ID:")).grid(row=0, column=0, sticky=W, pady=5)
        model_id_var = tk.StringVar(); ttk.Entry(frame, textvariable=model_id_var).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text=_("Model Name:")).grid(row=1, column=0, sticky=W, pady=5)
        model_name_var = tk.StringVar(); ttk.Entry(frame, textvariable=model_name_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text=_("Owner:")).grid(row=2, column=0, sticky=W, pady=5)
        owned_by_var = tk.StringVar(value="custom"); ttk.Entry(frame, textvariable=owned_by_var).grid(row=2, column=1, sticky="ew", pady=5)
        frame.grid_columnconfigure(1, weight=1)
        def do_add():
            model_id = model_id_var.get().strip()
            if not model_id:
                messagebox.showwarning(_("Warning"), _("Please enter a Model ID"), parent=dialog); return
            if any(m.get('id') == model_id for m in self.all_intercepted_models):
                messagebox.showwarning(_("Warning"), _("This Model ID already exists"), parent=dialog); return
            new_model = {'id': model_id, 'name': model_name_var.get().strip() or model_id, 'object': 'model', 'owned_by': owned_by_var.get().strip() or 'custom', 'enabled': True}
            self.all_intercepted_models.append(new_model)
            self.refresh_model_tree(); dialog.destroy()
        btn_frame = ttk.Frame(frame); btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text=_("Add"), command=do_add, bootstyle=SUCCESS).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text=_("Cancel"), command=dialog.destroy).pack(side=LEFT, padx=5)

    def delete_selected_models(self):
        selected_items = self.model_tree.selection()
        if not selected_items:
            messagebox.showwarning(_("Warning"), _("Please select models to delete first"), parent=self); return
        if messagebox.askyesno(_("Confirm"), _("Are you sure you want to delete the selected {count} models? This action cannot be undone.").format(count=len(selected_items)), parent=self):
            ids_to_delete = set(selected_items)
            self.all_intercepted_models = [m for m in self.all_intercepted_models if m.get('id') not in ids_to_delete]
            if self.is_filtering: self.filtered_models = [m for m in self.filtered_models if m.get('id') not in ids_to_delete]
            self.refresh_model_tree()

    def _toggle_visible_models_enabled(self, enable: bool):
        visible_ids = {self.model_tree.item(item)['values'][1] for item in self.model_tree.get_children()}
        for model in self.all_intercepted_models:
            if model.get('id') in visible_ids: model['enabled'] = enable
        self.refresh_model_tree()
    def select_all_models(self): self._toggle_visible_models_enabled(True)
    def deselect_all_models(self): self._toggle_visible_models_enabled(False)

    def on_model_double_click(self, event):
        item_id = self.model_tree.identify_row(event.y)
        if not item_id: return
        for model in self.all_intercepted_models:
            if model.get('id') == item_id:
                model['enabled'] = not model.get('enabled', False); break
        self.after(50, self.refresh_model_tree)

    def save_model_intercept_config(self):
        self.settings.intercepted_models = sorted(self.all_intercepted_models, key=lambda x: (not x.get('enabled', False), x.get('id', '')))
        if self.on_save_callback: self.on_save_callback()
        enabled_count = sum(1 for m in self.settings.intercepted_models if m.get('enabled'))
        msg = _("Settings saved. Total {total} models, {enabled} enabled.").format(total=len(self.settings.intercepted_models), enabled=enabled_count)
        messagebox.showinfo(_("Success"), msg, parent=self.parent)
        self.destroy()

    def show_context_menu(self, event):
        item = self.model_tree.identify_row(event.y)
        if item and item not in self.model_tree.selection(): self.model_tree.selection_set(item)
        selected_items = self.model_tree.selection()
        if not selected_items: return
        self.context_menu.entryconfig(_("📝 Copy Model ID"), state="normal" if len(selected_items) == 1 else "disabled")
        self.context_menu.post(event.x_root, event.y_root)

    def _toggle_selection_enabled(self, enable: bool):
        selected_ids = set(self.model_tree.selection())
        if not selected_ids: return
        for model in self.all_intercepted_models:
            if model.get('id') in selected_ids: model['enabled'] = enable
        self.refresh_model_tree()
    def enable_selected_items(self): self._toggle_selection_enabled(True)
    def disable_selected_items(self): self._toggle_selection_enabled(False)
    def copy_selected_model_id(self):
        selected_items = self.model_tree.selection()
        if len(selected_items) == 1: self.clipboard_clear(); self.clipboard_append(selected_items[0])

    def open_advanced_edit(self):
        edit_window = tk.Toplevel(self)
        edit_window.title(_("Advanced Edit Mode - JSON"))
        edit_window.geometry("700x500"); edit_window.transient(self)
        x, y = self.winfo_x()+(self.winfo_width()-700)//2, self.winfo_y()+(self.winfo_height()-500)//2
        edit_window.geometry(f"700x500+{x}+{y}"); edit_window.grab_set()
        main_frame = ttk.Frame(edit_window, padding=10); main_frame.pack(fill=BOTH, expand=True)
        info_label = ttk.Label(main_frame, text=_("Edit the model's JSON configuration directly here. Ensure the format is correct."), bootstyle=INFO)
        info_label.pack(fill=X, pady=(0, 10))
        text_frame = ttk.Frame(main_frame); text_frame.pack(fill=BOTH, expand=True)
        json_text_widget = ScrolledText(text_frame, wrap="word", autohide=True, height=10)
        json_text_widget.pack(fill=BOTH, expand=True)
        try:
            current_config = json.dumps(self.all_intercepted_models, indent=2, ensure_ascii=False)
            json_text_widget.insert("1.0", current_config)
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to load current model configuration: {error}").format(error=e), parent=edit_window)
            json_text_widget.insert("1.0", f"// {_('Failed to load configuration')}: {e}\n[]")
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=X, pady=(10, 0))
        def save_and_apply(): self.save_json_config(json_text_widget, edit_window)
        ttk.Button(button_frame, text=_("✅ Validate Format"), command=lambda: self.validate_json_config(json_text_widget.get("1.0", "end-1c"), parent=edit_window)).pack(side=LEFT)
        ttk.Button(button_frame, text=_("💅 Format"), command=lambda: self.format_json_config(json_text_widget)).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text=_("💾 Save and Apply"), command=save_and_apply, bootstyle=SUCCESS).pack(side=RIGHT)
        ttk.Button(button_frame, text=_("❌ Cancel"), command=edit_window.destroy).pack(side=RIGHT, padx=5)

    def validate_json_config(self, json_string, parent):
        try:
            data = json.loads(json_string)
            if not isinstance(data, list):
                messagebox.showerror(_("Validation Failed"), _("Top-level structure must be a JSON array (list)."), parent=parent); return False
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    messagebox.showerror(_("Validation Failed"), _("Item #{num} is not a valid JSON object (dictionary).").format(num=i+1), parent=parent); return False
                if 'id' not in item:
                    messagebox.showerror(_("Validation Failed"), _("Item #{num} is missing the required 'id' field.").format(num=i+1), parent=parent); return False
            messagebox.showinfo(_("Success"), _("JSON configuration validation passed!"), parent=parent); return True
        except json.JSONDecodeError as e:
            messagebox.showerror(_("JSON Error"), _("Invalid JSON format: {error}").format(error=e), parent=parent); return False

    def format_json_config(self, text_widget):
        try:
            current_text = text_widget.get("1.0", "end-1c")
            data = json.loads(current_text)
            formatted_text = json.dumps(data, indent=2, ensure_ascii=False)
            text_widget.delete("1.0", "end"); text_widget.insert("1.0", formatted_text)
        except Exception as e:
            messagebox.showerror(_("Formatting Failed"), _("Could not format JSON: {error}").format(error=e), parent=text_widget.winfo_toplevel())

    def save_json_config(self, text_widget, window):
        json_string = text_widget.get("1.0", "end-1c")
        if not self.validate_json_config(json_string, parent=window): return
        new_config = json.loads(json_string)
        self.all_intercepted_models = new_config
        self.refresh_model_tree()
        window.destroy()
        messagebox.showinfo(_("Success"), _("Advanced edits applied.\nPlease remember to click the 'Save' button in the main settings window to persist changes."), parent=self)

class MainApplication:
    """主应用程序类"""
    def __init__(self, root):
        self.root = root
        if getattr(sys, 'frozen', False):
            self.base_path = Path(sys._MEIPASS)
            self.config_path = Path(sys.executable).parent / "config.json"
        else:
            self.base_path = Path(__file__).parent
            self.config_path = self.base_path / "config.json"

        self.settings = Settings()
        self.load_config()
        
        locale_manager.switch_language(self.settings.language)

        self.style = tb.Style(theme=self.settings.theme)
        self.setup_window()
        self.server = None
        self.log_queue = queue.Queue()
        
        self.create_ui()
        self.update_ui_texts() # 初始化UI文本

        self.configure_treeview_style()
        self.set_window_icon()
        if ENABLE_TRAY: self.setup_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind("<Unmap>", self.on_minimize)
        self.apply_saved_config()
        if self.settings.auto_start and self.settings.start_minimized:
            self.root.after(100, self.minimize_to_tray)
            self.root.after(200, self.start_server)
        elif self.settings.auto_start:
            self.root.after(100, self.start_server)
        self.update_logs()

    def setup_window(self):
        width, height = 900, 700
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (screen_width - width) // 2, (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(800, 600)

    def create_ui(self):
        self.create_toolbar()
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.create_config_frame(main_frame)
        self.create_log_frame(main_frame)
        self.create_statusbar()
        
    def switch_language_and_update_ui(self, lang_code):
        locale_manager.switch_language(lang_code)
        self.settings.language = lang_code
        self.save_config()
        self.update_ui_texts()
        # 更新所有子窗口
        for win in self.root.winfo_children():
            if isinstance(win, tk.Toplevel) and hasattr(win, 'update_ui_texts'):
                win.update_ui_texts()

    def update_ui_texts(self):
        """更新所有UI组件的文本"""
        self.root.title(_("Oai2Ollama GUI - OpenAI to Ollama API Bridge"))
        
        # Toolbar
        self.theme_btn.config(text=_("🌙 Dark Theme") if self.settings.theme == "darkly" else _("☀️ Light Theme"))
        self.settings_btn.config(text=_("⚙️ Settings"))
        self.about_btn.config(text=_("ℹ️ About"))
        self.stop_btn.config(text=_("⏹️ Stop"))
        self.start_btn.config(text=_("▶️ Start"))

        # Config Frame
        self.config_frame.config(text=_("Server Configuration"))
        self.api_key_label.config(text=_("API Key:"))
        self.show_key_check.config(text=_("Show"))
        self.base_url_label.config(text=_("Base URL:"))
        self.listen_addr_label.config(text=_("Listen Address:"))
        self.port_label.config(text=_("Port:"))
        self.open_docs_btn.config(text=_("Open API Docs"))
        self.capabilities_label.config(text=_("Capabilities:"))
        self.capabilities_hint.config(text=_("(comma-separated, e.g., tools, vision, embedding)"))
        self.intercept_label.config(text=_("Intercept Model List:"))
        self.intercept_check.config(text=_("Enable"))
        self.intercept_settings_btn.config(text=_("Settings"))
        self.extra_models_label.config(text=_("Extra Models:"))
        self.extra_models_hint.config(text=_("(comma-separated, e.g., gpt-4, gpt-3.5-turbo)"))
        
        # Log Frame
        self.log_frame.config(text=_("Server Log"))
        self.clear_log_btn.config(text=_("Clear Log"))
        self.save_log_btn.config(text=_("Save Log"))
        self.auto_scroll_check.config(text=_("Auto-scroll"))
        
        # Statusbar
        self.status_label.config(text=_("Ready"))
        is_running = self.server and self.server.is_running
        status_text = _("Server: Running on {host}:{port}").format(host=self.settings.host, port=self.settings.port) if is_running else _("Server: Stopped")
        self.server_status_label.config(text=status_text)
        
    def create_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=X, padx=5, pady=2)
        
        self.theme_btn = ttk.Button(toolbar, command=self.toggle_theme, width=12)
        self.theme_btn.pack(side=LEFT, padx=2)
        
        # --- 语言菜单 ---
        self.lang_menu_btn = ttk.Menubutton(toolbar, text=_("🌐 Language"), width=12)
        self.lang_menu_btn.pack(side=LEFT, padx=2)
        self.lang_menu = Menu(self.lang_menu_btn, tearoff=0)
        self.lang_menu_btn['menu'] = self.lang_menu
        
        for code, name in locale_manager.supported_languages.items():
            self.lang_menu.add_command(label=name, command=lambda c=code: self.switch_language_and_update_ui(c))
        
        self.settings_btn = ttk.Button(toolbar, command=self.open_settings, width=8)
        self.settings_btn.pack(side=LEFT, padx=2)
        self.about_btn = ttk.Button(toolbar, command=self.show_about, width=8)
        self.about_btn.pack(side=LEFT, padx=2)
        self.stop_btn = ttk.Button(toolbar, command=self.stop_server, state=DISABLED, width=8)
        self.stop_btn.pack(side=RIGHT, padx=2)
        self.start_btn = ttk.Button(toolbar, command=self.start_server, bootstyle=SUCCESS, width=8)
        self.start_btn.pack(side=RIGHT, padx=2)

    def create_config_frame(self, parent):
        self.config_frame = ttk.LabelFrame(parent, padding=10)
        self.config_frame.pack(fill=X, pady=(0, 5))
        api_frame = ttk.Frame(self.config_frame); api_frame.pack(fill=X, pady=5)
        self.api_key_label = ttk.Label(api_frame, width=12); self.api_key_label.grid(row=0, column=0, sticky=W, padx=(0, 5))
        self.api_key_var = tk.StringVar(value=self.settings.api_key)
        self.api_key_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=0, column=1, sticky=(W, E), padx=(0, 5))
        self.show_key_var = tk.BooleanVar(value=False)
        self.show_key_check = ttk.Checkbutton(api_frame, variable=self.show_key_var, command=self.toggle_api_key_visibility)
        self.show_key_check.grid(row=0, column=2)
        api_frame.columnconfigure(1, weight=1)
        url_frame = ttk.Frame(self.config_frame); url_frame.pack(fill=X, pady=5)
        self.base_url_label = ttk.Label(url_frame, width=12); self.base_url_label.grid(row=0, column=0, sticky=W, padx=(0, 5))
        self.base_url_var = tk.StringVar(value=self.settings.base_url)
        ttk.Entry(url_frame, textvariable=self.base_url_var).grid(row=0, column=1, sticky=(W, E))
        url_frame.columnconfigure(1, weight=1)
        server_frame = ttk.Frame(self.config_frame); server_frame.pack(fill=X, pady=5)
        self.listen_addr_label = ttk.Label(server_frame, width=12); self.listen_addr_label.grid(row=0, column=0, sticky=W, padx=(0, 5))
        self.host_var = tk.StringVar(value=self.settings.host)
        ttk.Entry(server_frame, textvariable=self.host_var, width=20).grid(row=0, column=1, sticky=W, padx=(0, 10))
        self.port_label = ttk.Label(server_frame); self.port_label.grid(row=0, column=2, sticky=W, padx=(0, 5))
        self.port_var = tk.IntVar(value=self.settings.port); ttk.Entry(server_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, sticky=W)
        self.open_docs_btn = ttk.Button(server_frame, command=self.open_api_docs, width=15); self.open_docs_btn.grid(row=0, column=4, padx=(20, 0))
        advanced_frame = ttk.Frame(self.config_frame); advanced_frame.pack(fill=X, pady=5)
        self.capabilities_label = ttk.Label(advanced_frame, width=12); self.capabilities_label.grid(row=0, column=0, sticky=W, padx=(0, 5))
        self.capabilities_var = tk.StringVar(value=", ".join(self.settings.capabilities))
        ttk.Entry(advanced_frame, textvariable=self.capabilities_var, width=40).grid(row=0, column=1, sticky=W, padx=(0, 5))
        self.capabilities_hint = ttk.Label(advanced_frame, foreground="gray"); self.capabilities_hint.grid(row=0, column=2, sticky=W)
        intercept_frame = ttk.Frame(advanced_frame); intercept_frame.grid(row=1, column=0, columnspan=3, sticky=(W,E), pady=(5,0))
        self.intercept_label = ttk.Label(intercept_frame, width=12); self.intercept_label.grid(row=0, column=0, sticky=W, padx=(0,5))
        self.intercept_models_var = tk.BooleanVar(value=self.settings.intercept_models_enabled)
        self.intercept_check = ttk.Checkbutton(intercept_frame, variable=self.intercept_models_var, command=self.on_intercept_models_toggle)
        self.intercept_check.grid(row=0, column=1, sticky=W, padx=(0,10))
        self.intercept_settings_btn = ttk.Button(intercept_frame, command=self.open_model_intercept_window, width=8)
        self.intercept_settings_btn.grid(row=0, column=2, sticky=W)
        self.extra_models_label = ttk.Label(advanced_frame, width=12); self.extra_models_label.grid(row=2, column=0, sticky=W, padx=(0, 5), pady=(5,0))
        self.models_var = tk.StringVar(value=", ".join(self.settings.models))
        ttk.Entry(advanced_frame, textvariable=self.models_var, width=40).grid(row=2, column=1, sticky=W, padx=(0, 5), pady=(5,0))
        self.extra_models_hint = ttk.Label(advanced_frame, foreground="gray"); self.extra_models_hint.grid(row=2, column=2, sticky=W, pady=(5,0))

    def create_log_frame(self, parent):
        self.log_frame = ttk.LabelFrame(parent, padding=10)
        self.log_frame.pack(fill=BOTH, expand=True)
        control_frame = ttk.Frame(self.log_frame); control_frame.pack(fill=X, pady=(0, 5))
        self.clear_log_btn = ttk.Button(control_frame, command=self.clear_logs, width=10)
        self.clear_log_btn.pack(side=LEFT, padx=(0, 5))
        self.save_log_btn = ttk.Button(control_frame, command=self.save_logs, width=10)
        self.save_log_btn.pack(side=LEFT)
        self.auto_scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll_check = ttk.Checkbutton(control_frame, variable=self.auto_scroll_var)
        self.auto_scroll_check.pack(side=LEFT, padx=(10, 0))
        self.log_text = ScrolledText(self.log_frame, height=15, autohide=True,
                                     bootstyle="dark" if self.settings.theme == "darkly" else "light")
        self.log_text.pack(fill=BOTH, expand=True)

    def create_statusbar(self):
        self.statusbar = ttk.Frame(self.root)
        self.statusbar.pack(fill=X, side=BOTTOM)
        self.status_label = ttk.Label(self.statusbar, relief=SUNKEN, anchor=W)
        self.status_label.pack(side=LEFT, fill=X, expand=True, padx=2, pady=1)
        self.server_status_label = ttk.Label(self.statusbar, relief=SUNKEN, anchor=W, width=25)
        self.server_status_label.pack(side=RIGHT, padx=2, pady=1)

    def toggle_theme(self):
        if self.settings.theme == "darkly":
            self.settings.theme = "litera"
            self.style.theme_use("litera")
            self.log_text.config(bootstyle="light")
        else:
            self.settings.theme = "darkly"
            self.style.theme_use("darkly")
            self.log_text.config(bootstyle="dark")
        self.update_ui_texts() # 更新主题按钮文字
        self.configure_treeview_style()
        self.save_config()

    def configure_treeview_style(self):
        if self.settings.theme == "darkly":
            style_config = {"borderwidth": 1, "relief": "solid", "rowheight": 25, "background": "#2b2b2b", "fieldbackground": "#2b2b2b", "foreground": "white"}
            map_config = {"background": [("selected", "#0d6efd")], "foreground": [("selected", "white")]}
        else:
            style_config = {"borderwidth": 1, "relief": "solid", "rowheight": 25, "background": "white", "fieldbackground": "white", "foreground": "black"}
            map_config = {"background": [("selected", "#0d6efd")], "foreground": [("selected", "white")]}
        self.style.configure("Treeview", **style_config)
        self.style.map("Treeview", **map_config)
        self.style.configure("Treeview.Heading", borderwidth=1, relief="solid")

    def toggle_api_key_visibility(self):
        self.api_key_entry.config(show="" if self.show_key_var.get() else "*")

    def start_server(self):
        if not self.api_key_var.get():
            messagebox.showerror(_("Error"), _("Please enter an API Key")); return
        if not self.base_url_var.get():
            messagebox.showerror(_("Error"), _("Please enter a Base URL")); return
        self.settings.api_key = self.api_key_var.get()
        self.settings.base_url = self.base_url_var.get()
        self.settings.host = self.host_var.get()
        self.settings.port = self.port_var.get()
        cap_str = self.capabilities_var.get().strip()
        self.settings.capabilities = [c.strip() for c in cap_str.split(",")] if cap_str else []
        model_str = self.models_var.get().strip()
        self.settings.models = [m.strip() for m in model_str.split(",")] if model_str else []
        self.save_config()
        self.server = Oai2OllamaServer(self.settings, self.add_log)
        self.server.start()
        self.start_btn.config(state=DISABLED); self.stop_btn.config(state=NORMAL)
        self.status_label.config(text=_("Server started"))
        self.update_ui_texts() # 更新状态栏
        for widget in [self.api_key_entry]:
            if hasattr(widget, 'config'): widget.config(state=DISABLED)

    def stop_server(self):
        if self.server:
            self.server.stop(); self.server = None
        self.start_btn.config(state=NORMAL); self.stop_btn.config(state=DISABLED)
        self.status_label.config(text=_("Server stopped"))
        self.update_ui_texts() # 更新状态栏
        for widget in [self.api_key_entry]:
            if hasattr(widget, 'config'): widget.config(state=NORMAL)

    def add_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def update_logs(self):
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.log_text.insert(END, message + "\n")
                if self.auto_scroll_var.get(): self.log_text.see(END)
        except queue.Empty: pass
        self.root.after(100, self.update_logs)

    def clear_logs(self):
        self.log_text.delete(1.0, END); self.status_label.config(text=_("Log cleared"))

    def save_logs(self):
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            title=_("Save Log"), defaultextension=".txt",
            filetypes=[(_("Text files"), "*.txt"), (_("All files"), "*.*")])
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, END))
                self.status_label.config(text=_("Log saved to: {filename}").format(filename=filename))
                messagebox.showinfo(_("Success"), _("Log saved"))
            except Exception as e:
                messagebox.showerror(_("Error"), _("Failed to save log: {error}").format(error=e))

    def open_api_docs(self):
        if self.server and self.server.is_running:
            webbrowser.open(f"http://{self.settings.host}:{self.settings.port}/docs")
        else: messagebox.showwarning(_("Tip"), _("Please start the server first"))

    def open_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title(_("Settings"))
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.update_idletasks()
        x, y = (settings_window.winfo_screenwidth() - 400) // 2, (settings_window.winfo_screenheight() - 300) // 2
        settings_window.geometry(f"400x300+{x}+{y}")
        frame = ttk.Frame(settings_window, padding=20); frame.pack(fill=BOTH, expand=True)

        auto_start_var = tk.BooleanVar(value=self.settings.auto_start)
        ttk.Checkbutton(frame, text=_("Auto-start server on application launch"), variable=auto_start_var).pack(anchor=W, pady=5)
        
        minimize_var = tk.BooleanVar(value=self.settings.minimize_to_tray)
        ttk.Checkbutton(frame, text=_("Minimize to system tray on close"), variable=minimize_var).pack(anchor=W, pady=5)
        
        start_minimized_var = tk.BooleanVar(value=self.settings.start_minimized)
        ttk.Checkbutton(frame, text=_("Start minimized to tray"), variable=start_minimized_var).pack(anchor=W, pady=5)
        
        btn_frame = ttk.Frame(frame); btn_frame.pack(side=BOTTOM, fill=X, pady=(20, 0))
        def save_settings():
            self.settings.auto_start = auto_start_var.get()
            self.settings.minimize_to_tray = minimize_var.get()
            self.settings.start_minimized = start_minimized_var.get()
            self.save_config()
            settings_window.destroy()
            messagebox.showinfo(_("Success"), _("Settings have been saved"))
        
        ttk.Button(btn_frame, text=_("Save"), command=save_settings, bootstyle=SUCCESS).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text=_("Cancel"), command=settings_window.destroy).pack(side=RIGHT)

    def show_about(self):
        about_text = f"""Oai2Ollama GUI
{_('Version')}: {VERSION}

OpenAI to Ollama API Bridge
{_('A desktop application that converts OpenAI-compatible APIs to Ollama-compatible APIs')}

{_('Features')}:
• {_('API format conversion')}
• {_('Model management')}
• {_('Capability tagging')}
• {_('Streaming response support')}
• {_('Graphical user interface')}

{_('Author')}: Oai2Ollama Team
{_('License')}: MIT License"""
        messagebox.showinfo(_("About"), about_text)

    def on_intercept_models_toggle(self):
        self.settings.intercept_models_enabled = self.intercept_models_var.get()
        self.save_config()

    def open_model_intercept_window(self):
        ModelInterceptWindow(parent=self.root, settings_manager=self.settings, on_save_callback=self.save_config)

    def load_config(self):
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for key, value in config.items():
                    if hasattr(self.settings, key):
                        setattr(self.settings, key, value)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    def save_config(self):
        try:
            config = {key: value for key, value in self.settings.__dict__.items()}
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def apply_saved_config(self):
        if hasattr(self, 'api_key_var'): self.api_key_var.set(self.settings.api_key)
        if hasattr(self, 'base_url_var'): self.base_url_var.set(self.settings.base_url)
        if hasattr(self, 'host_var'): self.host_var.set(self.settings.host)
        if hasattr(self, 'port_var'): self.port_var.set(self.settings.port)
        if hasattr(self, 'capabilities_var'): self.capabilities_var.set(", ".join(self.settings.capabilities))
        if hasattr(self, 'models_var'): self.models_var.set(", ".join(self.settings.models))
        if hasattr(self, 'intercept_models_var'): self.intercept_models_var.set(self.settings.intercept_models_enabled)
    
    def set_window_icon(self):
        """设置窗口图标"""
        icon_path = self.base_path / "icon.ico"
        icon_png_path = self.base_path / "icon.png"
        
        try:
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
                self.icon_image = Image.open(str(icon_path))
            elif icon_png_path.exists():
                self.icon_image = Image.open(str(icon_png_path))
                self.root.iconphoto(True, tk.PhotoImage(file=str(icon_png_path)))
            else:
                # 创建默认图标
                self.icon_image = self.create_default_icon()
        except Exception as e:
            logger.error(f"设置图标失败: {e}")
            self.icon_image = self.create_default_icon()
    
    def create_default_icon(self):
        """创建默认图标"""
        img = Image.new('RGB', (64, 64), color='#0d6efd')
        draw = ImageDraw.Draw(img)
        draw.rectangle([8, 8, 56, 56], outline='white', width=2)
        draw.text((20, 20), "O2O", fill='white')
        return img
    
    def setup_tray(self):
        if not ENABLE_TRAY: return
        self.tray_icon = None
        def show_window(): self.root.deiconify(); self.root.lift(); self.root.focus_force()
        def quit_app(): self.quit_application()
        def on_tray_click(icon, item):
            actions = {"Show": show_window, "Hide": self.root.withdraw, "Start Server": self.start_server,
                       "Stop Server": self.stop_server, "Exit": quit_app}
            if str(item) in actions: self.root.after(0, actions[str(item)])
        
        menu = pystray.Menu(
            Item(_("Show"), on_tray_click, default=True), Item(_("Hide"), on_tray_click), pystray.Menu.SEPARATOR,
            Item(_("Start Server"), on_tray_click), Item(_("Stop Server"), on_tray_click), pystray.Menu.SEPARATOR,
            Item(_("Exit"), on_tray_click)
        )
        self.tray_icon = pystray.Icon("Oai2Ollama", self.icon_image, "Oai2Ollama - API Bridge", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()
    
    def minimize_to_tray(self):
        """最小化到托盘"""
        if ENABLE_TRAY and self.settings.minimize_to_tray:
            self.root.withdraw()
            if self.tray_icon:
                self.add_log("程序已最小化到系统托盘")
    
    def minimize_to_tray(self):
        if ENABLE_TRAY and self.settings.minimize_to_tray:
            self.root.withdraw()
            if self.tray_icon: self.add_log(_("Application minimized to system tray"))
    
    def on_minimize(self, event):
        if event.widget == self.root and self.root.state() == 'iconic' and ENABLE_TRAY and self.settings.minimize_to_tray:
            self.root.withdraw()

    def on_closing(self):
        if ENABLE_TRAY and self.settings.minimize_to_tray: self.minimize_to_tray()
        else: self.quit_application()

    def quit_application(self):
        if self.server and self.server.is_running: self.stop_server()
        if ENABLE_TRAY and hasattr(self, 'tray_icon') and self.tray_icon: self.tray_icon.stop()
        self.save_config()
        self.root.quit(); self.root.destroy()

class QuickStartDialog:
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(_("Quick Setup Wizard"))
        self.dialog.geometry("600x450"); self.dialog.resizable(False, False)
        self.dialog.transient(parent); self.dialog.update_idletasks()
        x, y = (self.dialog.winfo_screenwidth() - 600) // 2, (self.dialog.winfo_screenheight() - 450) // 2
        self.dialog.geometry(f"600x450+{x}+{y}")
        self.result = None
        self.create_widgets()
        self.dialog.grab_set(); self.dialog.focus_set()

    def create_widgets(self):
        title_frame = ttk.Frame(self.dialog); title_frame.pack(fill=X, padx=20, pady=10)
        ttk.Label(title_frame, text=_("Welcome to Oai2Ollama"), font=('', 16, 'bold')).pack()
        ttk.Label(title_frame, text=_("Please configure basic parameters to start the service"), foreground="gray").pack(pady=5)
        
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        preset_frame = ttk.LabelFrame(main_frame, text=_("Select a preset configuration"), padding=15)
        preset_frame.pack(fill=X, pady=(0, 15))
        self.preset_var = tk.StringVar(value="custom")
        presets = [(_("Official OpenAI"), "openai", "https://api.openai.com/v1"), 
                   (_("Azure OpenAI"), "azure", "https://YOUR-RESOURCE.openai.azure.com"),
                   (_("Local Service"), "local", "http://localhost:8080/v1"),
                   (_("Custom"), "custom", "")]
        for idx, (label, value, url) in enumerate(presets):
            ttk.Radiobutton(preset_frame, text=label, variable=self.preset_var, value=value, command=lambda u=url: self.on_preset_change(u)).grid(row=idx // 2, column=idx % 2, sticky=W, padx=10, pady=5)
            
        config_frame = ttk.LabelFrame(main_frame, text=_("API Configuration"), padding=15)
        config_frame.pack(fill=X, pady=(0, 15))
        ttk.Label(config_frame, text=_("API Key:")).grid(row=0, column=0, sticky=W, pady=5)
        self.api_key_entry = ttk.Entry(config_frame, width=50); self.api_key_entry.grid(row=0, column=1, pady=5, padx=(10, 0))
        ttk.Label(config_frame, text=_("Base URL:")).grid(row=1, column=0, sticky=W, pady=5)
        self.base_url_entry = ttk.Entry(config_frame, width=50); self.base_url_entry.grid(row=1, column=1, pady=5, padx=(10, 0))

        advanced_frame = ttk.LabelFrame(main_frame, text=_("Advanced Options (optional)"), padding=15); advanced_frame.pack(fill=X)
        listen_frame = ttk.Frame(advanced_frame); listen_frame.pack(fill=X)
        ttk.Label(listen_frame, text=_("Listen Address:")).pack(side=LEFT)
        self.host_entry = ttk.Entry(listen_frame, width=15); self.host_entry.pack(side=LEFT, padx=(5, 10)); self.host_entry.insert(0, "localhost")
        ttk.Label(listen_frame, text=_("Port:")).pack(side=LEFT)
        self.port_entry = ttk.Entry(listen_frame, width=8); self.port_entry.pack(side=LEFT, padx=5); self.port_entry.insert(0, "11434")

        button_frame = ttk.Frame(self.dialog); button_frame.pack(fill=X, padx=20, pady=10)
        ttk.Button(button_frame, text=_("Get Started"), command=self.on_start, bootstyle=SUCCESS, width=12).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text=_("Configure Later"), command=self.on_cancel, width=12).pack(side=RIGHT)

    def on_preset_change(self, url):
        if url: self.base_url_entry.delete(0, tk.END); self.base_url_entry.insert(0, url)
    def on_start(self):
        api_key, base_url = self.api_key_entry.get().strip(), self.base_url_entry.get().strip()
        if not api_key: messagebox.showerror(_("Error"), _("Please enter an API Key"), parent=self.dialog); return
        if not base_url: messagebox.showerror(_("Error"), _("Please enter a Base URL"), parent=self.dialog); return
        self.result = {'api_key': api_key, 'base_url': base_url, 'host': self.host_entry.get() or "localhost", 'port': int(self.port_entry.get() or "11434")}
        self.dialog.destroy()
    def on_cancel(self): self.dialog.destroy()

def main():
    root = tb.Window(themename="darkly")
    app = MainApplication(root)
    if not app.settings.api_key and not app.settings.base_url:
        dialog = QuickStartDialog(root)
        root.wait_window(dialog.dialog)
        if dialog.result:
            app.settings.api_key = dialog.result['api_key']
            app.settings.base_url = dialog.result['base_url']
            app.settings.host = dialog.result['host']
            app.settings.port = dialog.result['port']
            app.save_config()
            app.apply_saved_config()
    try:
        root.mainloop()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()