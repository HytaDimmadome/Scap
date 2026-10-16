# -*- coding: utf-8 -*-
"""Scap: tema e widgets (tkinter + Pillow). Tudo é desenhado em Canvas com cantos arredondados suaves."""
import os
import sys
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

# ---------------------------------------------------------------- tema
VERDE = "#0B4B33"
VERDE_HOV = "#0F5C3E"
VERDE_ESC = "#073A27"
VERDE_MED = "#2F6B4A"
CREME = "#F8EBD3"
CREME_CLARO = "#FCF4E3"
CREME_ESC = "#F1E1C2"
BORDA = "#E3D0AE"
VERMELHO = "#E01A13"
VERM_HOV = "#EF3B33"
TEXTO = "#0B4B33"
MUDO = "#5A5E4E"
OK = "#2E9B4E"
ERRO = "#D8231A"
AVISO = "#F2AD43"
DESAB_BG = "#E5DCC5"
DESAB_FG = "#9AA591"


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def asset(nome):
    return os.path.join(base_dir(), "gui_assets", nome)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


FONTE = "Inter"


def _carregar_inter():
    """Registra a fonte Inter embutida (só para este programa)."""
    pasta = os.path.join(base_dir(), "gui_assets", "fonts")
    arqs = [os.path.join(pasta, n) for n in ("Inter-Regular.ttf", "Inter-Bold.ttf")]  # SemiBold/ExtraBold só são lidas direto pelo PIL
    if os.name == "nt":
        try:
            import ctypes
            for a in arqs:
                ctypes.windll.gdi32.AddFontResourceExW(a, 0x10, 0)
        except Exception:
            pass
    else:
        try:
            dest = os.path.expanduser("~/.fonts")
            os.makedirs(dest, exist_ok=True)
            import shutil
            novo = False
            for a in arqs:
                d = os.path.join(dest, os.path.basename(a))
                if not os.path.exists(d):
                    shutil.copy(a, d)
                    novo = True
            if novo:
                import subprocess
                subprocess.run(["fc-cache", "-f", dest], timeout=30)
        except Exception:
            pass


def escolher_fonte(root=None):
    global FONTE
    return FONTE


def fonte(tam=10, peso="normal"):
    return (FONTE, tam, peso)


# ---------------------------------------------------------------- imagens
_cache = {}


_cantos_cache = {}


def _canto(r):
    """Máscara (L) do canto superior esquerdo arredondado: 255 dentro da curva."""
    m = _cantos_cache.get(r)
    if m is None:
        S = 4
        g = Image.new("L", (r * S, r * S), 0)
        ImageDraw.Draw(g).pieslice((0, 0, 2 * r * S - 1, 2 * r * S - 1), 180, 270, fill=255)
        m = g.resize((r, r), Image.LANCZOS)
        _cantos_cache[r] = m
    return m


