# -*- coding: utf-8 -*-
"""Scap: janela principal (tkinter). Layout: barra lateral verde, páginas Mapa / Configurações / Mods / Sobre."""
import hashlib
import io
import json
import math
import os
import queue
import sys
import threading
import time
import webbrowser
import zipfile
import tkinter as tk
from tkinter import filedialog

import numpy as np
from PIL import Image, ImageDraw, ImageTk, ImageFont

import mcscan
import mapscan_ui as ui

sys.setswitchinterval(0.001)   # a interface ganha a vez mais vezes enquanto o scan trabalha
from mapscan_ui import (VERDE, VERDE_HOV, CREME, CREME_CLARO, CREME_ESC, BORDA, VERMELHO, TEXTO, MUDO, OK, ERRO,
                        AVISO, Btn, IconBtn, Check, Painel, Campo, Dropdown, NavItem, BarraProgresso, ListaRolavel,
                        rr_img, tk_icone, fonte)

VERSAO = "1.0.0 (build 15/10 20h40 - escala DPI)"
NOME = "Scap"

# ---------------------------------------------------------------- configuração
def pasta_config():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        p = os.path.join(base, "Scap")
    else:
        p = os.path.join(os.path.expanduser("~"), ".config", "mapscan")
    os.makedirs(p, exist_ok=True)
    return p


def pasta_minecraft():
    """Pasta .minecraft padrão do sistema (ou None)."""
    cands = []
    if os.environ.get("APPDATA"):
        cands.append(os.path.join(os.environ["APPDATA"], ".minecraft"))
    home = os.path.expanduser("~")
    cands += [os.path.join(home, ".minecraft"), os.path.join(home, "Library", "Application Support", "minecraft")]
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def sub_mc(nome, atual=""):
    """Pasta inicial para um seletor de arquivos: a última usada, senão .minecraft/<nome>, senão .minecraft."""
    if atual and os.path.isdir(atual):
        return atual
    mc = pasta_minecraft()
    if mc:
        p = os.path.join(mc, nome)
        return p if os.path.isdir(p) else mc
    return os.path.expanduser("~")


PADRAO = {"jar": "", "mods": "", "packs": "", "ymin": 59, "ymax": 131, "texturas": True, "estados": True, "animadas": True,
          "mods_off": [], "ultimo_mundo": "", "pasta_saida": "", "ultima_pasta_packs": ""}


class Config:
    def __init__(self):
        self.arq = os.path.join(pasta_config(), "config.json")
        self.d = dict(PADRAO)
        try:
            with open(self.arq, "r", encoding="utf-8") as f:
                self.d.update(json.load(f))
        except Exception:
            pass

    def __getitem__(self, k):
        return self.d.get(k, PADRAO.get(k))

    def __setitem__(self, k, v):
        self.d[k] = v

    def salvar(self):
        try:
            with open(self.arq, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=1)
        except Exception:
            pass


# ---------------------------------------------------------------- visão de cima (com cache em disco)
def chave_visao(pasta):
    h = hashlib.sha1(os.path.abspath(pasta).encode("utf-8"))
    try:
        for f in sorted(os.listdir(pasta)):
            if f.endswith(".mca"):
                st = os.stat(os.path.join(pasta, f))
                h.update(("%s|%d|%d" % (f, st.st_size, int(st.st_mtime))).encode())
    except OSError:
        pass
    return h.hexdigest()[:20]


