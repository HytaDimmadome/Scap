import http.server
import json
import os
import socketserver
import sys
import threading
import webbrowser


ARQS = ("visualizador.html", "mcscan_leitor.js", "mcscan_visualizador.js")


def _pasta_viewer():
    for base in (getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()):
        if os.path.isfile(os.path.join(base, "visualizador.html")):
            return base
    return None


def _servidor(pasta, scan):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            nome = self.path.split("?")[0].lstrip("/")
            if nome == "scan.scap":
                caminho, tipo = scan, "application/octet-stream"
            elif nome.startswith("fonts/") and nome.endswith(".ttf") and ".." not in nome:
                caminho, tipo = os.path.join(pasta, "gui_assets", nome), "font/ttf"
            elif nome in ARQS or nome == "":
                nome = nome or "visualizador.html"
                caminho = os.path.join(pasta, nome)
                tipo = "text/html; charset=utf-8" if nome.endswith(".html") else "text/javascript; charset=utf-8"
            else:
                self.send_error(404)
                return
            try:
                with open(caminho, "rb") as f:
                    d = f.read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(d)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(d)

    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    srv = S(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/visualizador.html?arquivo=scan.scap" % srv.server_address[1]


def _pid_vivo(pid):
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259
        except Exception:
            return True
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _seguir(titulo, dono, arq):
    import ctypes
    import time
    from ctypes import wintypes
    u = _u()
    u.IsWindow.argtypes = [ctypes.c_void_p]
    u.IsIconic.argtypes = [ctypes.c_void_p]
    u.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.FindWindowW.restype = ctypes.c_void_p
    hwnd, t0 = 0, time.time()
    while not hwnd and time.time() - t0 < 60:
        hwnd = u.FindWindowW(None, titulo)
        time.sleep(0.05)
    if not hwnd:
        return
    prender(hwnd, dono)
    ult, visivel = None, None
    while u.IsWindow(dono):
        try:
            with open(arq, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            time.sleep(0.02)
            continue
        try:
            if not d.get("vis") or u.IsIconic(dono):
                if visivel is not False:
                    u.ShowWindow(hwnd, 0)
                    visivel = False
            else:
                pt = wintypes.POINT(0, 0)
                rc = wintypes.RECT()
                u.ClientToScreen(dono, ctypes.byref(pt))
                u.GetClientRect(dono, ctypes.byref(rc))
                esc = (rc.right - rc.left) / float(d["cw"]) if d.get("cw") else 1.0
                novo = (pt.x + round(d["x"] * esc), pt.y + round(d["y"] * esc), max(1, round(d["w"] * esc)), max(1, round(d["h"] * esc)))
                if novo != ult or visivel is not True:
                    u.SetWindowPos(hwnd, None, novo[0], novo[1], novo[2], novo[3], 0x0010 | 0x0200 | 0x0040 | 0x0004)
                    ult, visivel = novo, True
        except Exception:
            pass
        time.sleep(0.012)


class _ApiSalvar:

    def __init__(self, pasta=None):
        self._f = None
        self._pasta = pasta

    def ler_recurso(self, nome):
        import base64
        nome = str(nome).split("?")[0].lstrip("/")
        if nome in ARQS:
            caminho = os.path.join(self._pasta or "", nome)
        elif nome.startswith("fonts/") and nome.endswith(".ttf") and ".." not in nome:
            caminho = os.path.join(self._pasta or "", "gui_assets", nome)
        else:
            return ""
        try:
            with open(caminho, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return ""

    def salvar_abrir(self, nome, descricao=""):
        import webview
        self.salvar_fechar()
        pasta = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.isdir(pasta):
            pasta = os.path.expanduser("~")
        try:
            tipo = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
            ext = os.path.splitext(nome)[1].lstrip(".") or "*"
            r = webview.windows[0].create_file_dialog(tipo, directory=pasta, save_filename=nome,
                                                      file_types=("%s (*.%s)" % (descricao or ext.upper(), ext),))
        except Exception as e:
            print("diálogo de salvar falhou:", e, file=sys.stderr)
            return False
        if not r:
            return False
        caminho = r if isinstance(r, str) else r[0]
        try:
            self._f = open(caminho, "wb")
        except OSError:
            return False
        return True

    def salvar_pedaco(self, b64):
        import base64
        if self._f:
            self._f.write(base64.b64decode(b64))
        return True

    def salvar_fechar(self):
        if self._f:
            try:
                self._f.close()
            finally:
                self._f = None
        return True


def executar(scan, titulo=None, sem_moldura=False, pai=None):
    pasta = _pasta_viewer()
    if not pasta or not os.path.isfile(scan):
        print("Visualizador ou scan não encontrado.", file=sys.stderr)
        return 1
    srv, url = _servidor(pasta, scan)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (OSError, AttributeError):
            pass
    try:
        import webview
    except Exception as e:
        if sem_moldura:
            print("pywebview indisponível:", e, file=sys.stderr)
            return 3
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0
    if pai:
        def vigia():
            import time
            while _pid_vivo(pai):
                time.sleep(2)
            os._exit(0)
        threading.Thread(target=vigia, daemon=True).start()
    webview.create_window(titulo or ("Scap — " + os.path.basename(scan)), url, width=1280, height=800,
                          min_size=(400, 300), background_color="#0B1F16", frameless=bool(sem_moldura),
                          js_api=_ApiSalvar(pasta))
    janela = webview.windows[0]
    if sem_moldura and os.environ.get("SCAP_DONO") and os.environ.get("SCAP_POS") and titulo:
        threading.Thread(target=_seguir, args=(titulo, int(os.environ["SCAP_DONO"]), os.environ["SCAP_POS"]), daemon=True).start()

    def travar():
        import time
        time.sleep(1.5)
        while True:
            try:
                f = janela.native
                def fix():
                    try:
                        f.AutoScroll = False
                        f.AutoScrollPosition = type(f.AutoScrollPosition)(0, 0)
                        for c in f.Controls:
                            c.Dock = c.Dock.__class__.Fill
                            c.Location = type(c.Location)(0, 0)
                            try:
                                c.CoreWebView2Controller.NotifyParentWindowPositionChanged()
                            except Exception:
                                pass
                    except Exception:
                        pass
                if f.InvokeRequired:
                    f.Invoke(__import__("System").Action(fix))
                else:
                    fix()
            except Exception:
                pass
            time.sleep(0.12)
    try:
        webview.start()
    except Exception as e:
        print("Falha ao iniciar a janela do visualizador:", e, file=sys.stderr)
        return 4
    return 0


_SERVIDORES = []


def abrir_no_navegador(scan):
    pasta = _pasta_viewer()
    if not pasta or not os.path.isfile(scan):
        raise RuntimeError("Visualizador ou scan não encontrado.")
    srv, url = _servidor(pasta, scan)
    _SERVIDORES.append(srv)
    webbrowser.open(url)
    return url


def abrir(scan, titulo=None, sem_moldura=False, dono=None, arq_pos=None):
    import subprocess
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--visualizar", scan]
    else:
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcscan.py"), "--visualizar", scan]
    if titulo:
        cmd += ["--titulo", titulo]
    if sem_moldura:
        cmd += ["--sem-moldura", "--pai", str(os.getpid())]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    env = dict(os.environ)
    if dono and arq_pos:
        env["SCAP_DONO"], env["SCAP_POS"] = str(int(dono)), arq_pos
    return subprocess.Popen(cmd, env=env, **kw)


def achar_janela(titulo):
    if os.name != "nt":
        return 0
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, titulo) or 0


def _u():
    import ctypes
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return u


class _Fisico:
    def __enter__(self):
        import ctypes
        self.u, self.ant = ctypes.windll.user32, None
        try:
            self.u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            self.u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            self.ant = self.u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            self.ant = None
        return self

    def __exit__(self, *a):
        try:
            if self.ant:
                self.u.SetThreadDpiAwarenessContext(self.ant)
        except (OSError, AttributeError):
            pass


def retangulo(hwnd):
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    with _Fisico() as f:
        f.u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        f.u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def prender(hwnd, dono_hwnd):
    u = _u()
    estilo = u.GetWindowLongPtrW(hwnd, -16)
    estilo &= ~(0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000 | 0x40000000)
    estilo |= 0x80000000
    u.SetWindowLongPtrW(hwnd, -16, estilo)
    ex = u.GetWindowLongPtrW(hwnd, -20)
    ex = (ex | 0x00000080) & ~0x00040000
    u.SetWindowLongPtrW(hwnd, -20, ex)
    u.SetWindowLongPtrW(hwnd, -8, dono_hwnd)
    u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    return True


def ajustar(hwnd, x, y, w, h, visivel=True):
    u = _u()
    if not visivel:
        u.ShowWindow(hwnd, 0)
        return
    with _Fisico():
        u.SetWindowPos(hwnd, None, int(x), int(y), max(1, int(w)), max(1, int(h)), 0x0010 | 0x0200 | 0x0040 | 0x0004)