def _mascara(w, h, r):
    from PIL import ImageChops
    m = Image.new("L", (w, h), 255)
    r = max(0, min(int(r), w // 2, h // 2))
    if r > 0:
        c = _canto(r)
        for flip, pos in ((None, (0, 0)), (Image.FLIP_LEFT_RIGHT, (w - r, 0)), (Image.FLIP_TOP_BOTTOM, (0, h - r)),
                          (Image.ROTATE_180, (w - r, h - r))):
            cc = c.transpose(flip) if flip is not None else c
            m.paste(ImageChops.darker(m.crop((pos[0], pos[1], pos[0] + r, pos[1] + r)), cc), pos)
    return m


def rr_pil(w, h, r, fill, outline=None, ow=2):
    """Retângulo arredondado suave, rápido mesmo em tamanhos grandes (só os cantos são suavizados)."""
    w, h = max(int(w), 2), max(int(h), 2)
    cor = rgb(outline if outline else fill)
    img = Image.new("RGBA", (w, h), cor + (255,))
    img.putalpha(_mascara(w, h, r))
    if outline and w > 2 * ow + 2 and h > 2 * ow + 2:
        iw, ih = w - 2 * ow, h - 2 * ow
        dentro = Image.new("RGBA", (iw, ih), rgb(fill) + (255,))
        dentro.putalpha(_mascara(iw, ih, max(0, r - ow)))
        img.alpha_composite(dentro, (ow, ow))
    return img


def rr_img(w, h, r, fill, outline=None, ow=2):
    w, h = max(int(w), 2), max(int(h), 2)
    key = ("rr", w, h, r, fill, outline, ow)
    im = _cache.get(key)
    if im is not None:
        return im
    tkimg = ImageTk.PhotoImage(rr_pil(w, h, r, fill, outline, ow))
    _cache[key] = tkimg
    return tkimg


def _icone_arquivo(nome, px, cor):
    """Se existir gui_assets/icones/<nome>.png, usa o canal alfa dele como máscara e pinta com a cor pedida."""
    arq = os.path.join(base_dir(), "gui_assets", "icones", nome + ".png")
    if not os.path.isfile(arq):
        return None
    try:
        im = Image.open(arq).convert("RGBA")
        alfa = im.getchannel("A")
        if alfa.getextrema()[0] == 255:  # sem transparência: usa o brilho invertido (preto = traço)
            alfa = Image.eval(im.convert("L"), lambda v: 255 - v)
        alfa = alfa.resize((px, px), Image.LANCZOS)
        out = Image.new("RGBA", (px, px), rgb(cor) + (0,))
        out.putalpha(alfa)
        return out
    except Exception:
        return None


def fonte_pil(arquivo, px):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(base_dir(), "gui_assets", "fonts", arquivo), px)


def marca_img(largura, cor="#FFF5DB", autor=True, cor_autor=None, contorno=None):
    """Logotipo 'Scap' em letra script (Damion, exceção à regra da Inter) com sombra deslocada e
    rabisco sublinhado; 'by Essie N Pierot' (Inter SemiBold) fica abaixo, sem encostar."""
    S = 3
    f = fonte_pil("Damion-Regular.ttf", 240 * S)
    t = "Scap"
    bb = f.getbbox(t)
    w = bb[2] - bb[0]
    pad = 26 * S
    off = 7 * S                                   # sombra deslocada
    sub = 44 * S if autor else 0
    gap = 26 * S if autor else 0
    h = (bb[3] - bb[1]) + pad * 2 + sub + gap + 30 * S
    im = Image.new("RGBA", (w + pad * 2 + off, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = pad - bb[0], pad - bb[1]
    sombra = contorno or ("#073624" if rgb(cor)[0] > 200 else "#E3D0AE")
    ct = max(2, int(5 * S))
    d.text((x0 + off, y0 + off), t, font=f, fill=rgb(sombra) + (255,), stroke_width=ct, stroke_fill=rgb(sombra) + (255,))
    d.text((x0, y0), t, font=f, fill=rgb(cor) + (255,), stroke_width=ct // 2, stroke_fill=rgb(cor) + (255,))
    # rabisco curvo sublinhando a palavra (assinatura de logotipo)
    base = pad + (bb[3] - bb[1]) + 12 * S
    pts = []
    import math
    n = 60
    for i in range(n + 1):
        u = i / n
        xx = pad + 18 * S + u * (w - 40 * S)
        yy = base + 10 * S * math.sin(u * math.pi) * (1 - u) - 6 * S * u
        pts.append((xx, yy))
    for dx, dy, c in ((off * 0.8, off * 0.8, sombra), (0, 0, cor)):
        d.line([(x + dx, y + dy) for x, y in pts], fill=rgb(c) + (255,), width=int(6 * S), joint="curve")
        for (x, y), r in ((pts[0], 3 * S), (pts[-1], 3 * S)):
            d.ellipse((x + dx - r, y + dy - r, x + dx + r, y + dy + r), fill=rgb(c) + (255,))
    if autor:
        fa = fonte_pil("Inter-SemiBold.ttf", 46 * S)
        ta = "by Essie N Pierot"
        ya = base + 10 * S + gap
        d.text((pad + w - fa.getlength(ta) + 2 * S, ya), ta, font=fa, fill=rgb(cor_autor or cor) + (255,))
    im = im.crop(im.getbbox())
    return im.resize((largura, max(1, round(im.height * largura / im.width))), Image.LANCZOS)


def pil_icone(nome, px, cor=VERDE):
    """Ícone vetorial simples desenhado em máscara e colorido."""
    arq = _icone_arquivo(nome, px, cor)
    if arq is not None:
        return arq
    S = 4
    n = px * S
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    w = max(2, int(n * 0.085))

    def P(*pts):
        return [(x * n, y * n) for x, y in pts]

    def linha(pts, largura=w, fill=255):
        d.line(P(*pts), fill=fill, width=largura, joint="curve")
        for x, y in P(*pts):
            d.ellipse((x - largura / 2, y - largura / 2, x + largura / 2, y + largura / 2), fill=fill)

    def circ(cx, cy, r, fill=255, outline=None, width=0):
        d.ellipse(((cx - r) * n, (cy - r) * n, (cx + r) * n, (cy + r) * n), fill=fill, outline=outline, width=width)

    if nome == "mapa":
        pts = [(.1, .22), (.36, .13), (.64, .24), (.9, .13), (.9, .78), (.64, .88), (.36, .77), (.1, .87), (.1, .22)]
        linha(pts)
        linha([(.36, .13), (.36, .77)])
        linha([(.64, .24), (.64, .88)])
    elif nome == "engrenagem":
        import math
        for i in range(8):
            a = math.radians(i * 45)
            cx, cy = .5 + .33 * math.cos(a), .5 + .33 * math.sin(a)
            ca, sa = math.cos(a), math.sin(a)
            hw, hl = .085, .1
            pts = []
            for dx, dy in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)):
                pts.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
            d.polygon(P(*pts), fill=255)
        circ(.5, .5, .3)
        circ(.5, .5, .13, fill=0)
    elif nome == "mods":
        d.rounded_rectangle(P((.18, .3), (.82, .88)), int(.06 * n), fill=255)
        circ(.5, .26, .11)
        circ(.88, .6, .1)
        circ(.18, .6, .1, fill=0)
        circ(.5, .88, .1, fill=0)
    elif nome == "info":
        circ(.5, .5, .43, fill=0, outline=255, width=w)
        circ(.5, .3, .055)
        d.rounded_rectangle(P((.455, .43), (.545, .73)), int(.03 * n), fill=255)
    elif nome == "pasta":
        d.polygon(P((.06, .22), (.38, .22), (.47, .33), (.94, .33), (.94, .82), (.06, .82)), fill=255)
    elif nome == "cubo":
        pts = [(.5, .08), (.88, .29), (.88, .71), (.5, .92), (.12, .71), (.12, .29), (.5, .08)]
        linha(pts)
        linha([(.12, .29), (.5, .5), (.88, .29)])
        linha([(.5, .5), (.5, .92)])
    elif nome == "doc":
        d.rounded_rectangle(P((.2, .08), (.8, .92)), int(.08 * n), outline=255, width=w)
        for y in (.36, .52, .68):
            linha([(.34, y), (.66, y)], largura=max(2, int(w * .75)))
    elif nome == "pessoa":
        circ(.5, .31, .19)
        d.pieslice(P((.14, .56), (.86, 1.36)), 180, 360, fill=255)
    elif nome == "play":
        d.polygon(P((.26, .12), (.88, .5), (.26, .88)), fill=255)
    elif nome == "check":
        linha([(.17, .53), (.4, .75), (.84, .27)], largura=int(n * .13))
    elif nome in ("x", "fechar"):
        lw = int(n * (.11 if nome == "x" else .08))
        linha([(.24, .24), (.76, .76)], largura=lw)
        linha([(.76, .24), (.24, .76)], largura=lw)
    elif nome == "aviso":
        d.polygon(P((.5, .07), (.96, .9), (.04, .9)), fill=255)
        d.rounded_rectangle(P((.46, .36), (.54, .64)), int(.03 * n), fill=0)
        circ(.5, .76, .05, fill=0)
    elif nome == "mais":
        linha([(.2, .5), (.8, .5)], largura=int(n * .1))
        linha([(.5, .2), (.5, .8)], largura=int(n * .1))
    elif nome == "menos":
        linha([(.2, .5), (.8, .5)], largura=int(n * .1))
    elif nome == "enquadrar":
        lw = int(n * .09)
        for sx in (0, 1):
            for sy in (0, 1):
                x0, y0 = (.18 if sx == 0 else .82), (.18 if sy == 0 else .82)
                dx, dy = (.22 if sx == 0 else -.22), (.22 if sy == 0 else -.22)
                linha([(x0 + dx, y0), (x0, y0), (x0, y0 + dy)], largura=lw)
    elif nome == "min":
        linha([(.22, .5), (.78, .5)], largura=int(n * .08))
    elif nome == "max":
        d.rectangle(P((.24, .24), (.76, .76)), outline=255, width=int(n * .07))
    elif nome == "restaurar":
        d.rectangle(P((.22, .34), (.66, .78)), outline=255, width=int(n * .07))
        linha([(.34, .22), (.78, .22), (.78, .66)], largura=int(n * .07))
    elif nome == "sair":
        linha([(.42, .15), (.14, .15), (.14, .85), (.42, .85)], largura=int(n * .08))
        linha([(.34, .5), (.88, .5)], largura=int(n * .08))
        linha([(.68, .3), (.88, .5), (.68, .7)], largura=int(n * .08))
    elif nome == "chevron":
        linha([(.26, .38), (.5, .64), (.74, .38)], largura=int(n * .1))
    elif nome == "abrir":
        d.rounded_rectangle(P((.14, .24), (.64, .82)), int(.05 * n), outline=255, width=w)
        linha([(.5, .5), (.86, .14)], largura=w)
        linha([(.62, .14), (.86, .14), (.86, .38)], largura=w)
    elif nome == "atualizar":
        d.arc(P((.16, .16), (.84, .84)), 40, 320, fill=255, width=w)
        d.polygon(P((.72, .1), (.9, .36), (.58, .36)), fill=255)
    else:
        circ(.5, .5, .3)
    m = m.resize((px, px), Image.LANCZOS)
    im = Image.new("RGBA", (px, px), rgb(cor) + (255,))
    im.putalpha(m)
    return im


def tk_icone(nome, px, cor=VERDE):
    key = ("ic", nome, px, cor)
    im = _cache.get(key)
    if im is None:
        im = ImageTk.PhotoImage(pil_icone(nome, px, cor))
        _cache[key] = im
    return im


def tk_pil(img, nome=None):
    """PhotoImage de uma imagem PIL com a referência guardada no cache."""
    t = ImageTk.PhotoImage(img)
    _cache[("pil", id(t))] = t
    return t


def _deb(w, fn, *args, ms=70):
    """Agenda fn(*args) só depois que o tamanho parar de mudar (evita travar ao redimensionar/maximizar)."""
    ant = getattr(w, "_deb_id", None)
    if ant is not None:
        try:
            w.after_cancel(ant)
        except Exception:
            pass
    def _run():
        w._deb_id = None
        try:
            fn(*args)
        except tk.TclError:
            pass
    w._deb_id = w.after(ms, _run)


# ---------------------------------------------------------------- widgets
class Btn(tk.Canvas):
    ESTILOS = {
        "primario": dict(bg=VERDE, hov=VERDE_HOV, fg=CREME, borda=None),
        "secundario": dict(bg=CREME_CLARO, hov=CREME_ESC, fg=VERDE, borda=VERDE),
        "perigo": dict(bg=VERMELHO, hov=VERM_HOV, fg="#FFFFFF", borda=None),
        "claro": dict(bg=CREME_CLARO, hov=CREME_ESC, fg=VERDE, borda=BORDA),
        "desab": dict(bg=DESAB_BG, hov=DESAB_BG, fg=DESAB_FG, borda=None),
    }

    def __init__(self, master, texto, comando=None, estilo="primario", icone=None, w=None, h=40, bg=CREME,
                 tam=10, peso="bold", raio=10, icone_px=18):
        super().__init__(master, height=h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.texto, self.comando, self.estilo_nome, self.icone, self.h = texto, comando, estilo, icone, h
        self.raio, self.icone_px, self.peso, self.tam = raio, icone_px, peso, tam
        self.hover = False
        self.habilitado = True
        self.f = tkfont.Font(family=FONTE, size=tam, weight=peso)
        larg = w
        if larg is None:
            larg = self.f.measure(texto) + 36 + (icone_px + 8 if icone else 0)
        self.config(width=larg)
        self._bw = larg
        self.bind("<Configure>", lambda e: _deb(self, self._desenhar, e.width))
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._soltar)
        self._desenhar(larg)

    def _set_hover(self, v):
        self.hover = v
        self._desenhar(self._bw)

    def _soltar(self, e):
        if self.habilitado and self.comando and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.comando()

    def habilitar(self, sim):
        self.habilitado = sim
        self.config(cursor="hand2" if sim else "arrow")
        self._desenhar(self._bw)

    def definir_texto(self, t):
        self.texto = t
        self._desenhar(self._bw)

    def _desenhar(self, w):
        self._bw = w = max(w, 4)
        est = self.ESTILOS["desab" if not self.habilitado else self.estilo_nome]
        cor = est["hov"] if (self.hover and self.habilitado) else est["bg"]
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, self.raio, cor, est["borda"], 2))
        ic = None
        if self.icone:
            ic = tk_icone(self.icone, self.icone_px, est["fg"])
        tw = self.f.measure(self.texto)
        total = tw + (self.icone_px + 8 if ic else 0)
        x = (w - total) / 2
        if ic:
            self.create_image(x, self.h / 2, anchor="w", image=ic)
            x += self.icone_px + 8
        self.create_text(x, self.h / 2, anchor="w", text=self.texto, fill=est["fg"], font=self.f)