def carregar_visao_cache(pasta):
    arq = os.path.join(pasta_config(), "visao_%s.npz" % chave_visao(pasta))
    if not os.path.isfile(arq):
        return None
    try:
        z = np.load(arq, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        meta.update({"rgb": z["rgb"], "topo": z["topo"], "topo_max": z["topo_max"], "nome_idx": z["nome_idx"]})
        return meta
    except Exception:
        return None


def salvar_visao_cache(pasta, vis):
    arq = os.path.join(pasta_config(), "visao_%s.npz" % chave_visao(pasta))
    try:
        meta = {k: vis[k] for k in ("res", "x0", "z0", "w", "h", "nomes")}
        np.savez_compressed(arq, rgb=vis["rgb"], topo=vis["topo"], topo_max=vis["topo_max"],
                            nome_idx=vis["nome_idx"], meta=json.dumps(meta))
        # mantém só as 12 mais recentes
        arqs = sorted((os.path.join(pasta_config(), f) for f in os.listdir(pasta_config()) if f.startswith("visao_")),
                      key=os.path.getmtime, reverse=True)
        for velho in arqs[12:]:
            os.remove(velho)
    except Exception:
        pass


# ---------------------------------------------------------------- imagens do app
def imagem(nome, largura=None, altura=None):
    im = Image.open(ui.asset(nome)).convert("RGBA")
    if largura or altura:
        if largura and not altura:
            altura = round(im.height * largura / im.width)
        elif altura and not largura:
            largura = round(im.width * altura / im.height)
        im = im.resize((largura, altura), Image.LANCZOS)
    return im


def cubo_grama(px):
    """Cubo isométrico de grama (ícone padrão dos mods sem logo)."""
    S = 4
    n = px * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n / 2
    r = n * .46
    top = [(c, c - r), (c + r * .87, c - r * .5), (c, c), (c - r * .87, c - r * .5)]
    esq = [(c - r * .87, c - r * .5), (c, c), (c, c + r), (c - r * .87, c + r * .5)]
    dir_ = [(c + r * .87, c - r * .5), (c, c), (c, c + r), (c + r * .87, c + r * .5)]
    d.polygon(top, fill=(98, 160, 62, 255))
    d.polygon(esq, fill=(121, 85, 58, 255))
    d.polygon(dir_, fill=(96, 66, 44, 255))
    d.line(top + [top[0]], fill=(40, 70, 30, 255), width=max(1, S // 2))
    return im.resize((px, px), Image.LANCZOS)


def arte_vazio(w, h):
    """Paisagem de blocos bem clara para o fundo da tela vazia."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cor = (226, 215, 186, 110)
    u = max(10, w // 60)
    base = h - u * 2
    import random
    rnd = random.Random(7)
    for cx, larg in ((0.16, 7), (0.84, 8)):
        x0 = int(w * cx)
        for k in range(larg):
            esc = larg - k
            d.rectangle((x0 - esc * u * 2 // 2, base - k * u * 2, x0 + esc * u * 2 // 2, base - k * u * 2 + u * 2), fill=cor)
    for cx in (0.34, 0.62, 0.5):
        x0 = int(w * cx)
        d.rectangle((x0 - u // 2, base - u * 5, x0 + u // 2, base), fill=cor)
        for k in range(3):
            d.rectangle((x0 - u * (3 - k), base - u * (8 - k * 2), x0 + u * (3 - k), base - u * (6 - k * 2)), fill=cor)
    d.rectangle((0, base, w, h), fill=cor)
    return im


# ---------------------------------------------------------------- diálogos
class Dialogo(tk.Toplevel):
    TIPOS = {"erro": ("x", ERRO, "Erro"), "aviso": ("aviso", AVISO, "Atenção"), "ok": ("check", OK, "Concluído"),
             "info": ("info", VERDE, "Informação")}

    def __init__(self, app, tipo, titulo, mensagem, botoes=(("OK", "primario"),), largura=470, detalhes=None):
        super().__init__(app)
        self.app, self.resultado = app, None
        self.overrideredirect(True)
        self.configure(bg=BORDA)
        self.transient(app)
        ic, cor, padrao = self.TIPOS.get(tipo, self.TIPOS["info"])
        corpo = tk.Frame(self, bg=CREME_CLARO)
        corpo.pack(fill="both", expand=True, padx=1, pady=1)
        topo = tk.Frame(corpo, bg=CREME_CLARO)
        topo.pack(fill="x", padx=22, pady=(20, 6))
        c = tk.Canvas(topo, width=54, height=54, bg=CREME_CLARO, highlightthickness=0)
        c.pack(side="left", anchor="n")
        if tipo == "aviso":
            c.create_image(27, 27, image=tk_icone("aviso", 46, cor))
        else:
            c.create_image(27, 27, image=rr_img(50, 50, 25, cor))
            c.create_image(27, 27, image=tk_icone(ic, 28, "#FFFFFF"))
        txt = tk.Frame(topo, bg=CREME_CLARO)
        txt.pack(side="left", fill="both", expand=True, padx=(16, 0))
        tk.Label(txt, text=titulo or padrao, bg=CREME_CLARO, fg=TEXTO, font=fonte(13, "bold"), anchor="w").pack(fill="x")
        tk.Label(txt, text=mensagem, bg=CREME_CLARO, fg=TEXTO, font=fonte(10), justify="left", anchor="w",
                 wraplength=largura - 150).pack(fill="x", pady=(4, 0))
        if detalhes:
            cx = tk.Frame(corpo, bg=CREME_CLARO)
            cx.pack(fill="x", padx=22, pady=(4, 0))
            t = tk.Text(cx, height=min(8, detalhes.count("\n") + 2), bg="#FBF0DC", fg=MUDO, font=fonte(9), bd=0,
                        wrap="word", highlightthickness=1, highlightbackground=BORDA)
            t.insert("1.0", detalhes)
            t.config(state="disabled")
            t.pack(fill="x")
        rod = tk.Frame(corpo, bg=CREME_CLARO)
        rod.pack(fill="x", padx=22, pady=(14, 18))
        for i, (rot, est) in reversed(list(enumerate(botoes))):
            Btn(rod, rot, lambda i=i: self._fim(i), estilo=est, h=40, bg=CREME_CLARO, w=max(110, 40 + 9 * len(rot))).pack(
                side="right", padx=(8, 0))
        xb = IconBtn(self, "x", lambda: self._fim(len(botoes) - 1), tam=28, px=14, bg=CREME_CLARO, hov=CREME_ESC)
        xb.place(relx=1, x=-36, y=8)
        self.update_idletasks()
        w, h = largura, self.winfo_reqheight()
        ui.centralizar(self, app, w, h)
        self.bind("<Escape>", lambda e: self._fim(len(botoes) - 1))
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.update_idletasks()
            self.wait_visibility()
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _fim(self, i):
        self.resultado = i
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    @classmethod
    def mostrar(cls, app, tipo, titulo, mensagem, botoes=(("OK", "primario"),), **k):
        d = cls(app, tipo, titulo, mensagem, botoes, **k)
        app.wait_window(d)
        return d.resultado


# ---------------------------------------------------------------- mapa de cima
class MapaView(tk.Canvas):
    def __init__(self, master, ao_selecionar, ao_hover):
        super().__init__(master, bg=CREME, highlightthickness=0, bd=0, cursor="crosshair")
        self.ao_selecionar, self.ao_hover = ao_selecionar, ao_hover
        self.vis = None
        self.pir = []
        self.s, self.ox, self.oy = 1.0, 0.0, 0.0
        self.s_fit = 1.0
        self.sel = None
        self.arrasto = None
        self.pan = None
        self._foto = None
        self._pend = False
        self.msg = None
        self.bind("<Configure>", lambda e: self._agenda())
        self.bind("<ButtonPress-1>", self._ini)
        self.bind("<B1-Motion>", self._mov)
        self.bind("<ButtonRelease-1>", self._fim)
        for b in ("2", "3"):
            self.bind("<ButtonPress-" + b + ">", self._pan_ini)
            self.bind("<B" + b + "-Motion>", self._pan_mov)
        self.bind("<Motion>", self._hover)
        self.bind("<MouseWheel>", lambda e: self._roda(e.x, e.y, 1.25 if e.delta > 0 else 0.8))
        self.bind("<Button-4>", lambda e: self._roda(e.x, e.y, 1.25))
        self.bind("<Button-5>", lambda e: self._roda(e.x, e.y, 0.8))
        # controles de zoom (cartão claro no canto)
        self._ctrl = tk.Frame(self, bg=CREME_CLARO, highlightthickness=1, highlightbackground=BORDA)
        for ic, cmd in (("mais", lambda: self._roda(None, None, 1.4)), ("menos", lambda: self._roda(None, None, 1 / 1.4)),
                        ("enquadrar", self.enquadrar)):
            IconBtn(self._ctrl, ic, cmd, tam=40, px=22, bg=CREME_CLARO, hov=CREME_ESC, raio=6).pack(padx=3, pady=2)
        self._lbl = self.create_text(16, 16, anchor="sw", text="", fill=VERDE, font=fonte(9, "bold"), tags="hover")
        self._lbl_bg = None

    # --- dados
    def definir_visao(self, vis):
        self.vis = vis
        rgb = vis["rgb"].copy()
        rgb[vis["nome_idx"] < 0] = (0, 0, 0)
        base = Image.fromarray(rgb, "RGB")
        self.pir = [base]
        while min(self.pir[-1].size) > 300:
            self.pir.append(self.pir[-1].reduce(2))
        self.sel = None
        self.enquadrar()

    def limpar(self):
        self.vis, self.pir, self.sel = None, [], None
        self._agenda()

    def enquadrar(self):
        if not self.pir:
            return
        W, H = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        w, h = self.pir[0].size
        self.s_fit = min(W / w, H / h) * 0.98
        self.s = self.s_fit
        self.ox, self.oy = (W - w * self.s) / 2, (H - h * self.s) / 2
        self._agenda()

    def _agenda(self):
        if not self._pend:
            self._pend = True
            self.after(8, self._desenhar)

    # --- conversões
    def f(self):
        return 16.0 / self.vis["res"]

    def para_bloco(self, vx, vy):
        ix, iy = (vx - self.ox) / self.s, (vy - self.oy) / self.s
        return self.vis["x0"] + ix * self.f(), self.vis["z0"] + iy * self.f()

    def para_tela(self, x, z):
        return (self.ox + (x - self.vis["x0"]) / self.f() * self.s, self.oy + (z - self.vis["z0"]) / self.f() * self.s)

    # --- desenho
    def _desenhar(self):
        self._pend = False
        W, H = self.winfo_width(), self.winfo_height()
        if W < 20 or H < 20:
            return
        self.delete("mapa")
        if not self.pir:
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, W - 1, H - 1), 16, fill=(11, 31, 22, 255))
            self._foto = ImageTk.PhotoImage(im)
            self.create_image(0, 0, anchor="nw", image=self._foto, tags="mapa")
            self.create_text(W / 2, H / 2, text=self.msg or "", fill="#CFE5D4", font=fonte(12), tags="mapa")
            self._ordem()
            return
        k = 0
        while k + 1 < len(self.pir) and self.s * 2 ** (k + 1) <= 1.0:
            k += 1
        sk = self.s * 2 ** k
        base = self.pir[k]
        res = Image.NEAREST if sk >= 3 else Image.BILINEAR
        im = base.transform((W, H), Image.AFFINE, (1 / sk, 0, -self.ox / sk, 0, 1 / sk, -self.oy / sk), res,
                            fillcolor=(0, 0, 0)).convert("RGBA")
        if self.sel:
            x1, z1, x2, z2 = self.sel
            a, b = self.para_tela(x1, z1)
            c, d = self.para_tela(x2 + 1, z2 + 1)
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dd = ImageDraw.Draw(ov)
            dd.rectangle((a, b, c, d), fill=(255, 212, 0, 38), outline=(255, 204, 0, 255), width=3)
            im = Image.alpha_composite(im, ov)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), 16, fill=255)
        im.putalpha(mask)
        self._foto = ImageTk.PhotoImage(im)
        self.create_image(0, 0, anchor="nw", image=self._foto, tags="mapa")
        self._ordem()

    def _ordem(self):
        W = self.winfo_width()
        if not hasattr(self, "_ctrl_id"):
            self._ctrl_id = self.create_window(W - 14, 14, anchor="ne", window=self._ctrl)
        else:
            self.coords(self._ctrl_id, W - 14, 14)
        self.tag_raise(self._ctrl_id)
        self.tag_raise("hover")

    # --- interação
    def _ini(self, e):
        if not self.pir:
            return
        self.arrasto = self.para_bloco(e.x, e.y)

    def _mov(self, e):
        if self.arrasto is None:
            return
        bx, bz = self.para_bloco(e.x, e.y)
        ax, az = self.arrasto
        self.sel = (int(math.floor(min(ax, bx))), int(math.floor(min(az, bz))),
                    int(math.floor(max(ax, bx))), int(math.floor(max(az, bz))))
        self.ao_selecionar(self.sel, False)
        self._agenda()

    def _fim(self, e):
        if self.arrasto is None:
            return
        self.arrasto = None
        if self.sel and self.sel[2] > self.sel[0] and self.sel[3] > self.sel[1]:
            self.ao_selecionar(self.sel, True)

    def _pan_ini(self, e):
        self.pan = (e.x, e.y, self.ox, self.oy)

    def _pan_mov(self, e):
        if self.pan:
            self.ox = self.pan[2] + e.x - self.pan[0]
            self.oy = self.pan[3] + e.y - self.pan[1]
            self._agenda()

    def _roda(self, mx, my, fator):
        if not self.pir:
            return
        W, H = self.winfo_width(), self.winfo_height()
        mx = W / 2 if mx is None else mx
        my = H / 2 if my is None else my
        novo = max(self.s_fit * 0.6, min(self.s * fator, 30.0))
        ix, iy = (mx - self.ox) / self.s, (my - self.oy) / self.s
        self.s = novo
        self.ox, self.oy = mx - ix * novo, my - iy * novo
        self._agenda()

    def _hover(self, e):
        if not self.pir:
            return
        bx, bz = self.para_bloco(e.x, e.y)
        vis = self.vis
        i, j = int((bx - vis["x0"]) / self.f()), int((bz - vis["z0"]) / self.f())
        info = "X=%d  Z=%d" % (bx, bz)
        if 0 <= i < vis["w"] and 0 <= j < vis["h"] and vis["topo"][j, i] > -9000:
            info += "   |   y=%d   |   %s" % (vis["topo"][j, i], vis["nomes"][vis["nome_idx"][j, i]].replace("minecraft:", ""))
        H = self.winfo_height()
        self.itemconfigure("hover", text=info)
        self.coords("hover", 18, H - 14)
        bb = self.bbox("hover")
        if bb:
            if self._lbl_bg is not None:
                self.delete(self._lbl_bg)
            self._lbl_bg = self.create_rectangle(bb[0] - 8, bb[1] - 4, bb[2] + 8, bb[3] + 4, fill=CREME_CLARO,
                                                 outline=BORDA, tags="hoverbg")
            self.tag_lower(self._lbl_bg, "hover")
            self.tag_raise("hover")


# ---------------------------------------------------------------- aplicativo
ETAPAS_SCAN = ["Iniciando leitura do mundo…", "Escaneando blocos…", "Processando dados…", "Gerando arquivo…"]
ETAPAS_MAPA = ["Iniciando leitura do mundo…", "Lendo o mapa de cima…", "Montando o mapa…"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        ui.escolher_fonte(self)
        self.cfg = Config()
        self._preencher_padroes()
        self.title(NOME)
        self.configure(bg=CREME)
        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.ocupado = False
        self.dims = []
        self.vis = None
        self.pasta_mundo = ""
        self.sel_ativa = None
        self.pagina = None
        self._maximizado = False
        self._normal_geo = None
        self._minimizado = False
        self._toast = None
        self._ultimo_scan = None
        self._scan3d = None
        self._proc3d = None
        self._hwnd3d = 0
        self._ult_ret3d = None
        self._overlay = None
        self.ico_mods = {}
        self.splash = Splash(self)
        self.splash.passo(0.10, "Carregando interface…")
        self._montar()
        self.splash.passo(0.65, "Lendo configurações…")
        self._aplicar_cfg()
        self.splash.passo(0.9, "Quase pronto…")
        self.after(250, self._abrir)

    def _preencher_padroes(self):
        """Na primeira execução, já preenche o jar e a pasta de mods a partir da .minecraft padrão."""
        try:
            mc = pasta_minecraft()
            if not mc:
                return
            if not self.cfg["mods"] and os.path.isdir(os.path.join(mc, "mods")):
                self.cfg["mods"] = os.path.join(mc, "mods")
            if not self.cfg["jar"]:
                vs = os.path.join(mc, "versions")
                if os.path.isdir(vs):
                    for v in ["1.20.1"] + sorted(os.listdir(vs), reverse=True):
                        j = os.path.join(vs, v, v + ".jar")
                        if os.path.isfile(j):
                            self.cfg["jar"] = j
                            break
            self.cfg.salvar()
        except Exception:
            pass

    def _abrir(self):
        self.splash.fechar()
        w, h = 1240, 760
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(w, sw - 60), min(h, sh - 90)
        self.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, max((sh - h) // 3, 10)))
        self.minsize(1000, 640)
        self.deiconify()
        self.update_idletasks()
        self._sem_borda()
        self.after(150, self._ler_fila)
        iconpath = ui.asset("emblema.png")
        try:
            self.iconphoto(True, ImageTk.PhotoImage(Image.open(iconpath).resize((64, 64))))
        except Exception:
            pass
        self.mostrar("mapa")

    # ---------- janela sem borda
    def _sem_borda(self):
        """Tira a barra de título do Windows mantendo a janela 'de verdade' (foco, barra de tarefas, diálogos)."""
        self._barra_propria = True
        if os.name == "nt":
            try:
                import ctypes
                self.update_idletasks()
                u = ctypes.windll.user32
                u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
                u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
                u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
                u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
                hwnd = u.GetParent(self.winfo_id()) or self.winfo_id()
                estilo = u.GetWindowLongPtrW(hwnd, -16)
                estilo &= ~(0x00C00000 | 0x00040000)   # sem barra de título e sem moldura grossa
                estilo |= 0x00020000 | 0x00010000 | 0x00080000   # botões min, max, menu do sistema
                u.SetWindowLongPtrW(hwnd, -16, estilo)
                u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_uint]
                u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010)
                try:  # cantos arredondados no Windows 11
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(ctypes.c_int(2)), 4)
                except Exception:
                    pass
                return
            except Exception:
                pass
        try:
            self.overrideredirect(True)
        except Exception:
            self._barra_propria = False

    def minimizar(self):
        try:
            self.iconify()
        except Exception:
            pass

    def _area_util(self):
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                r = wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)
                return r.left, r.top, r.right - r.left, r.bottom - r.top
            except Exception:
                pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def maximizar(self):
        if not self._maximizado:
            self._normal_geo = self.geometry()
            x, y, w, h = self._area_util()
            self.geometry("%dx%d+%d+%d" % (w, h, x, y))
            self._maximizado = True
            self.btn_max.trocar_icone("restaurar")
        else:
            if self._normal_geo:
                self.geometry(self._normal_geo)
            self._maximizado = False
            self.btn_max.trocar_icone("max")

    def _drag_ini(self, e):
        if self._maximizado:
            return
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_mov(self, e):
        if self._maximizado:
            return
        self.geometry("+%d+%d" % (e.x_root - self._dx, e.y_root - self._dy))

    def _redim_ini(self, e, modo):
        if self._maximizado:
            return
        self._rd = (modo, e.x_root, e.y_root, self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height(), 0.0)

    def _redim_mov(self, e):
        rd = getattr(self, "_rd", None)
        if not rd or self._maximizado:
            return
        agora = time.time()
        if agora - rd[7] < 0.04:   # no máximo ~25 atualizações por segundo
            return
        modo, mx, my, x, y, w, h, _ = rd
        dx, dy = e.x_root - mx, e.y_root - my
        nx, ny, nw, nh = x, y, w, h
        if "e" in modo:
            nw = max(1000, w + dx)
        if "s" in modo:
            nh = max(640, h + dy)
        if "w" in modo:
            nw = max(1000, w - dx)
            nx = x + (w - nw)
        if "n" in modo:
            nh = max(640, h - dy)
            ny = y + (h - nh)
        self.geometry("%dx%d+%d+%d" % (nw, nh, nx, ny))
        self._rd = rd[:7] + (agora,)

    # ---------- montagem
    def _montar(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._montar_lateral()
        self.principal = tk.Frame(self, bg=CREME)
        self.principal.grid(row=0, column=1, sticky="nsew")
        self.principal.columnconfigure(0, weight=1)
        self.principal.rowconfigure(1, weight=1)
        self._montar_topo()
        self.area = tk.Frame(self.principal, bg=CREME)
        self.area.grid(row=1, column=0, sticky="nsew", padx=(22, 22), pady=(0, 20))
        self.area.columnconfigure(0, weight=1)
        self.area.rowconfigure(0, weight=1)
        self.paginas = {
            "mapa": self._pag_mapa(), "3d": self._pag_3d(), "config": self._pag_config(), "mods": self._pag_mods(), "sobre": self._pag_sobre()}
        self.bind("<Control-m>", lambda e: self.mostrar("mapa"))
        self.bind("<Control-s>", lambda e: self.mostrar("config"))
        self.bind("<Control-Key-3>", lambda e: self.mostrar("3d"))
        self.bind("<Control-o>", lambda e: self.abrir_scan_existente())
        self.bind("<Alt-F4>", lambda e: self.sair())
        self.protocol("WM_DELETE_WINDOW", self.sair)
        # bordas e cantos para redimensionar (a janela não tem moldura nativa)
        nt = os.name == "nt"
        cur = {"e": "size_we" if nt else "sb_h_double_arrow", "s": "size_ns" if nt else "sb_v_double_arrow",
               "w": "size_we" if nt else "sb_h_double_arrow", "se": "size_nw_se" if nt else "bottom_right_corner",
               "sw": "size_ne_sw" if nt else "bottom_left_corner"}
        for modo, kw, cor in (("e", dict(relx=1, rely=0, anchor="ne", width=5, relheight=1), CREME),
                              ("s", dict(x=250, rely=1, anchor="sw", height=5, relwidth=1, width=-250), CREME),
                              ("s", dict(x=0, rely=1, anchor="sw", height=5, width=250), VERDE),
                              ("w", dict(relx=0, rely=0, anchor="nw", width=4, relheight=1), VERDE),
                              ("se", dict(relx=1, rely=1, anchor="se", width=14, height=14), CREME),
                              ("sw", dict(relx=0, rely=1, anchor="sw", width=12, height=12), VERDE)):
            h = tk.Frame(self, bg=cor, cursor=cur[modo])
            h.place(**kw)
            h.bind("<ButtonPress-1>", lambda e, m=modo: self._redim_ini(e, m))
            h.bind("<B1-Motion>", self._redim_mov)

    def _montar_lateral(self):
        lat = tk.Frame(self, bg=VERDE, width=250)
        lat.grid(row=0, column=0, sticky="ns")
        lat.grid_propagate(False)
        lat.pack_propagate(False)
        self.lateral = lat
        self.img_logo = ui.tk_pil(ui.marca_img(190, "#FFF5DB"))
        lg = tk.Label(lat, image=self.img_logo, bg=VERDE, cursor="hand2")
        lg.pack(pady=(30, 26))
        lg.bind("<Button-3>", self._menu_contexto)
        lg.bind("<ButtonPress-1>", self._drag_ini)
        lg.bind("<B1-Motion>", self._drag_mov)
        self.nav = {}
        for chave, rot, ic in (("mapa", "Mapa", "mapa"), ("3d", "Visualizar em 3D", "cubo"),
                               ("config", "Configurações", "engrenagem"),
                               ("mods", "Mods", "mods"), ("sobre", "Sobre", "info")):
            n = NavItem(lat, rot, ic, lambda c=chave: self.mostrar(c))
            n.pack(fill="x", padx=16, pady=2)
            n.bind("<Button-3>", self._menu_contexto)
            self.nav[chave] = n
        # faixa xadrez bem embaixo e o mascote logo acima
        sq = 250 / 9.0
        xadrez = Image.new("RGB", (250, round(sq * 2)), ui.rgb(VERDE))
        dd = ImageDraw.Draw(xadrez)
        for r in range(2):
            for c in range(10):
                if (r + c) % 2 == 0:
                    dd.rectangle((round(c * sq), round(r * sq), round((c + 1) * sq) - 1, round((r + 1) * sq) - 1), fill=ui.rgb("#FFF5DB"))
        self.img_xad = ui.tk_pil(xadrez)
        tk.Label(lat, image=self.img_xad, bg=VERDE, bd=0).pack(side="bottom", fill="x")
        self.img_emb = ui.tk_pil(imagem("emblema.png", 190))
        tk.Label(lat, image=self.img_emb, bg=VERDE).pack(side="bottom", pady=(0, 2))

    def _montar_topo(self):
        topo = tk.Frame(self.principal, bg=CREME, height=44)
        topo.grid(row=0, column=0, sticky="ew")
        topo.grid_propagate(False)
        topo.bind("<ButtonPress-1>", self._drag_ini)
        topo.bind("<B1-Motion>", self._drag_mov)
        topo.bind("<Double-Button-1>", lambda e: self.maximizar())
        fechar = tk.Canvas(topo, width=58, height=34, bg=CREME, highlightthickness=0, cursor="hand2")
        fechar.place(relx=1, x=-6, y=0, anchor="ne")
        self._fechar_cv = fechar
        self._pintar_fechar(False)
        fechar.bind("<Enter>", lambda e: self._pintar_fechar(True))
        fechar.bind("<Leave>", lambda e: self._pintar_fechar(False))
        fechar.bind("<ButtonRelease-1>", lambda e: self.sair())
        self.btn_max = IconBtn(topo, "max", self.maximizar, tam=34, px=18, bg=CREME, hov=CREME_ESC, raio=6)
        self.btn_max.place(relx=1, x=-70, y=0, anchor="ne")
        IconBtn(topo, "min", self.minimizar, tam=34, px=18, bg=CREME, hov=CREME_ESC, raio=6).place(
            relx=1, x=-108, y=0, anchor="ne")

    def _pintar_fechar(self, hov):
        c = self._fechar_cv
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=rr_img(58, 34, 8, VERM_HOV if hov else VERMELHO))
        c.create_image(29, 17, image=tk_icone("fechar", 18, "#FFFFFF"))

    def _menu_contexto(self, e):
        m = tk.Menu(self, tearoff=0, bg=CREME_CLARO, fg=TEXTO, activebackground=VERDE, activeforeground=CREME,
                    font=fonte(10), bd=1)
        m.add_command(label="Mapa                      Ctrl+M", command=lambda: self.mostrar("mapa"))
        m.add_command(label="Visualizar em 3D      Ctrl+3", command=lambda: self.mostrar("3d"))
        m.add_command(label="Configurações        Ctrl+S", command=lambda: self.mostrar("config"))
        m.add_command(label="Mods", command=lambda: self.mostrar("mods"))
        m.add_command(label="Abrir scan 3D...      Ctrl+O", command=self.abrir_scan_existente)
        m.add_separator()
        m.add_command(label="Sobre", command=lambda: self.mostrar("sobre"))
        m.add_separator()
        m.add_command(label="Sair                        Alt+F4", command=self.sair)
        m.tk_popup(e.x_root, e.y_root)

    def mostrar(self, nome):
        if self.pagina == nome:
            return
        for k, f in self.paginas.items():
            f.grid_remove()
        self.paginas[nome].grid(row=0, column=0, sticky="nsew")
        self.pagina = nome
        for k, n in self.nav.items():
            n.definir_ativo(k == nome)
        if nome == "3d" and self._ultimo_scan and self._scan3d != self._ultimo_scan:
            self.after(50, lambda: self._carregar_3d(self._ultimo_scan))
        if nome == "mods":
            self._listar_mods(forcar=False)
        if nome == "config":
            self._cfg_para_campos()

    def sair(self):
        if self.ocupado:
            if Dialogo.mostrar(self, "aviso", "Atenção", "Há uma operação em andamento. Deseja cancelar e sair?",
                               (("Sair", "primario"), ("Continuar", "secundario"))) != 0:
                return
            self.cancelar.set()
        self._parar_3d()
        self._guardar_cfg()
        self.destroy()

    # ---------- cabeçalho padrão das páginas
    def _cabecalho(self, pai, icone, titulo, sub):
        p = Painel(pai, bg=CREME, fundo=CREME_CLARO, pad=14)
        i = p.inner
        c = tk.Canvas(i, width=64, height=64, bg=CREME_CLARO, highlightthickness=0)
        c.pack(side="left")
        c.create_image(32, 32, image=rr_img(62, 62, 14, VERDE))
        c.create_image(32, 32, image=tk_icone(icone, 38, "#FFF5DB"))
        t = tk.Frame(i, bg=CREME_CLARO)
        t.pack(side="left", padx=18)
        tk.Label(t, text=titulo, bg=CREME_CLARO, fg=TEXTO, font=fonte(22, "bold")).pack(anchor="w")
        tk.Label(t, text=sub, bg=CREME_CLARO, fg=MUDO, font=fonte(11)).pack(anchor="w")
        return p

    def _titulo_secao(self, pai, texto, bg=CREME_CLARO):
        return tk.Label(pai, text=texto, bg=bg, fg=TEXTO, font=fonte(14, "bold"))

    # ---------- página: mapa
    def _pag_mapa(self):
        pg = tk.Frame(self.area, bg=CREME)
        pg.columnconfigure(0, weight=1)
        pg.rowconfigure(0, weight=1)
        # estado vazio
        self.vazio = tk.Canvas(pg, bg=CREME, highlightthickness=0)
        self.vazio.grid(row=0, column=0, sticky="nsew")
        self.vazio.bind("<Configure>", self._desenhar_vazio)
        self.btn_sel = Btn(self.vazio, "Selecionar pasta do mundo", self.escolher_mundo, estilo="primario",
                           icone="pasta", w=300, h=54, tam=12, raio=12, icone_px=24, bg=CREME_CLARO)
        self.btn_abrir_scan = Btn(self.vazio, "Abrir um scan 3D (.scap)", self.abrir_scan_existente, estilo="secundario",
                                  icone="abrir", w=300, h=44, tam=10, bg=CREME_CLARO)
        # mapa
        self.mapa = MapaView(pg, self._ao_selecionar, None)
        # painéis inferiores
        self.base = tk.Frame(pg, bg=CREME)
        self.base.columnconfigure(0, weight=5, uniform="p")
        self.base.columnconfigure(1, weight=5, uniform="p")
        self.base.columnconfigure(2, weight=5, uniform="p")
        self.base.columnconfigure(3, weight=0)
        self.v_mundo = tk.StringVar()
        self.v_dim = tk.StringVar()
        self.v = {k: tk.StringVar() for k in ("x1", "z1", "x2", "z2", "ymin", "ymax")}
        self.var_tex = tk.BooleanVar(value=True)
        self.var_estados = tk.BooleanVar(value=True)
        self.var_packs = tk.BooleanVar(value=False)

        def num(p, n, t):
            c = tk.Canvas(p, width=30, height=30, bg=CREME_CLARO, highlightthickness=0)
            c.create_image(15, 15, image=rr_img(28, 28, 14, VERDE))
            c.create_text(15, 15, text=str(n), fill="#FFF5DB", font=fonte(11, "bold"))
            c.grid(row=0, column=0, sticky="w")
            tk.Label(p, text=t, bg=CREME_CLARO, fg=TEXTO, font=fonte(11, "bold")).grid(row=0, column=1, sticky="w", padx=8)

        # 1 mundo + 2 mapa de cima
        p1 = Painel(self.base, bg=CREME)
        p1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        i = p1.inner
        i.columnconfigure(0, weight=1)
        num_f = tk.Frame(i, bg=CREME_CLARO)
        num_f.grid(row=0, column=0, sticky="w")
        num(num_f, 1, "MUNDO")
        lin = tk.Frame(i, bg=CREME_CLARO)
        lin.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        lin.columnconfigure(0, weight=1)
        self.campo_mundo = Campo(lin, self.v_mundo, h=38)
        self.campo_mundo.grid(row=0, column=0, sticky="ew")
        self.campo_mundo.entry.bind("<Return>", lambda e: self.carregar_mundo(self.v_mundo.get().strip()))
        self.btn_pasta = IconBtn(lin, "pasta", self.escolher_mundo, tam=38, px=20, bg=CREME_CLARO, hov=VERDE_HOV,
                                 cor="#FFF5DB", hov_icone="#FFF5DB", raio=9)
        self.btn_pasta.bgc = VERDE
        self.btn_pasta._desenhar()
        self.btn_pasta.grid(row=0, column=1, padx=(6, 0))
        nf2 = tk.Frame(i, bg=CREME_CLARO)
        nf2.grid(row=2, column=0, sticky="w")
        num(nf2, 2, "MAPA DE CIMA")
        self.dd_dim = Dropdown(i, self.v_dim, [], comando=lambda v: self._recarregar_mapa(), bg=CREME_CLARO,
                               icone=ui.tk_pil(cubo_grama(24)))
        self.dd_dim.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        # 3 área
        p3 = Painel(self.base, bg=CREME)
        p3.grid(row=0, column=1, sticky="nsew", padx=5)
        i = p3.inner
        nf3 = tk.Frame(i, bg=CREME_CLARO)
        nf3.grid(row=0, column=0, columnspan=4, sticky="w")
        num(nf3, 3, "ÁREA DO SCAN")
        for lin, (a, b) in enumerate((("x1", "z1"), ("x2", "z2"), ("ymin", "ymax"))):
            for col, k in enumerate((a, b)):
                rot = {"x1": "X1", "z1": "Z1", "x2": "X2", "z2": "Z2", "ymin": "Y mín.", "ymax": "Y máx."}[k]
                tk.Label(i, text=rot, bg=CREME_CLARO, fg=TEXTO, font=fonte(10)).grid(row=1 + lin, column=col * 2, sticky="w",
                                                                                   padx=(0 if col == 0 else 14, 6), pady=4)
                c = Campo(i, self.v[k], h=34, largura=96, justificar="center")
                c.grid(row=1 + lin, column=col * 2 + 1, sticky="ew", pady=4)
                c.entry.bind("<Return>", lambda e: self._sel_de_campos())
                c.entry.bind("<FocusOut>", lambda e: self._sel_de_campos())
        i.columnconfigure(1, weight=1)
        i.columnconfigure(3, weight=1)
        # 4 texturas
        p4 = Painel(self.base, bg=CREME)
        p4.grid(row=0, column=2, sticky="nsew", padx=(5, 10))
        i = p4.inner
        nf4 = tk.Frame(i, bg=CREME_CLARO)
        nf4.grid(row=0, column=0, sticky="w")
        num(nf4, 4, "TEXTURAS E MODS")
        for r, (txt, var) in enumerate((("Usar texturas do jogo e dos mods", self.var_tex),
                                         ("Salvar estados dos blocos (escadas, lajes, portas)", self.var_estados),
                                         ("Resource packs (opcional)", self.var_packs))):
            Check(i, txt, var, bg=CREME_CLARO, tam=10).grid(row=1 + r, column=0, sticky="w", pady=(8 if r == 0 else 3, 0))
        # escanear
        self.btn_scan = Btn(self.base, "ESCANEAR", self.escanear, estilo="perigo", icone="play", w=190, h=150, tam=17,
                            raio=16, icone_px=34, bg=CREME)
        self.btn_scan.grid(row=0, column=3, sticky="ns", padx=(0, 0))
        # barra
        self.rodape = tk.Frame(pg, bg=CREME)
        self.rodape.columnconfigure(0, weight=1)
        self.barra = BarraProgresso(self.rodape, bg=CREME, h=20)
        self.barra.grid(row=0, column=0, sticky="ew", pady=(14, 0))
        self.lbl_pct = tk.Label(self.rodape, text="0%", bg=CREME, fg=TEXTO, font=fonte(12, "bold"), width=5)
        self.lbl_pct.grid(row=0, column=1, pady=(14, 0), padx=(10, 6))
        self.lbl_status = tk.Label(self.rodape, text="", bg=CREME, fg=TEXTO, font=fonte(10), anchor="w")
        self.lbl_status.grid(row=0, column=2, sticky="w", padx=(6, 0), pady=(14, 0))
        self._estado_mapa("vazio", pg)
        return pg

    def _estado_mapa(self, estado, pg=None):
        pg = pg or self.paginas["mapa"]
        if estado == "vazio":
            self.mapa.grid_remove()
            self.base.grid_remove()
            self.rodape.grid_remove()
            self.vazio.grid(row=0, column=0, sticky="nsew")
        else:
            self.vazio.grid_remove()
            self.mapa.grid(row=0, column=0, sticky="nsew")
            self.base.grid(row=1, column=0, sticky="ew", pady=(14, 0))
            self.rodape.grid(row=2, column=0, sticky="ew")

    def _desenhar_vazio(self, e):
        w, h = e.width, e.height
        if w < 100 or h < 100:
            return
        c = self.vazio
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=rr_img(w, h, 16, CREME_CLARO, BORDA, 2))
        self._arte = ui.tk_pil(arte_vazio(w - 8, int(h * .85)))
        c.create_image(4, h - 4, anchor="sw", image=self._arte)
        cx, cy = w / 2, h / 2
        self._pasta_img = ui.tk_pil(self._pasta_grande())
        c.create_image(cx, cy - 84, image=self._pasta_img)
        c.create_text(cx, cy + 6, text="Nenhum mundo carregado", fill=TEXTO, font=fonte(20, "bold"))
        c.create_text(cx, cy + 50, text="Selecione a pasta do seu mundo do Minecraft\npara começar a gerar o mapa.",
                      fill=MUDO, font=fonte(12), justify="center")
        c.create_window(cx, cy + 124, window=self.btn_sel)
        c.create_window(cx, cy + 196, window=self.btn_abrir_scan)

    def _pasta_grande(self):
        S = 4
        w, h = 150 * S, 140 * S
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        v = ui.rgb(VERDE)
        d.rounded_rectangle((8 * S, 38 * S, 118 * S, 130 * S), 10 * S, fill=v + (255,))
        d.polygon([(8 * S, 38 * S), (8 * S, 28 * S), (48 * S, 28 * S), (58 * S, 38 * S)], fill=v + (255,))
        d.rounded_rectangle((16 * S, 52 * S, 108 * S, 128 * S), 8 * S, fill=ui.rgb(CREME_CLARO) + (255,))
        cubo = cubo_grama(54 * 1).resize((54 * S, 54 * S), Image.LANCZOS)
        im.alpha_composite(cubo, (30 * S, 66 * S))
        for (x0, y0, x1, y1) in ((92, 12, 98, 28), (112, 20, 124, 30)):
            d.line((x0 * S, y0 * S, x1 * S, y1 * S), fill=v + (255,), width=5 * S)
        return im.resize((150, 140), Image.LANCZOS)

    # ---------- mundo e mapa
    def escolher_mundo(self):
        ult = os.path.dirname(self.cfg["ultimo_mundo"]) if self.cfg["ultimo_mundo"] else ""
        ini = ult if ult and os.path.isdir(ult) and "saves" in ult.replace("\\", "/").lower() else sub_mc("saves")
        pasta = filedialog.askdirectory(parent=self, title="Pasta do mundo (dentro de .minecraft/saves)", initialdir=ini)
        if pasta:
            self.carregar_mundo(pasta)

    def carregar_mundo(self, pasta):
        if self.ocupado:
            return
        pasta = os.path.abspath(pasta) if pasta else ""
        dims = mcscan.achar_dimensoes(pasta) if os.path.isdir(pasta) else []
        if not dims:
            self.campo_mundo.estado("erro")
            if self.pagina == "mapa":
                self._estado_mapa("mapa") if self.vis else None
            Dialogo.mostrar(self, "erro", "Erro", "Não foi possível carregar o mundo.\nVerifique se o caminho selecionado "
                            "está correto: a pasta deve conter a pasta \"region\".")
            return
        self.pasta_mundo = pasta
        self.dims = dims
        self.v_mundo.set(pasta)
        self.campo_mundo.estado("ok")
        self.dd_dim.definir([d[0] for d in dims])
        self.v_dim.set(dims[0][0])
        self.cfg["ultimo_mundo"] = pasta
        if not self.cfg["jar"]:
            self.cfg["jar"] = mcscan.achar_jar_minecraft(pasta) or ""
        if not self.cfg["mods"]:
            self.cfg["mods"] = mcscan.achar_pasta_mods(pasta) or ""
        self.cfg.salvar()
        self._cfg_para_campos()
        for k, ch in (("ymin", "ymin"), ("ymax", "ymax")):
            if not self.v[k].get():
                self.v[k].set(str(self.cfg[ch]))
        self._estado_mapa("mapa")
        self.update_idletasks()
        self._recarregar_mapa()

    def _pasta_dim(self):
        for n, p in self.dims:
            if n == self.v_dim.get():
                return p
        return self.dims[0][1] if self.dims else None

    def _recarregar_mapa(self):
        if self.ocupado or not self.dims:
            return
        pasta = self._pasta_dim()
        self.mapa.limpar()
        self.vis = None
        cache = carregar_visao_cache(pasta)
        if cache is not None:
            self._visao_pronta(cache, do_cache=True)
            return
        self.mapa.msg = "Gerando mapa…"
        self.mapa._agenda()
        self.cancelar.clear()
        self._bloquear(True, "mapa")
        try:
            self._mostrar_overlay("Gerando mapa…", ETAPAS_MAPA)
        except Exception:
            self._log_erro()

        def trabalho():
            try:
                self.fila.put(("prog", 0, 1, "Iniciando leitura do mundo…"))
                vis = mcscan.gerar_visao(pasta, lambda a, b, m: self.fila.put(("prog", a, b, m)), self.cancelar)
                salvar_visao_cache(pasta, vis)
                self.fila.put(("visao", vis))
            except mcscan.Cancelado:
                self.fila.put(("msg", "Cancelado."))
            except Exception as e:  # noqa
                self.fila.put(("erro", str(e)))
        threading.Thread(target=trabalho, daemon=True).start()

    def _visao_pronta(self, vis, do_cache=False):
        self.vis = vis
        self.mapa.definir_visao(vis)
        self.mapa.msg = None
        self.set_progresso(0, "Selecione a área da cidade no mapa: arraste com o botão esquerdo. Botão direito move, "
                              "a roda do mouse dá zoom.")
        self.lbl_pct.config(text="")

    def _ao_selecionar(self, sel, final):
        x1, z1, x2, z2 = sel
        for k, val in (("x1", x1), ("z1", z1), ("x2", x2), ("z2", z2)):
            self.v[k].set(str(val))
        if final and self.vis is not None:
            vis = self.vis
            f = 16 / vis["res"]
            i0, i1 = int((x1 - vis["x0"]) / f), int((x2 - vis["x0"]) / f) + 1
            j0, j1 = int((z1 - vis["z0"]) / f), int((z2 - vis["z0"]) / f) + 1
            sub = vis["topo"][max(j0, 0):j1, max(i0, 0):i1]
            sub = sub[sub > -9000]
            alto = vis["topo_max"][max(j0, 0):j1, max(i0, 0):i1]
            alto = alto[alto > -9000]
            if sub.size:
                chao = int(np.percentile(sub, 10))
                self.v["ymin"].set(str(chao - 3))
                self.v["ymax"].set(str(int(max(sub.max(), alto.max() if alto.size else sub.max())) + 2))
                self.set_progresso(None, "Altura sugerida: do chão − 3 até o ponto mais alto da área. Se a cidade tem "
                                         "porões mais fundos, diminua o Y mín.")

    def _sel_de_campos(self):
        try:
            x1, z1, x2, z2 = [int(self.v[k].get()) for k in ("x1", "z1", "x2", "z2")]
        except ValueError:
            return
        if self.vis is not None:
            self.mapa.sel = (min(x1, x2), min(z1, z2), max(x1, x2), max(z1, z2))
            self.mapa._agenda()

    # ---------- progresso
    def set_progresso(self, frac, texto=None):
        if frac is not None:
            self.barra.definir(frac)
            self.lbl_pct.config(text="%d%%" % int(round(frac * 100)))
        if texto is not None:
            self.lbl_status.config(text=texto)

    def _bloquear(self, sim, tipo=None):
        self.ocupado = sim
        self.btn_scan.habilitar(not sim)
        self.btn_sel.habilitar(not sim)
        self.btn_pasta.config(state="normal")

    def _painel_sobre_fundo(self, left, top, w, h, raio, fill, outline=None, ow=2):
        """Painel arredondado já composto sobre o que está atrás dele (o Tk não tem cantos transparentes)."""
        painel = ui.rr_pil(w, h, raio, fill, outline, ow)
        try:
            from PIL import ImageGrab
            self.update_idletasks()
            base = ImageGrab.grab(bbox=(left, top, left + w, top + h)).convert("RGBA")
        except Exception:
            base = Image.new("RGBA", (w, h), ui.rgb(CREME) + (255,))
        base.alpha_composite(painel)
        return ui.tk_pil(base)

    def _mostrar_overlay(self, titulo, etapas):
        self._fechar_overlay()
        w, h = 520, 150 + 36 * len(etapas) if len(etapas) > 2 else 330
        h = 150 + 34 * len(etapas) + 20
        ov = tk.Canvas(self, width=w, height=h, bg=CREME, highlightthickness=0)
        esq = self.winfo_rootx() + (self.winfo_width() - w) // 2 + 125
        topo = self.winfo_rooty() + (self.winfo_height() - h) // 2
        ov._fundo = self._painel_sobre_fundo(esq, topo, w, h, 16, CREME_CLARO, BORDA, 2)
        ov.create_image(0, 0, anchor="nw", image=ov._fundo)
        ov.create_text(28, 30, anchor="w", text=titulo, fill=TEXTO, font=fonte(14, "bold"))
        barra = BarraProgresso(ov, bg=CREME_CLARO, h=18)
        ov.create_window(28, 58, anchor="nw", window=barra, width=w - 120, height=18)
        pct = ov.create_text(w - 28, 67, anchor="e", text="0%", fill=TEXTO, font=fonte(12, "bold"))
        stat = ov.create_text(28, 100, anchor="w", text="", fill=TEXTO, font=fonte(10))
        etapa_ids = []
        for k, e in enumerate(etapas):
            y = 140 + 34 * k
            etapa_ids.append((ov.create_image(40, y, image=rr_img(22, 22, 11, CREME_CLARO, DESAB_FG if False else BORDA, 2)),
                              ov.create_text(66, y, anchor="w", text=e, fill=MUDO, font=fonte(10)), y))
        Btn(ov, "Cancelar", self._cancelar_op, estilo="secundario", h=38, w=120, bg=CREME_CLARO).place(
            x=w - 148, y=h - 56)
        ov.place(in_=self, relx=0.5, rely=0.5, anchor="center", x=125)
        tk.Misc.tkraise(ov)
        self._overlay = dict(cv=ov, barra=barra, pct=pct, stat=stat, etapas=etapa_ids, lista=etapas, atual=-1)

    def _etapa_overlay(self, idx):
        o = self._overlay
        if not o or idx == o["atual"]:
            return
        ov = o["cv"]
        for k, (img, txt, y) in enumerate(o["etapas"]):
            if k < idx:
                ov.delete(img)
                o["etapas"][k] = (ov.create_image(40, y, image=rr_img(22, 22, 11, OK)), txt, y)
                ov.create_image(40, y, image=tk_icone("check", 14, "#FFFFFF"))
                ov.itemconfigure(txt, fill=TEXTO, font=fonte(10))
            elif k == idx:
                ov.delete(img)
                o["etapas"][k] = (ov.create_image(40, y, image=rr_img(22, 22, 11, CREME_CLARO, VERDE, 3)), txt, y)
                ov.itemconfigure(txt, fill=TEXTO, font=fonte(10, "bold"))
        o["atual"] = idx

    def _fechar_overlay(self):
        if self._overlay:
            self._overlay["cv"].destroy()
            self._overlay = None

    def _cancelar_op(self):
        self.cancelar.set()

    # ---------- escaneamento
    def escanear(self):
        if self.ocupado or not self.dims:
            return
        try:
            x1, z1, x2, z2, ymin, ymax = [int(self.v[k].get()) for k in ("x1", "z1", "x2", "z2", "ymin", "ymax")]
        except ValueError:
            Dialogo.mostrar(self, "aviso", "Atenção", "Selecione a área no mapa (ou preencha X1, Z1, X2, Z2, Y mín. e "
                            "Y máx.) antes de escanear.")
            return
        if x1 == x2 or z1 == z2 or ymin >= ymax:
            Dialogo.mostrar(self, "aviso", "Atenção", "A área escolhida está vazia. Confira os valores de X, Z e Y.")
            return
        ini = self.cfg["pasta_saida"] or os.path.expanduser("~")
        saida = filedialog.asksaveasfilename(parent=self, title="Salvar scan como", defaultextension=".scap", initialfile="cidade.scap",
                                             initialdir=ini if os.path.isdir(ini) else None,
                                             filetypes=[("Scap", "*.scap")])
        if not saida:
            return
        self.cfg["pasta_saida"] = os.path.dirname(saida)
        self._guardar_cfg()
        nome_dim, pasta = [(n, p) for n, p in self.dims if n == self.v_dim.get()][0]
        usar_tex = self.var_tex.get()
        estados = self.var_estados.get()
        jar, mods = self.cfg["jar"].strip(), self.cfg["mods"].strip()
        packs = [p.strip() for p in self.cfg["packs"].split(";") if p.strip()] if self.var_packs.get() else []
        off = set(self.cfg["mods_off"])
        if usar_tex and not jar:
            r = Dialogo.mostrar(self, "aviso", "Atenção", "Sem o jar do Minecraft os blocos do jogo ficam sem textura "
                                "(só os mods terão).\nDeseja continuar mesmo assim?",
                                (("Continuar", "primario"), ("Cancelar", "secundario")))
            if r != 0:
                return
        self.cancelar.clear()
        self._bloquear(True)
        try:
            self._mostrar_overlay("Gerando mapa…", ETAPAS_SCAN)
            self._etapa_overlay(0)
        except Exception:
            self._log_erro()

        def trabalho():
            try:
                rec = None
                if usar_tex:
                    self.fila.put(("prog", 0, 1, "Lendo os jars do Minecraft e dos mods…"))
                    rec = mcscan.Recursos(jar or None, mods or None, packs, [], excluir_mods=off)
                    rec.animar = bool(self.cfg["animadas"])
                    if not rec.tem_fontes:
                        raise ValueError("Não encontrei nenhuma textura. Confira o jar do Minecraft e a pasta de mods em "
                                         "Configurações, ou desmarque \"Usar texturas\".")
                r = mcscan.escanear(pasta, x1, z1, x2, z2, ymin, ymax, saida, estados, nome_dim,
                                    lambda a, b, m: self.fila.put(("prog", a, b, m)), self.cancelar, rec)
                self.fila.put(("fim", r))
            except mcscan.Cancelado:
                self.fila.put(("msg", "Cancelado."))
            except Exception as e:  # noqa
                self.fila.put(("erro", str(e)))
        threading.Thread(target=trabalho, daemon=True).start()

    def _prog(self, a, b, m):
        low = m.lower()
        idx, frac = None, None
        if self._overlay and self._overlay["lista"] is ETAPAS_SCAN:
            if "jars" in low:
                idx, frac = 0, 0.03
            elif "chunks" in low or "escaneando" in low:
                idx, frac = 1, 0.05 + 0.65 * (a / max(b, 1))
            elif "montando" in low or "modelos" in low:
                idx, frac = 2, 0.78
            elif "comprimindo" in low or "salvando" in low:
                idx, frac = 3, 0.93
            else:
                idx, frac = max(self._overlay["atual"], 0), None
        elif self._overlay:
            if "lendo o mapa" in low:
                idx, frac = 1, 0.05 + 0.9 * (a / max(b, 1))
            else:
                idx, frac = 0, 0.02
        if idx is not None:
            self._etapa_overlay(idx)
        if frac is None:
            frac = self.barra.frac
        self.set_progresso(frac, m.strip())
        if self._overlay:
            o = self._overlay
            o["barra"].definir(frac)
            o["cv"].itemconfigure(o["pct"], text="%d%%" % int(frac * 100))
            o["cv"].itemconfigure(o["stat"], text=m.strip())

    def _ler_fila(self):
        try:
            ultimo_prog = None
            outros = []
            try:
                while True:
                    m = self.fila.get_nowait()
                    if m[0] == "prog":
                        ultimo_prog = m          # só a última mensagem de progresso interessa
                    else:
                        outros.append(m)
            except queue.Empty:
                pass
            if ultimo_prog is not None:
                try:
                    self._prog(ultimo_prog[1], ultimo_prog[2], ultimo_prog[3])
                except Exception:
                    self._log_erro()
            for m in outros:
                try:
                    self._tratar_msg(m)
                except Exception:
                    self._log_erro()
        finally:
            self.after(120, self._ler_fila)

    def _tratar_msg(self, m):
        tipo = m[0]
        if tipo == "icone":
            self.ico_mods[m[1]] = ui.tk_pil(m[2])
            for lin in getattr(self, "linhas_mods", []):
                if lin.winfo_exists() and lin.nome == m[1]:
                    lin.pintar()
        elif tipo == "visao":
            self._fechar_overlay()
            self._bloquear(False)
            self._visao_pronta(m[1])
            self.toast("Mapa carregado. Selecione a área da cidade.")
        elif tipo == "fim":
            self._fechar_overlay()
            self._bloquear(False)
            self.set_progresso(1.0, "Pronto: %s (%.2f MB, %d blocos, %d tipos)" % (
                os.path.basename(m[1]["arquivo"]), m[1]["bytes"] / 1048576, m[1]["blocos"], m[1]["tipos"]))
            self._fim_scan(m[1])
        elif tipo == "msg":
            self._fechar_overlay()
            self._bloquear(False)
            self.set_progresso(0, m[1])
            if self.vis is None and self.dims:
                self.mapa.msg = "Mapa não carregado. Escolha a dimensão novamente."
                self.mapa._agenda()
        elif tipo == "erro":
            self._fechar_overlay()
            self._bloquear(False)
            self.set_progresso(0, "Erro: " + m[1])
            Dialogo.mostrar(self, "erro", "Erro", m[1])

    def _log_erro(self):
        """Registra o erro num arquivo e avisa sem travar o programa."""
        import traceback
        txt = traceback.format_exc()
        try:
            with open(os.path.join(pasta_config(), "erro.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + txt + "\n")
        except Exception:
            pass
        try:
            self.toast("Ocorreu um erro (detalhes em erro.log).", 6000)
        except Exception:
            pass

    def report_callback_exception(self, exc, val, tb):
        import traceback
        txt = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(pasta_config(), "erro.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + txt + "\n")
        except Exception:
            pass
        try:
            self._fechar_overlay()
            self._bloquear(False)
            self.toast("Ocorreu um erro: %s" % val, 7000)
        except Exception:
            pass

    def _fim_scan(self, r):
        self._ultimo_scan = r["arquivo"]
        mb = r["bytes"] / 1048576
        detalhes = ["Arquivo: " + r["arquivo"],
                    "Tamanho: %.2f MB (texturas: %.2f MB)" % (mb, r["bytes_atlas"] / 1048576),
                    "Blocos guardados: %d | Tipos de bloco: %d | Texturas: %d" % (r["blocos"], r["tipos"], r["texturas"])]
        if r["texturas_faltando"]:
            detalhes.append("Texturas não encontradas: %d (ex.: %s)" % (len(r["texturas_faltando"]),
                                                                      ", ".join(r["texturas_faltando"][:4])))
        if r["sem_modelo"]:
            detalhes.append("Blocos sem modelo próprio (viraram cubo): %d tipo(s) (ex.: %s)" % (
                len(r["sem_modelo"]), ", ".join(n for n, _, _ in r["sem_modelo"][:4])))
        if r["relatorio"]:
            detalhes.append("Relatório completo: " + r["relatorio"])
        if r["avisos"]:
            detalhes.append("Avisos: " + "; ".join(r["avisos"][:3]))
        self.toast("Mapa gerado com sucesso!")
        botoes = [("Ver em 3D", "secundario"), ("OK", "primario")]
        i = Dialogo.mostrar(self, "ok", "Concluído", "O mapa foi gerado com sucesso!", botoes, largura=560,
                            detalhes="\n".join(detalhes))
        if i == 0:
            self.abrir_visualizador()

    def abrir_visualizador(self, scan=None):
        scan = scan or self._ultimo_scan
        if not scan or not os.path.isfile(scan):
            return self.abrir_scan_existente()
        self.abrir_3d(scan)

    def abrir_scan_existente(self):
        ini = self.cfg["pasta_saida"] or os.path.expanduser("~")
        c = filedialog.askopenfilename(parent=self, title="Abrir scan", initialdir=ini if os.path.isdir(ini) else None,
                                       filetypes=[("Scap", "*.scap"), ("Scan antigo", "*.mcscan"), ("Todos", "*.*")])
        if c:
            self.abrir_3d(c)

    def abrir_no_browser(self):
        import mapscan_viewer as mv
        scan = self._scan3d or self._ultimo_scan
        if not scan or not os.path.isfile(scan):
            ini = self.cfg["pasta_saida"] or os.path.expanduser("~")
            scan = filedialog.askopenfilename(parent=self, title="Abrir scan no browser",
                                              initialdir=ini if os.path.isdir(ini) else None,
                                              filetypes=[("Scap", "*.scap"), ("Scan antigo", "*.mcscan"), ("Todos", "*.*")])
            if not scan:
                return
        try:
            mv.abrir_no_navegador(scan)
            self.toast("Abri o scan no navegador.")
        except Exception as e:  # noqa
            Dialogo.mostrar(self, "erro", "Erro", "Não consegui abrir no navegador.", detalhes=str(e))

    # ---------- página: 3D dentro do app
    def _pag_3d(self):
        pg = tk.Frame(self.area, bg=CREME)
        pg.columnconfigure(0, weight=1)
        pg.rowconfigure(1, weight=1)
        cab = self._cabecalho(pg, "cubo", "Visualizador 3D", "Veja o seu mapa em 3D, sem sair do Scap")
        cab.grid(row=0, column=0, sticky="ew")
        Btn(cab.inner, "Abrir scan...", self.abrir_scan_existente, estilo="primario", icone="abrir", h=46, w=200,
            bg=CREME_CLARO).pack(side="right")
        Btn(cab.inner, "Abrir scan no browser", self.abrir_no_browser, estilo="secundario", icone="abrir", h=46, w=250,
            bg=CREME_CLARO).pack(side="right", padx=(0, 10))
        self.v3d = tk.Frame(pg, bg="#0B1F16")
        self.v3d.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.lbl3d = tk.Label(self.v3d, text="Nenhum scan aberto.\nGere um scan na aba Mapa ou abra um arquivo .scap.",
                              bg="#0B1F16", fg="#CFE5D4", font=fonte(12), justify="center")
        self.lbl3d.place(relx=0.5, rely=0.5, anchor="center")
        self.v3d.bind("<Configure>", self._ajustar_3d)
        return pg

    def abrir_3d(self, scan):
        self._ultimo_scan = scan
        self._scan3d = None
        if self.pagina == "3d":
            self._carregar_3d(scan)
        else:
            self.mostrar("3d")

    def _parar_3d(self):
        p = self._proc3d
        self._proc3d, self._hwnd3d = None, 0
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    def _garantir_webview(self, depois):
        """No Windows o 3D embutido precisa do pywebview. Se faltar (rodando pelo Python), instala sozinho."""
        import importlib.util
        if getattr(sys, "frozen", False) or importlib.util.find_spec("webview") is not None:
            depois()
            return
        self.lbl3d.config(text="Instalando o componente do visualizador 3D (só na primeira vez)…")
        self.lbl3d.place(relx=0.5, rely=0.5, anchor="center")

        def instalar():
            import subprocess
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
            try:
                r = subprocess.run([sys.executable, "-m", "pip", "install", "pywebview"], capture_output=True, text=True, **kw)
                ok, det = r.returncode == 0, (r.stderr or r.stdout)[-600:]
            except Exception as e:  # noqa
                ok, det = False, str(e)
            self.after(0, lambda: self._pos_instalar_webview(ok, det, depois))
        threading.Thread(target=instalar, daemon=True).start()

    def _pos_instalar_webview(self, ok, det, depois):
        import importlib
        importlib.invalidate_caches()
        if ok:
            depois()
            return
        self.lbl3d.config(text="Não consegui instalar o componente do visualizador 3D.")
        Dialogo.mostrar(self, "erro", "Visualizador 3D",
                        "Para ver o 3D dentro do Scap é preciso o componente pywebview, e a instalação automática falhou. "
                        "Rode no terminal: pip install pywebview pythonnet", detalhes=det)

    def _carregar_3d(self, scan):
        self._garantir_webview(lambda: self._carregar_3d_ok(scan))

    def _carregar_3d_ok(self, scan):
        import mapscan_viewer as mv
        self._parar_3d()
        self._scan3d = scan
        self.lbl3d.config(text="Carregando %s…" % os.path.basename(scan))
        self.lbl3d.place(relx=0.5, rely=0.5, anchor="center")
        try:
            if os.name != "nt":
                self._proc3d = mv.abrir(scan)
                self.lbl3d.config(text="Fora do Windows o 3D abre em uma janela separada.")
                return
            self._titulo3d = "Scap3D-%d-%d" % (os.getpid(), int(time.time() * 1000) % 10 ** 8)
            self._proc3d = mv.abrir(scan, self._titulo3d, True)
            self._tent3d = 0
            self.after(500, lambda: self._prender_3d(scan))
        except Exception as e:  # noqa
            self.lbl3d.config(text="Não consegui abrir o visualizador.")
            Dialogo.mostrar(self, "erro", "Erro", "Não consegui abrir o visualizador 3D.", detalhes=str(e))

    def _prender_3d(self, scan):
        import mapscan_viewer as mv
        if self._scan3d != scan or self._proc3d is None:
            return
        rc = self._proc3d.poll()
        if rc is not None:
            if rc in (3, 4):
                self.lbl3d.config(text="O componente do visualizador 3D (pywebview) não iniciou.")
                Dialogo.mostrar(self, "erro", "Visualizador 3D",
                                "Não consegui iniciar o visualizador embutido. No Windows ele usa o WebView2 (já vem no Windows 11; "
                                "no Windows 10 instale o \"WebView2 Runtime\" da Microsoft) e o pacote pywebview com pythonnet.")
            else:
                self.lbl3d.config(text="O visualizador fechou. Tente abrir o scan de novo.")
            return
        hwnd = mv.achar_janela(self._titulo3d)
        if hwnd:
            try:
                self.update_idletasks()
                dono = ctypes_user32().GetParent(self.winfo_id()) or self.winfo_id()
                mv.prender(hwnd, dono)
                self._hwnd3d = hwnd
                self._ult_ret3d = None
                self.lbl3d.place_forget()
                self._vigiar_3d()
                return
            except Exception:
                self._log_erro()
        self._tent3d += 1
        if self._tent3d > 70:
            # não deu para encaixar: abre em janela própria
            self._parar_3d()
            self._proc3d = mv.abrir(scan)
            self.lbl3d.config(text="O 3D abriu em uma janela separada.")
            self.toast("Não consegui encaixar o 3D; abri em janela própria.")
            return
        self.after(400, lambda: self._prender_3d(scan))

    def _vigiar_3d(self):
        """A janela do visualizador acompanha o quadro da aba 3D (posição, tamanho e visibilidade)."""
        if not self._hwnd3d or self._proc3d is None:
            return
        try:
            import mapscan_viewer as mv
            vis = (self.pagina == "3d" and self.state() != "iconic" and self.v3d.winfo_viewable()
                   and self.v3d.winfo_width() > 20)
            ret = mv.retangulo(self.v3d.winfo_id()) if vis else None
            chave = (ret, vis)
            if chave != self._ult_ret3d:
                self._ult_ret3d = chave
                if vis:
                    mv.ajustar(self._hwnd3d, ret[0], ret[1], ret[2], ret[3], True)
                else:
                    mv.ajustar(self._hwnd3d, 0, 0, 1, 1, False)
        except Exception:
            pass
        self.after(30, self._vigiar_3d)

    def _ajustar_3d(self, e):
        pass

    # ---------- avisos discretos
    def toast(self, texto, ms=4500):
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
        w, h = 340, 76
        c = tk.Canvas(self, width=w, height=h, bg=CREME, highlightthickness=0)
        esq = self.winfo_rootx() + self.winfo_width() - 30 - w
        topo = self.winfo_rooty() + self.winfo_height() - 70 - h
        c._fundo = self._painel_sobre_fundo(esq, topo, w, h, 14, "#064930")
        c.create_image(0, 0, anchor="nw", image=c._fundo)
        self._ic_toast = ui.tk_pil(imagem("emblema.png", 46))
        c.create_image(18, h / 2, anchor="w", image=self._ic_toast)
        c.create_text(78, 26, anchor="w", text=NOME, fill="#FFF5DB", font=fonte(12, "bold"))
        c.create_text(78, 50, anchor="w", text=texto, fill="#FFF5DB", font=fonte(10))
        x = IconBtn(c, "x", lambda: c.destroy(), tam=24, px=12, bg="#064930", hov="#0B5B3E", cor="#FFF5DB",
                    hov_icone="#FFFFFF", raio=6)
        c.create_window(w - 12, 12, anchor="ne", window=x)
        c.place(relx=1, rely=1, anchor="se", x=-30, y=-70)
        tk.Misc.tkraise(c)
        self._toast = c
        self.after(ms, lambda: c.destroy() if c.winfo_exists() else None)

    # ---------- página: configurações
    def _pag_config(self):
        pg = tk.Frame(self.area, bg=CREME)
        pg.columnconfigure(0, weight=1)
        self._cabecalho(pg, "engrenagem", "Configurações", "Ajuste os caminhos e as opções do Scap").grid(
            row=0, column=0, sticky="ew")
        self.c_tex = tk.BooleanVar(value=True)
        self.c_estados = tk.BooleanVar(value=True)
        self.c_anim = tk.BooleanVar(value=True)
        self.c_jar, self.c_mods, self.c_packs = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.c_ymin, self.c_ymax = tk.StringVar(), tk.StringVar()

        p = Painel(pg, bg=CREME)
        p.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self._titulo_secao(p.inner, "Texturas").grid(row=0, column=0, sticky="w")
        Check(p.inner, "Usar texturas do jogo e dos mods", self.c_tex, bg=CREME_CLARO, tam=11).grid(
            row=1, column=0, sticky="w", pady=(8, 0))

        p = Painel(pg, bg=CREME)
        p.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        i = p.inner
        i.columnconfigure(1, weight=1)
        self._titulo_secao(i, "Arquivos e pastas").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.campos_cfg = {}
        for r, (rot, var, cmd, k) in enumerate((("Jar do Minecraft:", self.c_jar, self._pick_jar, "jar"),
                                                ("Pasta de mods:", self.c_mods, self._pick_mods, "mods"),
                                                ("Resource packs (opcional):", self.c_packs, self._pick_packs, "packs"))):
            tk.Label(i, text=rot, bg=CREME_CLARO, fg=TEXTO, font=fonte(10)).grid(row=1 + r, column=0, sticky="w",
                                                                              padx=(0, 14), pady=5)
            c = Campo(i, var, h=38)
            c.grid(row=1 + r, column=1, sticky="ew", pady=5)
            self.campos_cfg[k] = c
            c.entry.bind("<FocusOut>", lambda e, k=k: self._validar_cfg(k))
            Btn(i, "Procurar...", cmd, estilo="primario", h=38, w=130, bg=CREME_CLARO).grid(row=1 + r, column=2,
                                                                                         padx=(10, 0), pady=5)
        tk.Label(i, text="Vários resource packs: separe com ponto e vírgula (;). O último da lista vence.",
                 bg=CREME_CLARO, fg=MUDO, font=fonte(9)).grid(row=4, column=1, sticky="w")

        p = Painel(pg, bg=CREME)
        p.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        i = p.inner
        self._titulo_secao(i, "Intervalo vertical (Y)").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        tk.Label(i, text="Y mínimo:", bg=CREME_CLARO, fg=TEXTO, font=fonte(10)).grid(row=1, column=0, sticky="w")
        Campo(i, self.c_ymin, h=36, largura=110, justificar="center").grid(row=1, column=1, padx=(8, 40))
        tk.Label(i, text="Y máximo:", bg=CREME_CLARO, fg=TEXTO, font=fonte(10)).grid(row=1, column=2, sticky="w")
        Campo(i, self.c_ymax, h=36, largura=110, justificar="center").grid(row=1, column=3, padx=(8, 0))

        p = Painel(pg, bg=CREME)
        p.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._titulo_secao(p.inner, "Dados dos blocos").grid(row=0, column=0, sticky="w")
        Check(p.inner, "Salvar estados dos blocos (escadas, lajes, portas)", self.c_estados, bg=CREME_CLARO,
              tam=11).grid(row=1, column=0, sticky="w", pady=(8, 0))
        Check(p.inner, "Texturas animadas (água, lava, fogo...) — aumenta o arquivo em poucas dezenas de KB", self.c_anim,
              bg=CREME_CLARO, tam=11).grid(row=2, column=0, sticky="w", pady=(6, 0))

        rod = tk.Frame(pg, bg=CREME)
        rod.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        Btn(rod, "Salvar configurações", self._salvar_cfg_btn, estilo="perigo", h=46, w=210, bg=CREME).pack(side="right")
        Btn(rod, "Cancelar", self._cfg_para_campos, estilo="secundario", h=46, w=130, bg=CREME).pack(side="right", padx=12)
        return pg

    def _validar_cfg(self, k):
        v = self.campos_cfg[k]
        txt = {"jar": self.c_jar, "mods": self.c_mods, "packs": self.c_packs}[k].get().strip()
        if not txt:
            v.estado(None)
            return
        if k == "jar":
            ok = os.path.isfile(txt)
        elif k == "mods":
            ok = os.path.isdir(txt)
        else:
            ok = all(os.path.exists(p.strip()) for p in txt.split(";") if p.strip())
        v.estado("ok" if ok else "erro")

    def _cfg_para_campos(self):
        self.c_tex.set(bool(self.cfg["texturas"]))
        self.c_estados.set(bool(self.cfg["estados"]))
        self.c_anim.set(bool(self.cfg["animadas"]))
        self.c_jar.set(self.cfg["jar"])
        self.c_mods.set(self.cfg["mods"])
        self.c_packs.set(self.cfg["packs"])
        self.c_ymin.set(str(self.cfg["ymin"]))
        self.c_ymax.set(str(self.cfg["ymax"]))
        self.v_modsdir.set(self.cfg["mods"]) if hasattr(self, "v_modsdir") else None
        self.v_packs_m.set(self.cfg["packs"]) if hasattr(self, "v_packs_m") else None
        for k in self.campos_cfg:
            self._validar_cfg(k)

    def _salvar_cfg_btn(self):
        try:
            ymin, ymax = int(self.c_ymin.get()), int(self.c_ymax.get())
            if ymin >= ymax:
                raise ValueError
        except ValueError:
            Dialogo.mostrar(self, "erro", "Erro", "O intervalo vertical é inválido. O Y mínimo deve ser menor que o Y máximo.")
            return
        self.cfg["texturas"] = bool(self.c_tex.get())
        self.cfg["estados"] = bool(self.c_estados.get())
        self.cfg["animadas"] = bool(self.c_anim.get())
        self.cfg["jar"] = self.c_jar.get().strip()
        self.cfg["mods"] = self.c_mods.get().strip()
        self.cfg["packs"] = self.c_packs.get().strip()
        self.cfg["ymin"], self.cfg["ymax"] = ymin, ymax
        self.cfg.salvar()
        self._aplicar_cfg()
        self.toast("Configurações salvas.")

    def _aplicar_cfg(self):
        self.var_tex.set(bool(self.cfg["texturas"]))
        self.var_estados.set(bool(self.cfg["estados"]))
        self.var_packs.set(bool(self.cfg["packs"]))
        self._cfg_para_campos()

    def _guardar_cfg(self):
        try:
            self.cfg["texturas"] = bool(self.var_tex.get())
            self.cfg["estados"] = bool(self.var_estados.get())
            self.cfg.salvar()
        except Exception:
            pass

    def _pick_jar(self):
        c = filedialog.askopenfilename(parent=self, initialdir=sub_mc("versions"),
                                       title="Jar do Minecraft (ex.: versions/1.20.1/1.20.1.jar)",
                                       filetypes=[("Jar", "*.jar"), ("Todos", "*.*")])
        if c:
            self.c_jar.set(c)
            self._validar_cfg("jar")

    def _pick_mods(self):
        c = filedialog.askdirectory(parent=self, initialdir=sub_mc("mods", self.cfg["mods"]),
                                    title="Pasta de mods (a que contém os .jar dos mods)")
        if c:
            self.c_mods.set(c)
            self._validar_cfg("mods")

    def _pick_packs(self):
        cs = filedialog.askopenfilenames(parent=self, initialdir=sub_mc("resourcepacks", self.cfg["ultima_pasta_packs"]),
                                         title="Resource packs (.zip)", filetypes=[("Zip", "*.zip"), ("Todos", "*.*")])
        if cs:
            self.cfg["ultima_pasta_packs"] = os.path.dirname(cs[0])
        if cs:
            atual = [p for p in self.c_packs.get().split(";") if p.strip()]
            self.c_packs.set(";".join(atual + [c for c in cs if c not in atual]))
            self._validar_cfg("packs")

    # ---------- página: mods
    def _pag_mods(self):
        pg = tk.Frame(self.area, bg=CREME)
        pg.columnconfigure(0, weight=1)
        pg.rowconfigure(2, weight=1)
        self._cabecalho(pg, "mods", "Mods", "Gerencie os mods utilizados no mapa").grid(row=0, column=0, sticky="ew")
        self.v_modsdir, self.v_packs_m = tk.StringVar(), tk.StringVar()
        p = Painel(pg, bg=CREME)
        p.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        i = p.inner
        i.columnconfigure(0, weight=1)
        self._titulo_secao(i, "Pasta de mods").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        c = Campo(i, self.v_modsdir, h=38)
        c.grid(row=1, column=0, sticky="ew")
        self.campo_modsdir = c
        Btn(i, "Procurar...", self._pick_mods_pg, estilo="primario", h=38, w=130, bg=CREME_CLARO).grid(
            row=1, column=1, padx=(10, 0))

        p = Painel(pg, bg=CREME, expandir=True)
        p.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        i = p.inner
        i.columnconfigure(0, weight=1)
        i.rowconfigure(1, weight=1)
        topo = tk.Frame(i, bg=CREME_CLARO)
        topo.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._titulo_secao(topo, "Mods detectados").pack(side="left")
        self.lbl_nmods = tk.Label(topo, text="", bg=CREME_CLARO, fg=MUDO, font=fonte(10))
        self.lbl_nmods.pack(side="left", padx=12)
        self.lista_mods = ListaRolavel(i)
        self.lista_mods.grid(row=1, column=0, sticky="nsew", pady=(8, 0), padx=(0, 10))
        bt = tk.Frame(i, bg=CREME_CLARO)
        bt.grid(row=1, column=1, sticky="n", pady=(8, 0))
        for rot, cmd in (("Selecionar todos", lambda: self._marcar_todos(True)),
                         ("Desmarcar todos", lambda: self._marcar_todos(False)),
                         ("Atualizar lista", self._listar_mods)):
            Btn(bt, rot, cmd, estilo="secundario", h=44, w=170, bg=CREME_CLARO).pack(pady=(0, 10))

        p = Painel(pg, bg=CREME)
        p.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        i = p.inner
        i.columnconfigure(0, weight=1)
        self._titulo_secao(i, "Resource packs (opcional)").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        c = Campo(i, self.v_packs_m, h=38)
        c.grid(row=1, column=0, sticky="ew")
        Btn(i, "Procurar...", self._pick_packs_pg, estilo="primario", h=38, w=130, bg=CREME_CLARO).grid(
            row=1, column=1, padx=(10, 0))
        self.v_modsdir.trace_add("write", lambda *a: self._mods_dir_mudou())
        self.v_packs_m.trace_add("write", lambda *a: self._packs_mudou())
        self.linhas_mods = []
        return pg

    def _mods_dir_mudou(self):
        v = self.v_modsdir.get().strip()
        self.campo_modsdir.estado(("ok" if os.path.isdir(v) else "erro") if v else None)

    def _packs_mudou(self):
        self.cfg["packs"] = self.v_packs_m.get().strip()
        self.c_packs.set(self.cfg["packs"])
        self.cfg.salvar()
        self.var_packs.set(bool(self.cfg["packs"]))

    def _pick_mods_pg(self):
        c = filedialog.askdirectory(parent=self, initialdir=sub_mc("mods", self.cfg["mods"]),
                                    title="Pasta de mods (a que contém os .jar dos mods)")
        if c:
            self.v_modsdir.set(c)
            self.cfg["mods"] = c
            self.cfg.salvar()
            self._listar_mods()

    def _pick_packs_pg(self):
        cs = filedialog.askopenfilenames(parent=self, initialdir=sub_mc("resourcepacks", self.cfg["ultima_pasta_packs"]),
                                         title="Resource packs (.zip)", filetypes=[("Zip", "*.zip"), ("Todos", "*.*")])
        if cs:
            self.cfg["ultima_pasta_packs"] = os.path.dirname(cs[0])
        if cs:
            atual = [p for p in self.v_packs_m.get().split(";") if p.strip()]
            self.v_packs_m.set(";".join(atual + [c for c in cs if c not in atual]))

    def _listar_mods(self, forcar=True):
        pasta = (self.v_modsdir.get() or self.cfg["mods"] or "").strip()
        if not forcar and self.linhas_mods and pasta == getattr(self, "_mods_listados", None):
            return
        self._mods_listados = pasta
        self.v_modsdir.set(pasta)
        for w in self.lista_mods.inner.winfo_children():
            w.destroy()
        self.linhas_mods = []
        if not os.path.isdir(pasta):
            self.lbl_nmods.config(text="(pasta não encontrada)")
            return
        arqs = sorted((f for f in os.listdir(pasta) if f.lower().endswith(".jar")), key=str.lower)
        off = set(self.cfg["mods_off"])
        self._vars_mods = {}
        for f in arqs:
            var = tk.BooleanVar(value=f not in off)
            self._vars_mods[f] = var
            self.linhas_mods.append(self._linha_mod(f, var))
        self._contar_mods()
        threading.Thread(target=self._carregar_icones, args=(pasta, arqs), daemon=True).start()

    def _linha_mod(self, nome, var):
        lin = tk.Canvas(self.lista_mods.inner, height=42, bg=CREME_CLARO, highlightthickness=0, cursor="hand2")
        lin.pack(fill="x")
        lin.nome, lin.var = nome, var

        def pintar(*a):
            lin.delete("all")
            if var.get():
                lin.create_image(8, 21, anchor="w", image=rr_img(24, 24, 6, VERDE))
                lin.create_image(20, 21, image=tk_icone("check", 16, "#FFFFFF"))
            else:
                lin.create_image(8, 21, anchor="w", image=rr_img(24, 24, 6, CREME_CLARO, VERDE_MED_(), 2))
            ic = self.ico_mods.get(nome)
            lin.create_image(54, 21, anchor="w", image=ic or self._ico_padrao())
            lin.create_text(98, 21, anchor="w", text=nome, fill=TEXTO, font=fonte(11))
        lin.pintar = pintar
        lin.bind("<ButtonRelease-1>", lambda e: (var.set(not var.get()), self._contar_mods()))
        var.trace_add("write", pintar)
        pintar()
        return lin

    def _ico_padrao(self):
        if not hasattr(self, "_ico_def"):
            self._ico_def = ui.tk_pil(cubo_grama(28))
        return self._ico_def

    def _carregar_icones(self, pasta, arqs):
        for f in arqs:
            if f in self.ico_mods:
                continue
            try:
                with zipfile.ZipFile(os.path.join(pasta, f)) as z:
                    nomes = z.namelist()
                    alvo = None
                    try:
                        toml = z.read("META-INF/mods.toml").decode("utf-8", "ignore")
                        import re
                        m = re.search(r'logoFile\s*=\s*"([^"]+)"', toml)
                        if m and m.group(1) in nomes:
                            alvo = m.group(1)
                    except KeyError:
                        pass
                    if alvo is None and "pack.png" in nomes:
                        alvo = "pack.png"
                    if alvo is None:
                        continue
                    im = Image.open(io.BytesIO(z.read(alvo))).convert("RGBA").resize((28, 28), Image.LANCZOS)
                self.fila.put(("icone", f, im))
            except Exception:
                continue

    def _marcar_todos(self, sim):
        for v in self._vars_mods.values():
            v.set(sim)
        self._contar_mods()

    def _contar_mods(self):
        total = len(self._vars_mods)
        marc = sum(1 for v in self._vars_mods.values() if v.get())
        self.lbl_nmods.config(text="%d de %d selecionados" % (marc, total))
        self.cfg["mods_off"] = [f for f, v in self._vars_mods.items() if not v.get()]
        self.cfg.salvar()

    # ---------- página: sobre
    def _pag_sobre(self):
        pg = tk.Frame(self.area, bg=CREME)
        pg.columnconfigure(0, weight=1)
        pg.columnconfigure(1, weight=1)
        self._cabecalho(pg, "info", "Sobre", "Informações sobre o Scap.").grid(row=0, column=0, columnspan=2,
                                                                                  sticky="ew")
        self._img_sobre = ui.tk_pil(ui.marca_img(300, VERDE))
        self._img_masc = ui.tk_pil(imagem("emblema.png", 120))
        topo = tk.Frame(pg, bg=CREME)
        topo.grid(row=1, column=0, columnspan=2, pady=(18, 8))
        lin = tk.Frame(topo, bg=CREME)
        lin.pack()
        tk.Label(lin, image=self._img_masc, bg=CREME).pack(side="left", padx=(0, 22))
        tk.Label(lin, image=self._img_sobre, bg=CREME).pack(side="left")
        tk.Label(topo, text="Um scanner de mapas para mundos do Minecraft.", bg=CREME, fg=MUDO, font=fonte(12)).pack(pady=(6, 0))
        tk.Frame(topo, bg=BORDA, height=1, width=420).pack(pady=(14, 0))

        def cartao(r, c, icone, titulo):
            p = Painel(pg, bg=CREME)
            p.grid(row=r, column=c, sticky="nsew", padx=(0 if c == 0 else 8, 8 if c == 0 else 0), pady=8)
            i = p.inner
            i.columnconfigure(1, weight=1)
            cv = tk.Canvas(i, width=44, height=44, bg=CREME_CLARO, highlightthickness=0)
            cv.grid(row=0, column=0, sticky="w")
            cv.create_image(22, 22, image=rr_img(42, 42, 10, VERDE))
            cv.create_image(22, 22, image=tk_icone(icone, 26, "#FFF5DB"))
            tk.Label(i, text=titulo, bg=CREME_CLARO, fg=TEXTO, font=fonte(14, "bold")).grid(row=0, column=1, sticky="w", padx=10)
            return i
        i = cartao(2, 0, "cubo", "Versão")
        Campo(i, tk.StringVar(value=VERSAO), h=40, somente_leitura=True).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        i = cartao(2, 1, "doc", "Descrição")
        tk.Label(i, text="O Scap permite gerar uma visão completa do seu mundo do Minecraft, combinando os blocos, "
                         "biomas e estruturas em um mapa detalhado, com suporte a mods e resource packs.",
                 bg=CREME_CLARO, fg=TEXTO, font=fonte(10), wraplength=420, justify="left").grid(row=1, column=0, columnspan=2,
                                                                                                sticky="w", pady=(10, 0))
        i = cartao(3, 0, "pessoa", "Autor")
        tk.Label(i, text="Essie N Pierot", bg=CREME_CLARO, fg=TEXTO, font=fonte(11, "bold")).grid(row=1, column=0, columnspan=2,
                                                                                               sticky="w", pady=(10, 0))
        i = cartao(3, 1, "pasta", "Tecnologias")
        tk.Label(i, text="Minecraft (Java Edition)\nMods e Resource Packs (opcional)", bg=CREME_CLARO, fg=TEXTO,
                 font=fonte(10), justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        return pg


def VERDE_MED_():
    return ui.VERDE_MED


VERM_HOV = ui.VERM_HOV


# ---------------------------------------------------------------- tela de abertura
def ctypes_user32():
    import ctypes
    return ctypes.windll.user32


class Splash(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        w = 760
        self.masc = ui.tk_pil(imagem("emblema.png", 170))
        self.logo = ui.tk_pil(ui.marca_img(300, "#FFF5DB"))
        mh, lh = self.masc.height(), self.logo.height()
        y_m = 40 + mh // 2
        y_l = 40 + mh + 22 + lh // 2
        y_b = 40 + mh + 22 + lh + 40
        h = y_b + 60
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, (sh - h) // 2))
        self.configure(bg="#0B4B33")
        self.cv = tk.Canvas(self, width=w, height=h, bg="#0B4B33", highlightthickness=0)
        self.cv.pack()
        self.cv.create_image(w / 2, y_m, image=self.masc)
        self.cv.create_image(w / 2, y_l, image=self.logo)
        self.barra = BarraProgresso(self.cv, bg="#0B4B33", h=16)
        self.cv.create_window(w / 2, y_b, window=self.barra, width=340, height=16)
        self.txt = self.cv.create_text(w / 2, y_b + 34, text="", fill="#CFE5D4", font=fonte(10))
        self.update()

    def passo(self, f, texto=""):
        self.barra.definir(f)
        self.cv.itemconfigure(self.txt, text=texto)
        self.update()

    def fechar(self):
        self.barra.definir(1.0)
        self.update()
        self.destroy()


def iniciar():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    iniciar()
