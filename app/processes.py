"""Bound document workers and their descendants to the owning service."""
import os
import signal
import subprocess


class WorkerFailure(Exception):
    pass


class WindowsJob:
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [("user", ctypes.c_longlong), ("job", ctypes.c_longlong), ("flags", w.DWORD),
                        ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t), ("count", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read", "write", "other", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Limits), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise WorkerFailure("无法建立文档处理隔离")
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            raise WorkerFailure("无法将文档处理进程加入隔离")

    def close(self):
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_worker(command: list[str], payload: bytes, timeout: float = 60) -> bytes:
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=environment, **kwargs) as process:
        job = None
        try:
            if os.name == "nt":
                job = WindowsJob(process)
            try:
                output, error = process.communicate(payload, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise WorkerFailure("文档处理超时，内容已保留，请重试") from None
            if process.returncode != 0:
                messages = {b"FONT_MISSING": "未找到中文字体，请通过项目启动入口运行",
                            b"PDF_LAYOUT": "PDF 无法在可读范围内排成一页，或正文检查未通过，请精简内容后重试"}
                raise WorkerFailure(messages.get(error.strip(), "文档处理失败，请检查运行环境后重试"))
            return output
        finally:
            if job:
                job.close()
            elif os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait()