class IconBtn(tk.Canvas):
    """Botão quadrado só com ícone (zoom do mapa, controles da janela)."""

    def __init__(self, master, icone, comando, tam=34, px=18, bg=CREME_CLARO, hov=CREME_ESC, cor=VERDE, raio=8,
                 cor_hov=None, hov_icone=None):
        super().__init__(master, width=tam, height=tam, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.icone, self.comando, self.tam, self.px = icone, comando, tam, px
        self.bgc, self.hov, self.cor, self.raio = bg, hov, cor, raio
        self.cor_hov = cor_hov or hov
        self.hov_icone = hov_icone or cor
        self._h = False
        self.bind("<Enter>", lambda e: self._set(True))
        self.bind("<Leave>", lambda e: self._set(False))
        self.bind("<ButtonRelease-1>", lambda e: comando() if comando else None)
        self._desenhar()

    def _set(self, v):
        self._h = v
        self._desenhar()

    def trocar_icone(self, nome):
        self.icone = nome
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        fundo = self.cor_hov if self._h else self.bgc
        self.create_image(0, 0, anchor="nw", image=rr_img(self.tam, self.tam, self.raio, fundo))
        self.create_image(self.tam / 2, self.tam / 2, image=tk_icone(self.icone, self.px, self.hov_icone if self._h else self.cor))


class Check(tk.Canvas):
    def __init__(self, master, texto, variavel, bg=CREME, tam=10, comando=None, peso="normal", cor_texto=TEXTO):
        self.f = tkfont.Font(family=FONTE, size=tam, weight=peso)
        super().__init__(master, height=26, bg=bg, highlightthickness=0, bd=0, cursor="hand2",
                         width=34 + self.f.measure(texto))
        self.var, self.texto, self.comando, self.cor_texto = variavel, texto, comando, cor_texto
        self.bind("<ButtonRelease-1>", self._alt)
        self.var.trace_add("write", lambda *a: self._desenhar())
        self._desenhar()

    def _alt(self, e):
        self.var.set(not self.var.get())
        if self.comando:
            self.comando()

    def _desenhar(self):
        self.delete("all")
        on = bool(self.var.get())
        if on:
            self.create_image(2, 13, anchor="w", image=rr_img(22, 22, 6, VERDE))
            self.create_image(13, 13, image=tk_icone("check", 15, "#FFFFFF"))
        else:
            self.create_image(2, 13, anchor="w", image=rr_img(22, 22, 6, CREME_CLARO, VERDE_MED, 2))
        self.create_text(34, 13, anchor="w", text=self.texto, fill=self.cor_texto, font=self.f)


class Painel(tk.Canvas):
    """Cartão com cantos arredondados; os filhos vão em .inner. A altura segue o conteúdo."""

    def __init__(self, master, bg=CREME, fundo=CREME_CLARO, borda=BORDA, raio=14, pad=14, expandir=False):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=40)
        self.fundo, self.borda_c, self.raio, self.pad, self.expandir = fundo, borda, raio, pad, expandir
        self.inner = tk.Frame(self, bg=fundo)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.inner)
        self._bgid = None
        self._wh = (0, 0)
        self.bind("<Configure>", self._conf)
        self.inner.bind("<Configure>", self._conf_inner)

    def _conf(self, e):
        self._wh = (e.width, e.height)
        _deb(self, self._redesenhar)

    def _conf_inner(self, e):
        if not self.expandir:
            nh = self.inner.winfo_reqheight() + 2 * self.pad
            if abs(int(self.cget("height")) - nh) > 1:
                self.config(height=nh)

    def _redesenhar(self):
        w, h = self._wh
        if w < 4 or h < 4:
            return
        if self._bgid is not None:
            self.delete(self._bgid)
        self._bgid = self.create_image(0, 0, anchor="nw", image=rr_img(w, h, self.raio, self.fundo, self.borda_c, 2))
        self.tag_lower(self._bgid)
        self.itemconfigure(self._win, width=w - 2 * self.pad, height=h - 2 * self.pad if self.expandir else 0)


