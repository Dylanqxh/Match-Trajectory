import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path


class WorkspaceBusy(Exception):
    pass


@contextmanager
def workspace_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / "workspace.lock").open("a+b")
    handle.seek(0)
    if os.fstat(handle.fileno()).st_size == 0:
        handle.write(b"1")
        handle.flush()
    handle.seek(0)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise WorkspaceBusy("这个资料目录已经在另一个工作台中打开，请先停止原服务") from None
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def bind_local_socket(port: int) -> socket.socket:
    if not 0 <= port <= 65535:
        raise ValueError("端口必须介于 0 和 65535")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", port))
    except OSError:
        listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener


def configure_bundled_resources():
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root / "runtime-browsers")
        os.environ["MATCH_TRAJECTORY_FONT_PATH"] = str(root / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf")
        return
    project_root = Path(__file__).resolve().parent.parent
    runtimes = project_root.parent / ".dev-environment" / "runtimes"
    browser_path = runtimes / "playwright"
    font = runtimes / "fonts" / "NotoSansCJKsc-Regular.otf"
    if browser_path.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browser_path))
    if font.is_file():
        os.environ.setdefault("MATCH_TRAJECTORY_FONT_PATH", str(font))


def configure_runtime_temp(directory: Path):
    runtime_temp = directory / "runtime-temp"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(runtime_temp)
    os.environ["TMP"] = str(runtime_temp)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    configure_bundled_resources()
    if "--export-worker" in sys.argv:
        from app.export_worker import main as worker_main
        raise SystemExit(worker_main())
    parser = argparse.ArgumentParser(description="Match-Trajectory 本地简历工作台")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    directory = (args.data_dir or root / "data").resolve()
    configure_runtime_temp(directory)
    try:
        with workspace_lock(directory), bind_local_socket(args.port) as listener:
            import uvicorn

            from app.main import create_app

            port = listener.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            if not args.no_browser:
                def open_when_ready():
                    import httpx
                    for _ in range(40):
                        try:
                            if httpx.get(url + "/health", timeout=0.5, trust_env=False).is_success:
                                webbrowser.open(url)
                                return
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.25)
                threading.Thread(target=open_when_ready, daemon=True).start()
            print(f"本地工作台：{url}\n资料目录：{directory}\n按 Ctrl+C 停止服务。", flush=True)
            server = uvicorn.Server(uvicorn.Config(create_app(directory), host="127.0.0.1", port=port, access_log=False))
            server.run(sockets=[listener])
    except (WorkspaceBusy, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
