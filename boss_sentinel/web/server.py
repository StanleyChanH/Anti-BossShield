"""Boss Sentinel Web UI — FastAPI 后端服务器

替代 PyQt5 GUI，通过浏览器提供 Apple 风格的监控界面。
支持 MJPEG 视频流、SSE 日志推送、REST API 控制。
"""

import os
import json
import time
import logging
import threading
import collections
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
    FileResponse,
)
from fastapi.staticfiles import StaticFiles

from ..monitor import SentinelMonitor
from ..config import SentinelConfig, load_config, save_config

logger = logging.getLogger(__name__)

# Web UI 静态文件目录
_STATIC_DIR = Path(__file__).parent / "static"

# 端口配置
DEFAULT_PORT = 8970
DEFAULT_HOST = "127.0.0.1"


class WebServer:
    """Boss Sentinel Web 服务器

    管理监控线程、视频流、日志推送和配置 CRUD。
    """

    def __init__(self):
        self.app = FastAPI(title="Boss Sentinel", docs_url=None, redoc_url=None)
        self._monitor: Optional[SentinelMonitor] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._current_config: Optional[SentinelConfig] = None
        self._config_path = "config.json"

        # 监控状态
        self._status = "idle"  # idle | starting | monitoring | stopping | error
        self._error_message = ""

        # 帧队列 (MJPEG 源)
        self._frame_queue: collections.deque = collections.deque(maxlen=2)

        # 日志环形缓冲
        self._log_buffer: collections.deque = collections.deque(maxlen=500)
        # SSE 日志订阅者列表
        self._log_subscribers: list = []

        # 特性状态
        self._feature_status: dict = {}
        # 已启用的特性列表（来自配置）
        self._enabled_features: dict = {}

        # 告警事件
        self._alert_subscribers: list = []

        # 统计数据（会话级）
        self._stats = self._empty_stats()

        # 初始化进度
        self._init_progress = 0
        self._init_message = ""

        self._setup_routes()

    # ------------------------------------------------------------------
    # 路由注册
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_stats() -> dict:
        """创建空的统计数据字典"""
        return {
            "start_time": None,
            "total_detections": 0,
            "total_alerts": 0,
            "detection_by_person": {},
            "detection_timeline": [],
            "hourly_detections": [0] * 24,
            "attention_samples": {"focused": 0, "distracted": 0, "away": 0},
        }

    def _setup_routes(self):
        """注册所有 API 路由"""
        app = self.app

        # 静态文件
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return FileResponse(str(_STATIC_DIR / "index.html"))

        # --- 状态 & 控制 ---

        @app.get("/api/status")
        async def get_status():
            return JSONResponse({
                "status": self._status,
                "error": self._error_message,
                "features": self._feature_status,
                "enabled_features": self._enabled_features,
                "lock_enabled": self._current_config.enable_lock if self._current_config else True,
                "roles": self._current_config.roles if self._current_config else {},
                "init_progress": self._init_progress,
                "init_message": self._init_message,
            })

        @app.post("/api/start")
        async def start_monitoring(request: Request):
            if self._status in ("monitoring", "starting"):
                return JSONResponse({"ok": False, "error": "监控已在运行中"}, status_code=409)

            try:
                body = await request.json()
            except Exception:
                body = {}

            # 优先使用请求体，其次从 config.json 加载
            if body:
                try:
                    config = load_config(body)
                except Exception as e:
                    return JSONResponse({"ok": False, "error": f"配置无效: {e}"}, status_code=400)
            elif os.path.exists(self._config_path):
                try:
                    config = load_config(self._config_path)
                except Exception as e:
                    return JSONResponse({"ok": False, "error": f"加载配置文件失败: {e}"}, status_code=400)
            else:
                config = SentinelConfig()

            self._start_monitor(config)
            return JSONResponse({"ok": True})

        @app.post("/api/stop")
        async def stop_monitoring():
            if self._status not in ("monitoring", "starting"):
                return JSONResponse({"ok": False, "error": "监控未在运行"}, status_code=409)

            self._stop_monitor()
            return JSONResponse({"ok": True})

        @app.post("/api/toggle_lock")
        async def toggle_lock(request: Request):
            """动态切换锁屏开关（无需重启监控）"""
            try:
                body = await request.json()
                enabled = body.get("enabled", True)
            except Exception:
                enabled = True

            enabled = bool(enabled)

            # 更新运行时标志（直接作用于当前运行的 monitor）
            if self._monitor is not None:
                self._monitor._runtime_lock_enabled = enabled
            if self._current_config is not None:
                self._current_config.enable_lock = enabled

            self._add_log(f"[系统] 锁屏功能已{'开启' if enabled else '关闭'}")
            return JSONResponse({"ok": True, "enabled": enabled})

        # --- 配置 ---

        @app.get("/api/config")
        async def get_config():
            if os.path.exists(self._config_path):
                try:
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        return JSONResponse(json.load(f))
                except Exception:
                    pass
            return JSONResponse({})

        @app.put("/api/config")
        async def update_config(request: Request):
            try:
                body = await request.json()
                config = load_config(body)
                save_config(config, self._config_path)
                self._add_log("[系统] 配置已保存")
                return JSONResponse({"ok": True})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        # --- 视频流 (MJPEG) ---

        @app.get("/api/video")
        async def video_stream():
            boundary = "frame"
            return StreamingResponse(
                self._generate_mjpeg(boundary),
                media_type=f"multipart/x-mixed-replace; boundary={boundary}",
            )

        # --- 日志流 (SSE) ---

        @app.get("/api/logs")
        async def log_stream():
            return StreamingResponse(
                self._generate_log_sse(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # --- 告警流 (SSE) ---

        @app.get("/api/alerts")
        async def alert_stream():
            return StreamingResponse(
                self._generate_alert_sse(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # --- 已知人脸列表 ---

        @app.get("/api/faces")
        async def list_faces():
            faces_dir = "known_faces"
            roles_config = {}
            if self._current_config:
                faces_dir = self._current_config.known_faces_dir
                roles_config = self._current_config.roles

            # Build name -> role mapping
            name_to_role = {}
            for role, names in roles_config.items():
                for name in names:
                    name_to_role[name.lower()] = role

            result = []
            if os.path.isdir(faces_dir):
                for name in sorted(os.listdir(faces_dir)):
                    person_dir = os.path.join(faces_dir, name)
                    if os.path.isdir(person_dir):
                        photos = [
                            f for f in os.listdir(person_dir)
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
                        ]
                        role = name_to_role.get(name.lower(), "")
                        result.append({"name": name, "photos": len(photos), "role": role})
            return JSONResponse(result)

        @app.get("/api/stats")
        async def get_stats():
            """返回数据看板统计信息"""
            stats = dict(self._stats)

            # 计算运行时长
            if stats["start_time"]:
                stats["uptime_seconds"] = time.time() - stats["start_time"]
            else:
                stats["uptime_seconds"] = 0

            # 独立识别人物数
            stats["unique_persons"] = len(stats.get("detection_by_person", {}))

            # 只返回最近 20 条时间线
            stats["detection_timeline"] = list(stats.get("detection_timeline", [])[-20:])

            # 番茄钟日报
            if self._monitor and hasattr(self._monitor, '_pomodoro') and self._monitor._pomodoro:
                try:
                    stats["pomodoro_report"] = self._monitor._pomodoro.get_daily_report()
                except Exception:
                    pass

            return JSONResponse(stats)

    # ------------------------------------------------------------------
    # 监控线程管理
    # ------------------------------------------------------------------

    def _start_monitor(self, config: SentinelConfig):
        """在后台线程启动监控"""
        self._current_config = config
        self._status = "starting"
        self._error_message = ""
        self._init_progress = 0
        self._init_message = "正在初始化..."

        # 重置统计数据
        self._stats = self._empty_stats()
        self._stats["start_time"] = time.time()

        # 记录哪些特性已启用
        self._enabled_features = {
            "shoulder_surfing": config.enable_shoulder_surfing,
            "intruder_capture": config.enable_intruder_capture,
            "pomodoro": config.enable_pomodoro,
            "mqtt": config.enable_mqtt,
            "drowsiness": config.enable_drowsiness,
            "head_pose": config.enable_head_pose,
        }
        enabled_names = [k for k, v in self._enabled_features.items() if v]
        if enabled_names:
            self._add_log(f"[系统] 已启用特性: {', '.join(enabled_names)}")

        self._add_log("[系统] 正在启动监控...")

        def _run():
            try:
                self._init_progress = 10
                self._init_message = "正在加载配置..."
                monitor = SentinelMonitor(config, lazy_load=True, config_path=self._config_path)

                self._init_progress = 30
                self._init_message = "正在加载 YOLOv8 模型..."
                monitor.initialize_models()

                self._init_progress = 80
                self._init_message = "模型加载完成"
                time.sleep(0.3)

                self._init_progress = 90
                self._init_message = "开始监控..."

                self._monitor = monitor
                self._status = "monitoring"
                self._init_progress = 100
                self._init_message = ""
                self._add_log("[系统] 监控已启动")

                monitor.run(
                    callback=self._detection_callback,
                    frame_callback=self._frame_callback,
                )
            except Exception as e:
                logger.exception("Monitor thread error")
                self._error_message = str(e)
                self._status = "error"
                self._add_log(f"[错误] 初始化失败: {e}")
            finally:
                self._monitor = None
                if self._status != "error":
                    self._status = "idle"
                self._feature_status = {}
                self._enabled_features = {}
                self._add_log("[系统] 监控已停止")

        self._monitor_thread = threading.Thread(target=_run, daemon=True)
        self._monitor_thread.start()

    def _stop_monitor(self):
        """停止监控"""
        if self._monitor:
            self._status = "stopping"
            self._add_log("[系统] 正在停止监控...")
            self._monitor.stop()
            # 线程会自行退出并设置 status = idle

    # ------------------------------------------------------------------
    # 回调
    # ------------------------------------------------------------------

    def _detection_callback(self, person_name: str):
        """检测到目标人物回调"""
        msg = f"检测到目标人物: {person_name}"
        self._add_log(msg)
        # 推送告警
        self._push_alert(person_name)

        # --- 统计数据追踪 ---
        self._stats["total_detections"] += 1
        self._stats["detection_by_person"][person_name] = \
            self._stats["detection_by_person"].get(person_name, 0) + 1

        # 角色识别
        role = "unknown"
        if self._current_config:
            for r, names in self._current_config.roles.items():
                if person_name.lower() in [n.lower() for n in (names or [])]:
                    role = r
                    break

        self._stats["detection_timeline"].append({
            "time": time.strftime("%H:%M:%S"),
            "person": person_name,
            "role": role,
        })
        # 保留最近 100 条
        if len(self._stats["detection_timeline"]) > 100:
            self._stats["detection_timeline"] = self._stats["detection_timeline"][-100:]

        # 按小时统计
        hour = time.localtime().tm_hour
        self._stats["hourly_detections"][hour] += 1

    def _frame_callback(self, frame: np.ndarray, feature_data: Optional[dict] = None):
        """帧回调 — 推送到 MJPEG 队列"""
        # 编码为 JPEG
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self._frame_queue.append(jpeg.tobytes())

        # 更新特性状态（使用 is not None 而非 truthy 检查，因为空字典 {} 是 falsy）
        if feature_data is not None:
            self._feature_status = feature_data

            # 采样注意力数据用于看板统计
            hp = feature_data.get("head_pose")
            if hp and "attention_status" in hp:
                status = hp["attention_status"]
                if status in self._stats["attention_samples"]:
                    self._stats["attention_samples"][status] += 1

    # ------------------------------------------------------------------
    # MJPEG 生成器
    # ------------------------------------------------------------------

    def _generate_mjpeg(self, boundary: str = "frame"):
        """生成 MJPEG 帧"""
        while True:
            if self._frame_queue:
                frame_bytes = self._frame_queue[-1]  # 取最新帧
                yield (
                    f"--{boundary}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame_bytes)}\r\n\r\n"
                ).encode()
                yield frame_bytes
                yield b"\r\n"
            else:
                # 无帧时发送空白占位
                time.sleep(0.033)  # ~30fps

    # ------------------------------------------------------------------
    # SSE 生成器
    # ------------------------------------------------------------------

    def _generate_log_sse(self):
        """生成日志 SSE 流"""
        # 先发送历史日志
        for log in list(self._log_buffer):
            yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"

        # 订阅新日志
        q: collections.deque = collections.deque(maxlen=100)
        self._log_subscribers.append(q)
        try:
            while True:
                if q:
                    log = q.popleft()
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                else:
                    time.sleep(0.1)
        finally:
            self._log_subscribers.remove(q)

    def _generate_alert_sse(self):
        """生成告警 SSE 流"""
        q: collections.deque = collections.deque(maxlen=10)
        self._alert_subscribers.append(q)
        try:
            while True:
                if q:
                    alert = q.popleft()
                    yield f"data: {json.dumps(alert, ensure_ascii=False)}\n\n"
                else:
                    time.sleep(0.1)
        finally:
            self._alert_subscribers.remove(q)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _add_log(self, message: str):
        """添加日志并推送给所有 SSE 订阅者"""
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "message": message,
        }
        self._log_buffer.append(entry)
        for q in self._log_subscribers:
            q.append(entry)

    def _push_alert(self, person_name: str):
        """推送告警事件"""
        self._stats["total_alerts"] += 1
        alert = {
            "type": "detection",
            "person": person_name,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
        }
        for q in self._alert_subscribers:
            q.append(alert)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    server = WebServer()
    return server.app


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True):
    """启动 Web 服务器"""
    import uvicorn
    import webbrowser

    if open_browser:
        # 延迟打开浏览器，等服务器就绪
        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    logger.info(f"Starting Boss Sentinel Web UI on http://{host}:{port}")
    uvicorn.run(
        "boss_sentinel.web.server:create_app",
        host=host,
        port=port,
        factory=True,
        log_level="warning",
    )