class Campo(tk.Canvas):
    """Campo de texto com borda arredondada. estado: None, 'ok', 'erro'."""

    def __init__(self, master, variavel=None, bg=CREME_CLARO, h=38, somente_leitura=False, largura=None, tam=10,
                 fundo="#FBF0DC", justificar="left"):
        super().__init__(master, height=h, bg=bg, highlightthickness=0, bd=0)
        if largura:
            self.config(width=largura)
        self.h = h
        self.fundo = fundo
        self.var = variavel or tk.StringVar()
        self.estado_v = None
        self.foco = False
        self.entry = tk.Entry(self, textvariable=self.var, bd=0, highlightthickness=0, bg=fundo, fg=TEXTO,
                              font=fonte(tam), relief="flat", insertbackground=VERDE, justify=justificar,
                              readonlybackground=fundo, disabledbackground=fundo, disabledforeground=MUDO)
        if somente_leitura:
            self.entry.config(state="readonly")
        self._win = self.create_window(10, h / 2, anchor="w", window=self.entry)
        self._bg = None
        self._wd = 0
        self.bind("<Configure>", self._conf)
        self.entry.bind("<FocusIn>", lambda e: self._foco(True))
        self.entry.bind("<FocusOut>", lambda e: self._foco(False))

    def _foco(self, v):
        self.foco = v
        self._desenhar()

    def estado(self, e):
        self.estado_v = e
        self._desenhar()

    def _conf(self, e):
        self._wd = e.width
        _deb(self, self._desenhar)

    def _desenhar(self):
        w = self._wd
        if w < 6:
            return
        cor = BORDA
        if self.estado_v == "ok":
            cor = OK
        elif self.estado_v == "erro":
            cor = ERRO
        elif self.foco:
            cor = VERDE
        if self._bg is not None:
            self.delete(self._bg)
        self._bg = self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, 9, self.fundo, cor, 2))
        self.tag_lower(self._bg)
        self.itemconfigure(self._win, width=w - 22, height=self.h - 12)


