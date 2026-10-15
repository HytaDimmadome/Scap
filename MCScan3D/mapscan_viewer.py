# -*- coding: utf-8 -*-
"""Visualizador 3D dentro do Scap: janela própria (sem navegador), servindo o scan por um servidor local."""
import http.server
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


def executar(scan, titulo=None, sem_moldura=False, pai=None):
    """Roda na janela do visualizador (bloqueia até fechar)."""
    pasta = _pasta_viewer()
    if not pasta or not os.path.isfile(scan):
        print("Visualizador ou scan não encontrado.", file=sys.stderr)
        return 1
    srv, url = _servidor(pasta, scan)
    try:
        import webview
    except Exception as e:
        if sem_moldura:            # embutido no app: nunca abre o navegador (o app mostra o aviso)
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
                          min_size=(400, 300), background_color="#0B1F16", frameless=bool(sem_moldura))
    janela = webview.windows[0]

    def travar():                       # impede a página de "andar" dentro da janela embutida (focar um botão rolava o painel)
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
                            try:      # o WebView2 precisa saber que a janela mudou de lugar (senão desenha deslocado ao arrastar)
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
    if sem_moldura:
        threading.Thread(target=travar, daemon=True).start()
    try:
        webview.start()
    except Exception as e:
        print("Falha ao iniciar a janela do visualizador:", e, file=sys.stderr)
        return 4
    return 0


_SERVIDORES = []


def abrir_no_navegador(scan):
    """Serve o visualizador neste processo e abre no navegador padrão (continua vivo enquanto o app roda)."""
    pasta = _pasta_viewer()
    if not pasta or not os.path.isfile(scan):
        raise RuntimeError("Visualizador ou scan não encontrado.")
    srv, url = _servidor(pasta, scan)
    _SERVIDORES.append(srv)
    webbrowser.open(url)
    return url


def abrir(scan, titulo=None, sem_moldura=False):
    """Chamado pelo app principal: abre o visualizador em outro processo (mesmo programa)."""
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
        kw["creationflags"] = 0x08000000  # sem janela de console
    return subprocess.Popen(cmd, **kw)


# ---- embutir a janela do visualizador dentro do app (Windows) ----
def achar_janela(titulo):
    if os.name != "nt":
        return 0
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, titulo) or 0


def prender(hwnd, pai_hwnd, w, h):
    """Transforma a janela do visualizador em filha do quadro do app."""
    import ctypes
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    u.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.MoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    estilo = u.GetWindowLongPtrW(hwnd, -16)
    estilo &= ~(0x00C00000 | 0x00040000 | 0x80000000 | 0x00080000 | 0x00020000 | 0x00010000)
    estilo |= 0x40000000 | 0x10000000
    u.SetWindowLongPtrW(hwnd, -16, estilo)
    u.SetParent(hwnd, pai_hwnd)
    u.MoveWindow(hwnd, 0, 0, int(w), int(h), True)
    return True


def ajustar(hwnd, w, h):
    import ctypes
    u = ctypes.windll.user32
    u.MoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    u.MoveWindow(hwnd, 0, 0, int(w), int(h), True)