class Dropdown(tk.Canvas):
    def __init__(self, master, variavel, valores=(), comando=None, bg=CREME_CLARO, h=38, icone=None):
        super().__init__(master, height=h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.var, self.valores, self.comando, self.h, self.icone = variavel, list(valores), comando, h, icone
        self._wd = 0
        self.bind("<Configure>", lambda e: _deb(self, self._desenhar, e.width))
        self.bind("<ButtonRelease-1>", self._abrir)
        self.var.trace_add("write", lambda *a: self._desenhar(self._wd))

    def definir(self, valores):
        self.valores = list(valores)
        self._desenhar(self._wd)

    def _abrir(self, e):
        if not self.valores:
            return
        m = tk.Menu(self, tearoff=0, bg=CREME_CLARO, fg=TEXTO, activebackground=VERDE, activeforeground=CREME,
                    font=fonte(10), bd=1, relief="solid")
        for v in self.valores:
            m.add_command(label=v, command=lambda v=v: self._escolher(v))
        m.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.h)

    def _escolher(self, v):
        self.var.set(v)
        if self.comando:
            self.comando(v)

    def _desenhar(self, w):
        self._wd = w
        if w < 6:
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, 9, "#FBF0DC", BORDA, 2))
        x = 12
        if self.icone:
            self.create_image(x, self.h / 2, anchor="w", image=self.icone)
            x += 34
        self.create_text(x, self.h / 2, anchor="w", text=self.var.get(), fill=TEXTO, font=fonte(10))
        self.create_image(w - 14, self.h / 2, image=tk_icone("chevron", 16, VERDE))


class NavItem(tk.Canvas):
    def __init__(self, master, texto, icone, comando, bg=VERDE, h=48):
        super().__init__(master, height=h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.texto, self.icone, self.comando, self.h, self.bgc = texto, icone, comando, h, bg
        self.ativo = False
        self.hover = False
        self._wd = 0
        self.bind("<Configure>", lambda e: _deb(self, self._desenhar, e.width))
        self.bind("<Enter>", lambda e: self._h(True))
        self.bind("<Leave>", lambda e: self._h(False))
        self.bind("<ButtonRelease-1>", lambda e: comando())

    def _h(self, v):
        self.hover = v
        self._desenhar(self._wd)

    def definir_ativo(self, v):
        self.ativo = v
        self._desenhar(self._wd)

    def _desenhar(self, w):
        self._wd = w
        if w < 6:
            return
        self.delete("all")
        if self.ativo:
            self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, 10, VERMELHO))
        elif self.hover:
            self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, 10, VERDE_HOV))
        self.create_image(20, self.h / 2, anchor="w", image=tk_icone(self.icone, 26, "#FFF5DB"))
        self.create_text(64, self.h / 2, anchor="w", text=self.texto, fill="#FFF5DB", font=fonte(11, "normal"))


class BarraProgresso(tk.Canvas):
    def __init__(self, master, bg=CREME, h=18):
        super().__init__(master, height=h, bg=bg, highlightthickness=0, bd=0)
        self.h = h
        self.frac = 0.0
        self._wd = 0
        self.bind("<Configure>", lambda e: _deb(self, self._desenhar, e.width))

    def definir(self, f):
        self.frac = max(0.0, min(1.0, f))
        self._desenhar(self._wd)

    def _desenhar(self, w):
        self._wd = w
        if w < 8:
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=rr_img(w, self.h, self.h // 2, CREME_ESC, BORDA, 2))
        fw = int((w - 4) * self.frac)
        if fw >= self.h - 4:
            self.create_image(2, 2, anchor="nw", image=rr_img(fw, self.h - 4, (self.h - 4) // 2, VERDE))
        elif fw > 3:
            self.create_image(2, 2, anchor="nw", image=rr_img(self.h - 4, self.h - 4, (self.h - 4) // 2, VERDE))


class ListaRolavel(tk.Frame):
    """Lista com rolagem e barra fina desenhada à mão."""

    def __init__(self, master, bg=CREME_CLARO):
        super().__init__(master, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.barra = tk.Canvas(self, width=10, bg=bg, highlightthickness=0, bd=0)
        self.barra.pack(side="right", fill="y", padx=(4, 2), pady=2)
        self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=bg)
        self._cw = self.cv.create_window(0, 0, anchor="nw", window=self.inner)
        self.inner.bind("<Configure>", lambda e: self._atualizar())
        self.cv.bind("<Configure>", self._conf)
        self.cv.bind("<Enter>", lambda e: self._bind_roda(True))
        self.cv.bind("<Leave>", lambda e: self._bind_roda(False))
        self.inner.bind("<Enter>", lambda e: self._bind_roda(True))
        self.barra.bind("<B1-Motion>", self._arrasta)
        self.barra.bind("<Button-1>", self._arrasta)
        self._thumb = (0, 0)

    def _conf(self, e):
        self.cv.itemconfigure(self._cw, width=e.width)
        self._atualizar()

    def _bind_roda(self, v):
        if v:
            self.bind_all("<MouseWheel>", self._roda)
            self.bind_all("<Button-4>", lambda e: self._rolar(-1))
            self.bind_all("<Button-5>", lambda e: self._rolar(1))
        else:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")

    def _roda(self, e):
        self._rolar(-1 if e.delta > 0 else 1)

    def _rolar(self, d):
        self.cv.yview_scroll(d * 2, "units")
        self._atualizar()

    def _atualizar(self):
        self.cv.configure(scrollregion=(0, 0, 1, max(self.inner.winfo_reqheight(), 1)))
        total = max(self.inner.winfo_reqheight(), 1)
        vis = self.cv.winfo_height()
        self.barra.delete("all")
        if total <= vis or vis < 10:
            return
        a, b = self.cv.yview()
        h = self.barra.winfo_height()
        y0, y1 = a * h, b * h
        self._thumb = (y0, y1)
        self.barra.create_image(0, 0, anchor="nw", image=rr_img(8, max(int(h) - 2, 4), 4, CREME_ESC))
        self.barra.create_image(0, int(y0), anchor="nw", image=rr_img(8, max(int(y1 - y0), 14), 4, VERDE_MED))

    def _arrasta(self, e):
        h = max(self.barra.winfo_height(), 1)
        a, b = self.cv.yview()
        self.cv.yview_moveto(max(0, min(1 - (b - a), e.y / h - (b - a) / 2)))
        self._atualizar()


def centralizar(janela, pai, w, h):
    pai.update_idletasks()
    x = pai.winfo_rootx() + (pai.winfo_width() - w) // 2
    y = pai.winfo_rooty() + (pai.winfo_height() - h) // 2
    janela.geometry("%dx%d+%d+%d" % (w, h, max(x, 0), max(y, 0)))


_carregar_inter()
