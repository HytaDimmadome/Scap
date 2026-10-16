import os
import io
import re
import sys
import json
import copy
import gzip
import math
import zlib
import zipfile
import struct
import argparse
import colorsys
import numpy as np
from collections import OrderedDict, Counter

VERSAO_FORMATO = 2
MAGIA = b"MCSC"


class Cancelado(Exception):
    pass


class _Leitor:
    __slots__ = ("b", "p")

    def __init__(self, b):
        self.b = b
        self.p = 0


_S_BYTE = struct.Struct(">b")
_S_SHORT = struct.Struct(">h")
_S_INT = struct.Struct(">i")
_S_LONG = struct.Struct(">q")
_S_FLOAT = struct.Struct(">f")
_S_DOUBLE = struct.Struct(">d")
_S_USHORT = struct.Struct(">H")


def _ler_payload(r, t):
    b = r.b
    if t == 1:
        v = _S_BYTE.unpack_from(b, r.p)[0]
        r.p += 1
        return v
    if t == 2:
        v = _S_SHORT.unpack_from(b, r.p)[0]
        r.p += 2
        return v
    if t == 3:
        v = _S_INT.unpack_from(b, r.p)[0]
        r.p += 4
        return v
    if t == 4:
        v = _S_LONG.unpack_from(b, r.p)[0]
        r.p += 8
        return v
    if t == 5:
        v = _S_FLOAT.unpack_from(b, r.p)[0]
        r.p += 4
        return v
    if t == 6:
        v = _S_DOUBLE.unpack_from(b, r.p)[0]
        r.p += 8
        return v
    if t == 7:
        n = _S_INT.unpack_from(b, r.p)[0]
        r.p += 4
        v = b[r.p:r.p + n]
        r.p += n
        return v
    if t == 8:
        n = _S_USHORT.unpack_from(b, r.p)[0]
        r.p += 2
        v = b[r.p:r.p + n].decode("utf-8", "replace")
        r.p += n
        return v
    if t == 9:
        tipo = b[r.p]
        n = _S_INT.unpack_from(b, r.p + 1)[0]
        r.p += 5
        return [_ler_payload(r, tipo) for _ in range(n)]
    if t == 10:
        d = {}
        while True:
            tt = b[r.p]
            r.p += 1
            if tt == 0:
                break
            n = _S_USHORT.unpack_from(b, r.p)[0]
            r.p += 2
            nome = b[r.p:r.p + n].decode("utf-8", "replace")
            r.p += n
            d[nome] = _ler_payload(r, tt)
        return d
    if t == 11:
        n = _S_INT.unpack_from(b, r.p)[0]
        r.p += 4
        v = np.frombuffer(b, dtype=">i4", count=n, offset=r.p).astype(np.int32)
        r.p += 4 * n
        return v
    if t == 12:
        n = _S_INT.unpack_from(b, r.p)[0]
        r.p += 4
        v = np.frombuffer(b, dtype=">u8", count=n, offset=r.p).astype(np.uint64)
        r.p += 8 * n
        return v
    raise ValueError("Tag NBT desconhecida: %d" % t)


def ler_nbt(b):
    r = _Leitor(b)
    t = b[0]
    n = _S_USHORT.unpack_from(b, 1)[0]
    r.p = 3 + n
    return _ler_payload(r, t)


class PastaRegioes:
    def __init__(self, pasta):
        self.pasta = pasta
        self._cache = {}

    def _abrir(self, rx, rz):
        k = (rx, rz)
        if k not in self._cache:
            p = os.path.join(self.pasta, "r.%d.%d.mca" % (rx, rz))
            dados = None
            if os.path.exists(p) and os.path.getsize(p) >= 8192:
                with open(p, "rb") as f:
                    dados = f.read()
            if len(self._cache) >= 4:
                self._cache.pop(next(iter(self._cache)))
            self._cache[k] = dados
        return self._cache[k]

    def chunk(self, cx, cz):
        dados = self._abrir(cx >> 5, cz >> 5)
        if dados is None:
            return None
        i = 4 * ((cx & 31) + (cz & 31) * 32)
        ent = int.from_bytes(dados[i:i + 4], "big")
        n_setores = ent & 255
        if ent == 0 or n_setores == 0:
            return None
        off = (ent >> 8) * 4096
        tam = int.from_bytes(dados[off:off + 4], "big")
        comp = dados[off + 4]
        bruto = dados[off + 5:off + 4 + tam]
        try:
            if comp == 2:
                raw = zlib.decompress(bruto)
            elif comp == 1:
                raw = gzip.decompress(bruto)
            elif comp == 3:
                raw = bruto
            else:
                return None
            return ler_nbt(raw)
        except Exception:
            return None


def achar_dimensoes(pasta_mundo):
    pasta_mundo = os.path.abspath(pasta_mundo)
    if os.path.basename(pasta_mundo) == "region" and os.path.isdir(pasta_mundo):
        return [("Região", pasta_mundo)]
    cand = [
        ("Overworld", os.path.join(pasta_mundo, "region")),
        ("Nether", os.path.join(pasta_mundo, "DIM-1", "region")),
        ("End", os.path.join(pasta_mundo, "DIM1", "region")),
    ]
    dims = os.path.join(pasta_mundo, "dimensions")
    if os.path.isdir(dims):
        for ns in sorted(os.listdir(dims)):
            nsdir = os.path.join(dims, ns)
            if not os.path.isdir(nsdir):
                continue
            for nome in sorted(os.listdir(nsdir)):
                cand.append(("%s:%s" % (ns, nome), os.path.join(nsdir, nome, "region")))
    return [(n, p) for n, p in cand if os.path.isdir(p)]


AR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air",
      "minecraft:barrier", "minecraft:light", "minecraft:structure_void"}

PROPS_VISUAIS = ("facing", "half", "shape", "type", "axis", "open", "hinge",
                 "rotation", "face")

TOKENS_TRANSP = {
    "glass", "leaves", "water", "lava", "pane", "bars", "stairs", "slab",
    "fence", "wall", "door", "trapdoor", "torch", "lantern", "chain", "ladder",
    "vine", "vines", "sign", "carpet", "rail", "rails", "button", "lever",
    "fern", "bush", "sapling", "cobweb", "bed", "banner", "candle", "skull",
    "head", "cactus", "kelp", "seagrass", "coral", "fan", "tulip", "rose",
    "dandelion", "poppy", "orchid", "allium", "azalea", "lilac", "peony",
    "sunflower", "cornflower", "lily", "flower", "pot", "potted", "grass",
    "scaffolding", "sprouts", "roots", "fire", "plate", "tripwire", "wire",
    "repeater", "comparator", "rod", "anvil", "hopper", "cauldron", "stand",
    "ice",
}
EXATOS_TRANSP = {
    "minecraft:snow", "minecraft:light", "minecraft:structure_void",
    "minecraft:red_mushroom", "minecraft:brown_mushroom",
    "minecraft:sugar_cane", "minecraft:wheat", "minecraft:carrots",
    "minecraft:potatoes", "minecraft:beetroots", "minecraft:melon_stem",
    "minecraft:pumpkin_stem", "minecraft:bamboo", "minecraft:cocoa",
    "minecraft:nether_wart", "minecraft:turtle_egg",
}


def e_transparente(nome):
    if nome in EXATOS_TRANSP:
        return True
    caminho = nome.split(":", 1)[-1]
    if caminho.endswith("_block") and caminho not in ("slime_block", "honey_block"):
        return False
    toks = caminho.split("_")
    if "ice" in toks and ("packed" in toks or "blue" in toks):
        return False
    return any(t in TOKENS_TRANSP for t in toks)


def chave_bloco(entrada, guardar_estados):
    nome = entrada["Name"]
    if guardar_estados:
        pr = entrada.get("Properties")
        if pr:
            partes = ["%s=%s" % (k, pr[k]) for k in sorted(pr) if k in PROPS_VISUAIS]
            if partes:
                return nome + "[" + ",".join(partes) + "]"
    return nome


FACES = ("down", "up", "north", "south", "west", "east")
DIR_VEC = {"down": (0, -1, 0), "up": (0, 1, 0), "north": (0, 0, -1),
           "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
VERTS_FACE = {
    "down": ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)),
    "up": ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
    "north": ((1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)),
    "south": ((0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)),
    "west": ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)),
    "east": ((1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)),
}
F_TRANSP, F_OPACO, F_TRANSLUC, F_AGUA, F_CULLSAME = 1, 2, 4, 8, 16
TINTAS = {"1": "91bd59", "2": "77ab2f", "3": "3f76e4", "4": "619961", "5": "80a755", "6": "208030"}


def _ns(ref, padrao="minecraft"):
    if ":" in ref:
        a, b = ref.split(":", 1)
        return a, b
    return padrao, ref


def _carregar_json(dados):
    try:
        return json.loads(dados.decode("utf-8-sig"))
    except ValueError:
        pass
    try:
        t = dados.decode("utf-8-sig", "replace")
        t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        t = re.sub(r'(^|[^:"\\])//[^\n]*', r"\1", t)
        t = re.sub(r",\s*([}\]])", r"\1", t)
        return json.loads(t)
    except ValueError:
        return None


def _uv_padrao(face, f, t):
    if face == "down":
        return [f[0], 16 - t[2], t[0], 16 - f[2]]
    if face == "up":
        return [f[0], f[2], t[0], t[2]]
    if face == "north":
        return [16 - t[0], 16 - t[1], 16 - f[0], 16 - f[1]]
    if face == "south":
        return [f[0], 16 - t[1], t[0], 16 - f[1]]
    if face == "west":
        return [f[2], 16 - t[1], t[2], 16 - f[1]]
    return [16 - t[2], 16 - t[1], 16 - f[2], 16 - f[1]]


def _rot_elemento(p, rot):
    o = rot.get("origin", [8, 8, 8])
    ang = float(rot.get("angle", 0))
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)
    q = [p[0] - o[0], p[1] - o[1], p[2] - o[2]]
    ax = rot.get("axis", "y")
    if ax == "x":
        q[1], q[2] = q[1] * c - q[2] * s, q[1] * s + q[2] * c
    elif ax == "y":
        q[0], q[2] = q[0] * c + q[2] * s, -q[0] * s + q[2] * c
    else:
        q[0], q[1] = q[0] * c - q[1] * s, q[0] * s + q[1] * c
    if rot.get("rescale") and abs(c) > 1e-6:
        k = 1.0 / abs(c)
        if ax == "x":
            q[1] *= k
            q[2] *= k
        elif ax == "y":
            q[0] *= k
            q[2] *= k
        else:
            q[0] *= k
            q[1] *= k
    return [q[0] + o[0], q[1] + o[1], q[2] + o[2]]


def _rot_ponto(p, rx, ry):
    x, y, z = p[0] - 8, p[1] - 8, p[2] - 8
    for _ in range((rx // 90) % 4):
        y, z = z, -y
    for _ in range((ry // 90) % 4):
        x, z = -z, x
    return [x + 8, y + 8, z + 8]


def _rot_vetor(v, rx, ry):
    x, y, z = v
    for _ in range((rx // 90) % 4):
        y, z = z, -y
    for _ in range((ry // 90) % 4):
        x, z = -z, x
    return (x, y, z)


class Recursos:

    def __init__(self, jar_mc=None, pasta_mods=None, pacotes=(), avisos=None, excluir_mods=()):
        self.avisos = avisos if avisos is not None else []
        self.indice = {}
        self._abertos = OrderedDict()
        self._json = {}
        self._tex = {}
        self._alfa_cache = {}
        self._props = {}
        self._modelos = {}
        self._infos = {}
        self._gen = {}
        self.n_zips = 0

        def add_zip(c):
            try:
                with zipfile.ZipFile(c) as z:
                    achou = False
                    for n in z.namelist():
                        if n.startswith("assets/") and not n.endswith("/"):
                            self.indice[n] = ("z", c, n)
                            achou = True
                    if achou:
                        self.n_zips += 1
            except Exception as e:
                self.avisos.append("Não consegui abrir %s (%s)" % (os.path.basename(c), e))

        def add_dir(pasta):
            base = os.path.join(pasta, "assets")
            for raiz, _, arqs in os.walk(base):
                for a in arqs:
                    full = os.path.join(raiz, a)
                    rel = os.path.relpath(full, pasta).replace(os.sep, "/")
                    self.indice[rel] = ("d", full, rel)
            self.n_zips += 1

        if jar_mc and os.path.isfile(jar_mc):
            add_zip(jar_mc)
        elif jar_mc:
            self.avisos.append("Jar do Minecraft não encontrado: %s" % jar_mc)
        if pasta_mods and os.path.isdir(pasta_mods):
            excl = set(excluir_mods or ())
            for f in sorted(os.listdir(pasta_mods)):
                if f.lower().endswith((".jar", ".zip")) and f not in excl:
                    add_zip(os.path.join(pasta_mods, f))
        for p in pacotes or ():
            if os.path.isdir(p):
                add_dir(p)
            elif os.path.isfile(p):
                add_zip(p)
            else:
                self.avisos.append("Resource pack não encontrado: %s" % p)

    @property
    def tem_fontes(self):
        return bool(self.indice)

    def ler(self, caminho):
        e = self.indice.get(caminho)
        if e is None:
            return None
        tipo, base, nome = e
        try:
            if tipo == "d":
                with open(base, "rb") as f:
                    return f.read()
            z = self._abertos.pop(base, None)
            if z is None:
                z = zipfile.ZipFile(base)
            self._abertos[base] = z
            while len(self._abertos) > 24:
                _, velho = self._abertos.popitem(last=False)
                try:
                    velho.close()
                except OSError:
                    pass
            return z.read(nome)
        except OSError:
            return None

    def json(self, caminho):
        if caminho not in self._json:
            d = self.ler(caminho)
            self._json[caminho] = _carregar_json(d) if d is not None else None
        return self._json[caminho]

    def blockstate(self, nome):
        ns, p = _ns(nome)
        return self.json("assets/%s/blockstates/%s.json" % (ns, p))

    def props_relevantes(self, nome):
        r = self._props.get(nome)
        if r is None:
            r = set()
            bs = self.blockstate(nome)
            if isinstance(bs, dict):
                for k in (bs.get("variants") or {}):
                    for par in str(k).split(","):
                        if "=" in par:
                            r.add(par.split("=", 1)[0].strip())

                def cond(c):
                    if isinstance(c, dict):
                        for k, v in c.items():
                            if k in ("OR", "AND") and isinstance(v, list):
                                for s in v:
                                    cond(s)
                            else:
                                r.add(k)
                for parte in bs.get("multipart") or []:
                    cond(parte.get("when"))
            self._props[nome] = r
        return r

    @staticmethod
    def _cond_ok(c, props):
        if not isinstance(c, dict):
            return True
        if "OR" in c:
            return any(Recursos._cond_ok(s, props) for s in c["OR"])
        if "AND" in c:
            return all(Recursos._cond_ok(s, props) for s in c["AND"])
        for k, v in c.items():
            atual = str(props.get(k, "false")).lower()
            if atual not in str(v).lower().split("|"):
                return False
        return True

    def _variantes(self, nome, props, bucket=None):
        bs = self.blockstate(nome)
        self._alea = False
        if not isinstance(bs, dict):
            return None
        saida = []

        def escolhe(v):
            if isinstance(v, list):
                lista = [e for e in v if isinstance(e, dict) and "model" in e]
                if len({e["model"] for e in lista}) > 1:
                    self._alea = True
                if bucket is not None and len(lista) > 1:
                    pesos = [max(0, float(e.get("weight", 1))) for e in lista]
                    alvo, acum, v = (bucket + 0.5) / self.BUCKETS * (sum(pesos) or 1), 0.0, lista[-1]
                    for e, w in zip(lista, pesos):
                        acum += w
                        if alvo < acum:
                            v = e
                            break
                else:
                    v = v[0] if v else None
            if isinstance(v, dict) and "model" in v:
                saida.append((v["model"], int(v.get("x", 0)) % 360,
                              int(v.get("y", 0)) % 360, bool(v.get("uvlock", False))))
        vs = bs.get("variants")
        if isinstance(vs, dict) and vs:
            melhor = None
            for k, v in vs.items():
                conds = [p.split("=", 1) for p in str(k).split(",") if "=" in p]
                if all(str(props.get(a.strip())) == b.strip() for a, b in conds):
                    if melhor is None or len(conds) > melhor[0]:
                        melhor = (len(conds), v)
            if melhor is None:
                melhor = (0, next(iter(vs.values())))
            escolhe(melhor[1])
        for parte in bs.get("multipart") or []:
            w = parte.get("when")
            if w is None or self._cond_ok(w, props):
                escolhe(parte.get("apply"))
        return saida

    def _modelo_achatado(self, ref):
        ns, p = _ns(ref)
        chave = "%s:%s" % (ns, p)
        if chave in self._modelos:
            return self._modelos[chave]
        cadeia, vistos, atual = [], set(), chave
        while atual and atual not in vistos and len(cadeia) < 16:
            vistos.add(atual)
            ns2, p2 = _ns(atual)
            if p2.startswith("builtin/"):
                cadeia.append({"__builtin__": p2})
                break
            j = self.json("assets/%s/models/%s.json" % (ns2, p2))
            if not isinstance(j, dict):
                break
            cadeia.append(j)
            par = j.get("parent")
            atual = "%s:%s" % _ns(par) if isinstance(par, str) else None
        texturas = {}
        for j in reversed(cadeia):
            if isinstance(j.get("textures"), dict):
                texturas.update(j["textures"])
        elementos = None
        for j in cadeia:
            if "__builtin__" in j:
                continue
            if isinstance(j.get("elements"), list):
                elementos = j["elements"]
                break
        r = {"texturas": texturas, "elementos": elementos}
        self._modelos[chave] = r
        return r

    @staticmethod
    def _tex_ref(texturas, valor):
        n = 0
        while isinstance(valor, str) and valor.startswith("#") and n < 12:
            valor = texturas.get(valor[1:])
            if isinstance(valor, dict):
                valor = valor.get("sprite") or valor.get("texture")
            n += 1
        if not isinstance(valor, str) or valor.startswith("#"):
            return None
        if valor.startswith("@"):
            return valor
        ns, p = _ns(valor)
        return "%s:%s" % (ns, p)

    def _quads(self, elementos, texturas, rx, ry, uvlock):
        quads = []
        for el in elementos:
            try:
                f = [float(v) for v in el["from"]]
                t = [float(v) for v in el["to"]]
            except (KeyError, TypeError, ValueError):
                continue
            rot_el = el.get("rotation") if isinstance(el.get("rotation"), dict) else None
            sombra = 1 if el.get("shade", True) else 0
            for nome_face, fc in (el.get("faces") or {}).items():
                if nome_face not in VERTS_FACE or not isinstance(fc, dict):
                    continue
                tid = self._tex_ref(texturas, fc.get("texture")) or "minecraft:missing"
                uv = fc.get("uv") or _uv_padrao(nome_face, f, t)
                rot = int(fc.get("rotation", 0)) % 360
                if uvlock and ry:
                    if nome_face == "up":
                        rot = (rot - ry) % 360
                    elif nome_face == "down":
                        rot = (rot + ry) % 360
                verts, uvs = [], []
                for i, (sx, sy, sz) in enumerate(VERTS_FACE[nome_face]):
                    p = [t[0] if sx else f[0], t[1] if sy else f[1], t[2] if sz else f[2]]
                    if rot_el:
                        p = _rot_elemento(p, rot_el)
                    if rx or ry:
                        p = _rot_ponto(p, rx, ry)
                    verts.append(p)
                    k = (i + rot // 90) % 4
                    u = uv[0] if k in (0, 1) else uv[2]
                    v = uv[1] if k in (0, 3) else uv[3]
                    uvs.append((u / 16.0, v / 16.0))
                cull = -1
                c = fc.get("cullface")
                if c in DIR_VEC:
                    vec = _rot_vetor(DIR_VEC[c], rx, ry)
                    cull = next(i for i, n in enumerate(FACES) if DIR_VEC[n] == vec)
                quads.append((tid, int(fc.get("tintindex", -1)), cull, sombra, verts, uvs))
        return quads

    def _quads_fluido(self, nome):
        tex = "block/water_still" if nome.endswith("water") else "block/lava_still"
        faces = {n: {"texture": "#a", "cullface": n if n != "up" else None, "tintindex": 0 if nome.endswith("water") else -1}
                 for n in FACES}
        faces["up"].pop("cullface")
        el = [{"from": [0, 0, 0], "to": [16, 14, 16], "faces": faces}]
        return self._quads(el, {"a": tex}, 0, 0, False)

    def _quads_cubo(self, nome, tid):
        faces = {n: {"texture": "#a", "cullface": n} for n in FACES}
        el = [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": faces}]
        return self._quads(el, {"a": tid}, 0, 0, False)

    @staticmethod
    def _primeiro_quadro(arr, meta):
        if meta is None:
            return arr
        h, w = arr.shape[:2]
        fw, fh, quadro = w, w if h >= w else h, 0
        try:
            an = json.loads(bytes(meta).decode("utf-8-sig")).get("animation", {})
            if "width" in an:
                fw = int(an["width"])
            if "height" in an:
                fh = int(an["height"])
            elif "width" in an and h >= w:
                fh = fw
            fr = an.get("frames")
            if fr:
                f0 = fr[0]
                quadro = int(f0["index"] if isinstance(f0, dict) else f0)
        except ValueError:
            pass
        if fw <= 0 or fh <= 0 or fw > w or fh > h:
            return arr
        por_linha = max(w // fw, 1)
        r, c = divmod(quadro, por_linha)
        if (r + 1) * fh > h:
            r, c = 0, 0
        return arr[r * fh:(r + 1) * fh, c * fw:(c + 1) * fw]

    animar = True
    MAX_QUADROS = 10 ** 9
    MAX_PASSOS = 10 ** 9

    def animacao(self, tid):
        cache = self.__dict__.setdefault("_anim", {})
        if tid in cache:
            return cache[tid]
        res = None
        try:
            dados = meta = None
            if tid.startswith("@gen:") or tid.startswith("cor:") or tid.endswith("#opaca") or tid == "minecraft:missing":
                pass
            elif tid.startswith("@"):
                dados, meta = self.ler(tid[1:] + ".png"), self.ler(tid[1:] + ".png.mcmeta")
            else:
                ns, p = _ns(tid)
                meta = self.ler("assets/%s/textures/%s.png.mcmeta" % (ns, p))
                dados = self.ler("assets/%s/textures/%s.png" % (ns, p)) if meta is not None else None
            if dados is not None and meta is not None:
                from PIL import Image
                an = json.loads(bytes(meta).decode("utf-8-sig")).get("animation")
                if an is not None:
                    arr = np.array(Image.open(io.BytesIO(dados)).convert("RGBA"))
                    h, w = arr.shape[:2]
                    fw, fh = int(an.get("width", w)), int(an.get("height", w if h >= w else h))
                    if "width" in an and "height" not in an and h >= w:
                        fh = fw
                    if 0 < fw <= w and 0 < fh <= h:
                        pl = max(w // fw, 1)
                        total = pl * (h // fh)
                        base = max(1, int(an.get("frametime", 1)))
                        fr = an.get("frames")
                        seq = []
                        if fr:
                            for f in fr:
                                if isinstance(f, dict):
                                    seq.append((int(f["index"]), max(1, int(f.get("time", base)))))
                                else:
                                    seq.append((int(f), base))
                        else:
                            seq = [(i, base) for i in range(total)]
                        seq = [(i, t) for i, t in seq if 0 <= i < total]
                        usados = sorted({i for i, _ in seq})
                        if len(usados) > self.MAX_QUADROS:
                            passo = len(usados) / float(self.MAX_QUADROS)
                            manter = [usados[int(k * passo)] for k in range(self.MAX_QUADROS)]
                            mapa = {u: min(manter, key=lambda m: abs(m - u)) for u in usados}
                            seq = [(mapa[i], t) for i, t in seq]
                            usados = sorted(set(manter))
                        if len(usados) >= 2 and len(seq) <= self.MAX_PASSOS:
                            quadros = {}
                            for i in usados:
                                r, c = divmod(i, pl)
                                quadros[i] = self._preparar_pixels(tid, arr[r * fh:(r + 1) * fh, c * fw:(c + 1) * fw])
                            res = {"quadros": quadros, "seq": seq}
        except Exception:
            res = None
        cache[tid] = res
        return res

    def textura(self, tid):
        if tid in self._tex:
            return self._tex[tid]
        arr = None
        if tid.endswith("#opaca"):
            base = self.textura(tid[:-6])
            if base is not None:
                arr = base.copy()
                ok = arr[:, :, 3] >= 128
                if ok.any():
                    media = arr[:, :, :3][ok].astype(np.float32).mean(axis=0)
                    arr[~ok, :3] = (media * 0.45).round().astype(np.uint8)
                arr[:, :, 3] = 255
            self._tex[tid] = arr
            return arr
        if tid.startswith("@gen:"):
            return self._gen.get(tid)
        if tid.startswith("@"):
            dados = self.ler(tid[1:] + ".png")
            if dados is not None:
                try:
                    from PIL import Image
                    arr = np.array(Image.open(io.BytesIO(dados)).convert("RGBA"))
                    arr = self._primeiro_quadro(arr, self.ler(tid[1:] + ".png.mcmeta"))
                    arr = self._preparar_pixels(tid, arr)
                except Exception:
                    arr = None
            self._tex[tid] = arr
            return arr
        if tid.startswith("cor:"):
            h = tid[4:]
            arr = np.empty((16, 16, 4), np.uint8)
            arr[:, :, 0], arr[:, :, 1], arr[:, :, 2] = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            arr[:, :, 3] = 255
        elif tid == "minecraft:missing":
            arr = np.zeros((16, 16, 4), np.uint8)
            arr[:, :, 3] = 255
            arr[:8, :8, 0] = arr[8:, 8:, 0] = 248
            arr[:8, :8, 2] = arr[8:, 8:, 2] = 248
        else:
            ns, p = _ns(tid)
            dados = self.ler("assets/%s/textures/%s.png" % (ns, p))
            if dados is not None:
                try:
                    from PIL import Image
                except ImportError:
                    raise RuntimeError("Para usar texturas é preciso instalar o Pillow: pip install pillow")
                try:
                    arr = np.array(Image.open(io.BytesIO(dados)).convert("RGBA"))
                    arr = self._primeiro_quadro(arr, self.ler("assets/%s/textures/%s.png.mcmeta" % (ns, p)))
                except Exception:
                    arr = None
                if arr is not None:
                    arr = self._preparar_pixels(tid, arr)
        self._tex[tid] = arr
        return arr

    folhas_opacas = True

    def _preparar_pixels(self, tid, arr):
        al = arr[:, :, 3]
        opacos = al >= 128
        if not opacos.any() or opacos.all():
            return arr
        arr = arr.copy()
        media = arr[:, :, :3][opacos].astype(np.float32).mean(axis=0)
        arr[al < 128, :3] = media.round().astype(np.uint8)
        return arr

    def _alfa(self, tid):
        r = self._alfa_cache.get(tid)
        if r is None:
            a = self.textura(tid)
            if a is None:
                r = (True, False)
            else:
                al = a[:, :, 3]
                r = (bool((al == 255).all()), bool(((al > 0) & (al < 255)).mean() > 0.25))
            self._alfa_cache[tid] = r
        return r


    CORES_DYE = [(0xFF, 0xFF, 0xFF), (0xD8, 0x7F, 0x33), (0xB2, 0x4C, 0xD8), (0x66, 0x99, 0xD8), (0xE5, 0xE5, 0x33),
                 (0x7F, 0xCC, 0x19), (0xF2, 0x7F, 0xA5), (0x4C, 0x4C, 0x4C), (0x99, 0x99, 0x99), (0x4C, 0x7F, 0x99),
                 (0x7F, 0x3F, 0xB2), (0x33, 0x4C, 0xB2), (0x66, 0x4C, 0x33), (0x66, 0x7F, 0x33), (0x99, 0x33, 0x33),
                 (0x19, 0x19, 0x19)]

    def _png_bruto(self, caminho):
        d = self.ler(caminho)
        if d is None:
            return None
        try:
            from PIL import Image
            return np.array(Image.open(io.BytesIO(d)).convert("RGBA"))
        except ImportError:
            return None

    def info_quadro(self, nome, props, pixels):
        sprite = self._png_bruto("assets/supplementaries/textures/block/blackboard.png")
        img = np.zeros((16, 16, 4), np.uint8)
        img[:, :, 3] = 255
        for x in range(16):
            for y in range(16):
                b = int(pixels[x][y]) & 15 if pixels is not None else 0
                if b in (0, 1):
                    cor = self.CORES_DYE[0]
                elif b == 15:
                    cor = self.CORES_DYE[1]
                else:
                    cor = self.CORES_DYE[b]
                if sprite is not None and sprite.shape[1] >= 32:
                    base = sprite[y, x + (16 if b > 0 else 0), :3].astype(np.float32)
                else:
                    base = np.array((235, 235, 235) if b > 0 else (30, 32, 31), np.float32)
                img[y, x, :3] = np.clip(base * np.array(cor, np.float32) / 255.0, 0, 255).astype(np.uint8)
        tid = "@gen:bb%08x" % (zlib.crc32(img.tobytes()) & 0xFFFFFFFF)
        self._gen[tid] = img
        frente = props.get("facing", "north")
        chave = ("bb", nome, frente, tid)
        r = self._infos.get(chave)
        if r is not None:
            return r
        m = self._modelo_achatado("supplementaries:block/blackboard_frame")
        ry = {"north": 0, "east": 90, "south": 180, "west": 270}.get(frente, 0)
        tex = dict(m["texturas"])
        tex["2"] = tid
        elementos = copy.deepcopy(m["elementos"]) if m["elementos"] else []
        for el in elementos:
            for fc in (el.get("faces") or {}).values():
                if fc.get("texture") == "#2":
                    fc["uv"] = [0, 0, 16, 16]
        quads = self._quads(elementos, tex, 0, ry, False) if elementos else []
        if not quads:
            f, t = self._lado({"north": "south", "south": "north", "west": "east", "east": "west"}.get(frente, "south"), 5)
            faces = {n: {"texture": "#quadro"} for n in FACES}
            quads = self._quads([{"from": f, "to": t, "faces": faces}], {"quadro": tid}, 0, 0, False)
        r = self._analisar(nome, quads, None)
        r["fallback"] = None
        r["tid"] = tid
        self._infos[chave] = r
        return r

    @staticmethod
    def _lado(d, e):
        f, t = [0, 0, 0], [16, 16, 16]
        eixo, fim = {"north": (2, 0), "south": (2, 1), "west": (0, 0), "east": (0, 1), "down": (1, 0), "up": (1, 1)}.get(d, (2, 0))
        if fim:
            f[eixo] = 16 - e
        else:
            t[eixo] = e
        return f, t

    OPOSTA = {"north": "south", "south": "north", "west": "east", "east": "west", "up": "down", "down": "up"}

    def _caixas_copycat(self, nome, pr):
        tipo = nome.split(":", 1)[-1].replace("copycat_", "")
        facing = pr.get("facing", "north")
        meia = pr.get("half") or "bottom"
        alto = meia in ("top", "upper")
        try:
            n = max(1, min(8, int(pr.get("layers", 1))))
        except ValueError:
            n = 1
        cheio = ([0, 0, 0], [16, 16, 16])
        if tipo in ("slab",):
            ax = {"x": 0, "y": 1, "z": 2}.get(pr.get("axis", "y"), 1)
            tp = pr.get("type", "bottom")
            def metade(top):
                f, t = [0, 0, 0], [16, 16, 16]
                if top:
                    f[ax] = 8
                else:
                    t[ax] = 8
                return (f, t)
            if tp == "double":
                return [metade(False) + ("bottom",), metade(True) + ("top",)]
            return [metade(tp == "top") + (tp,)]
        if tipo == "layer":
            f, t = self._lado(self.OPOSTA.get(pr.get("facing", "up"), "down"), 2 * n)
            return [(f, t, None)]
        def canto(w, h, y0):
            xp = facing in ("south", "east")
            zp = facing in ("south", "west")
            fx = 16 - w if xp else 0
            fz = 16 - w if zp else 0
            return ([fx, y0, fz], [fx + w, y0 + h, fz + w])
        if tipo == "slice":
            f, t = self._lado(facing, 2 * n)
            f[1], t[1] = (16 - 2 * n, 16) if alto else (0, 2 * n)
            return [(f, t, None)]
        if tipo == "vertical_slice":
            f, t = canto(2 * n, 16, 0)
            return [(f, t, None)]
        if tipo == "corner_slice":
            f, t = canto(2 * n, 2 * n, 16 - 2 * n if alto else 0)
            return [(f, t, None)]
        if tipo == "vertical_step":
            f, t = canto(8, 16, 0)
            return [(f, t, None)]
        if tipo == "stacked_half_layer":
            caixas = []
            for chave, topo in (("negative_layers", False), ("positive_layers", True)):
                try:
                    k = int(pr.get(chave, 0))
                except ValueError:
                    k = 0
                if k > 0:
                    f, t = self._lado(facing, 2 * k)
                    f[1], t[1] = (8, 16) if topo else (0, 8)
                    caixas.append((f, t, chave))
            return caixas or [(*self._lado(facing, 2), None)]
        if tipo in ("stairs", "vertical_stairs"):
            costas = self.OPOSTA.get(facing, "south")
            f, t = self._lado(costas, 8)
            f[1], t[1] = (0, 8) if alto else (8, 16)
            base = ([0, 8, 0], [16, 16, 16]) if alto else ([0, 0, 0], [16, 8, 16])
            return [base + (None,), (f, t, None)]
        if tipo in ("step", "half_layer", "vertical_half_layer"):
            f, t = self._lado(facing, 8)
            f[1], t[1] = (8, 16) if alto else (0, 8)
            return [(f, t, None)]
        if tipo == "board":
            caixas = []
            for d in ("up", "down", "north", "south", "east", "west"):
                if str(pr.get(d, "false")) == "true":
                    f, t = self._lado(d, 1)
                    caixas.append((f, t, d))
            if not caixas:
                f, t = self._lado(facing, 1)
                caixas.append((f, t, facing))
            return caixas
        if tipo in ("panel", "half_panel", "door", "folding_door", "sliding_door", "iron_door", "stone_button",
                    "wooden_button", "flat_pane", "trapdoor", "iron_trapdoor"):
            if tipo == "panel" and nome.startswith("create:"):
                f, t = self._lado(self.OPOSTA.get(facing, "south"), 3)
                return [(f, t, None)]
            f, t = self._lado(facing, 1 if tipo == "panel" else 3)
            if tipo == "half_panel":
                f[1], t[1] = (8, 16) if alto else (0, 8)
            return [(f, t, None)]
        if tipo in ("beam", "shaft"):
            e = 8 if tipo == "beam" else 6
            a, b = 8 - e // 2, 8 + e // 2
            ax = pr.get("axis", "y")
            f, t = [a, a, a], [b, b, b]
            k = "xyz".index(ax) if ax in "xyz" else 1
            f[k], t[k] = 0, 16
            return [(f, t, None)]
        return [cheio + (None,)]

    def _caras_material(self, mat, mprops):
        minfo = self.info_bloco(mat, mprops)
        por_face = {n: [] for n in FACES}
        for tid, tint, cull, sombra, verts, uvs in minfo["quads"]:
            d = self._dir_quad(verts)
            if d in por_face:
                por_face[d].append((tid, tint))
        todas = [x for l in por_face.values() for x in l]
        if not todas:
            todas = [(q[0], q[1]) for q in minfo["quads"][:1]] or [("minecraft:missing", -1)]
        return por_face, todas

    def info_copycat(self, base, bprops, mats):
        chave = ("cc", base, tuple(sorted(bprops.items())), tuple(sorted((k, v[0], tuple(sorted(v[1].items()))) for k, v in mats.items())))
        r = self._infos.get(chave)
        if r is not None:
            return r
        principal = mats.get("") or next(iter(mats.values()))
        cache = {}
        def caras(part):
            m = mats.get(part) or principal
            k = (m[0], tuple(sorted(m[1].items())))
            if k not in cache:
                cache[k] = self._caras_material(m[0], m[1])
            return cache[k]
        quads = []
        for f, t, parte in self._caixas_copycat(base, bprops):
            por_face, todas = caras(parte)
            camadas = max(len(l) for l in por_face.values()) if any(por_face.values()) else 1
            for k in range(max(1, camadas)):
                faces, texs = {}, {}
                for n in FACES:
                    l = por_face[n] or ([] if any(por_face.values()) else todas)
                    if not l:
                        l = [todas[0]] if k == 0 else []
                    if k >= len(l):
                        continue
                    tid, tint = l[k]
                    texs[n] = tid
                    eixo = {"west": 0, "east": 0, "down": 1, "up": 1, "north": 2, "south": 2}[n]
                    borda = (f[eixo] <= 1e-4) if n in ("west", "down", "north") else (t[eixo] >= 16 - 1e-4)
                    faces[n] = {"texture": "#" + n, "tintindex": 0 if tint >= 0 else -1}
                    if borda:
                        faces[n]["cullface"] = n
                if faces:
                    quads += self._quads([{"from": f, "to": t, "faces": faces}], texs, 0, 0, False)
        r = self._analisar(principal[0], quads, None)
        r["fallback"] = None
        self._infos[chave] = r
        return r


    def overlays(self):
        self._carregar_ctm()
        return self._overlay

    def info_overlays(self, base, extras):
        regras = self.overlays()
        quads = list(base["quads"])
        tinta = base["tinta"]
        for ri, tiles in extras:
            r = regras[ri]
            for t in tiles:
                el = {"from": [0, 16.25, 0], "to": [16, 16.25, 16],
                      "faces": {"up": {"uv": [0, 0, 16, 16], "texture": "#t", "cullface": "up",
                                       "tintindex": 0 if r["tint"] else -1}}}
                quads += self._quads([el], {"t": r["tiles"][t]}, 0, 0, False)
            if r["tint"] and not tinta:
                tinta = 1
        info = dict(base)
        info["quads"], info["tinta"] = quads, tinta
        return info

    BUCKETS = 128

    @staticmethod
    def _dir_quad(verts):
        nx = ny = nz = 0.0
        for i in range(4):
            a, b = verts[i], verts[(i + 1) & 3]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        m = max(abs(nx), abs(ny), abs(nz))
        if m < 1e-6:
            return None
        if abs(nx) >= 0.99 * m and abs(ny) < 0.05 * m and abs(nz) < 0.05 * m:
            return "east" if nx > 0 else "west"
        if abs(ny) >= 0.99 * m and abs(nx) < 0.05 * m and abs(nz) < 0.05 * m:
            return "up" if ny > 0 else "down"
        if abs(nz) >= 0.99 * m and abs(nx) < 0.05 * m and abs(ny) < 0.05 * m:
            return "south" if nz > 0 else "north"
        return None

    @staticmethod
    def _nome_tile(t):
        t = t.strip()
        if t.endswith(".png"):
            t = t[:-4]
        ns = "minecraft"
        if ":" in t:
            ns, t = t.split(":", 1)
        if "/" not in t:
            t = "block/" + t
        return "%s:%s" % (ns, t)

    def _carregar_ctm(self):
        if getattr(self, "_ctm", None) is not None:
            return self._ctm
        regras, ign, overlays = [], Counter(), []
        props_arqs = sorted(n for n in self.indice
                            if n.endswith(".properties") and ("/optifine/ctm/" in n or "/mcpatcher/ctm/" in n))
        for n in props_arqs:
            dados = self.ler(n)
            if dados is None:
                continue
            kv = {}
            for ln in dados.decode("utf-8", "replace").splitlines():
                ln = ln.strip()
                if not ln or ln[0] in "#!" or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                kv[k.strip().lower()] = v.strip()
            metodo = kv.get("method", "ctm").lower()
            if metodo not in ("random", "fixed", "overlay"):
                ign[metodo] += 1
                continue
            pasta = n.rsplit("/", 1)[0]
            tiles = []
            for tok in kv.get("tiles", "").split():
                m = re.fullmatch(r"(\d+)-(\d+)", tok)
                if m:
                    alvo = [str(i) for i in range(int(m.group(1)), int(m.group(2)) + 1)]
                else:
                    alvo = [tok]
                for a in alvo:
                    a = a[:-4] if a.endswith(".png") else a
                    cands = []
                    if a.startswith("assets/"):
                        cands.append(a)
                    elif ":" in a:
                        ns, pp = a.split(":", 1)
                        cands += ["assets/%s/%s" % (ns, pp), "assets/%s/textures/%s" % (ns, pp)]
                    elif a.startswith("~/"):
                        cands.append("assets/minecraft/optifine/" + a[2:])
                    else:
                        cands += [pasta + "/" + a.lstrip("./"), "assets/minecraft/textures/" + a,
                                  "assets/minecraft/textures/block/" + a]
                    achou = next((c for c in cands if (c + ".png") in self.indice), None)
                    tiles.append("@" + achou if achou else None)
            if not tiles or any(t is None for t in tiles):
                ign["tiles-ausentes"] += 1
                continue
            pesos = [max(1, int(x)) for x in re.findall(r"\d+", kv.get("weights", ""))]
            if len(pesos) != len(tiles):
                pesos = [1] * len(tiles)
            fc = set()
            for f in kv.get("faces", "all").lower().replace(",", " ").split():
                if f == "all":
                    fc |= set(FACES)
                elif f == "sides":
                    fc |= {"north", "south", "east", "west"}
                elif f in ("top", "bottom"):
                    fc.add("up" if f == "top" else "down")
                elif f in FACES:
                    fc.add(f)
            blocos = []
            for tok in kv.get("matchblocks", "").split():
                partes = tok.split(":")
                if len(partes) >= 2 and "=" not in partes[1]:
                    nome, resto = partes[0] + ":" + partes[1], partes[2:]
                else:
                    nome, resto = "minecraft:" + partes[0], partes[1:]
                blocos.append((nome, dict(r.split("=", 1) for r in resto if "=" in r)))
            tiles_alvo = {self._nome_tile(t) for t in kv.get("matchtiles", "").split()}
            if not blocos and not tiles_alvo:
                tiles_alvo = {self._nome_tile(os.path.basename(n)[:-11])}
            try:
                prio = int(kv.get("weight", "0"))
            except ValueError:
                prio = 0
            if metodo == "overlay":
                def nomes(txt):
                    out = set()
                    for tok in txt.split():
                        pt = tok.split(":")
                        out.add(pt[0] + ":" + pt[1] if len(pt) >= 2 and "=" not in pt[1] else "minecraft:" + pt[0])
                    return out
                alvo = {b[0] for b in blocos}
                conn = nomes(kv.get("connectblocks", ""))
                if len(tiles) < 17 or not alvo or not conn or "up" not in (fc or {"up"}):
                    ign["overlay (formato não suportado)"] += 1
                    continue
                try:
                    prio_o = int(kv.get("weight", "0"))
                except ValueError:
                    prio_o = 0
                overlays.append({"tiles": tiles[:17], "alvo": alvo, "conn": conn,
                                 "tint": "tintindex" in kv, "prio": prio_o, "arq": n})
                continue
            regras.append({"metodo": metodo, "tiles": tiles, "pesos": pesos, "faces": fc or set(FACES),
                           "blocos": blocos, "alvo": tiles_alvo, "prio": prio, "arq": n})
        regras.sort(key=lambda r: -r["prio"])
        overlays.sort(key=lambda r: r["prio"])
        self._ctm = regras
        self._overlay = overlays
        self.ctm_ignorados = ign
        return regras

    def _regra_para(self, nome, props, tid, face):
        for r in self._carregar_ctm():
            if face is not None and face not in r["faces"]:
                continue
            if r["blocos"] and not any(b == nome and all(props.get(k) == v for k, v in pr.items()) for b, pr in r["blocos"]):
                continue
            if r["alvo"] and tid not in r["alvo"]:
                continue
            return r
        return None

    def _ctm_quads(self, nome, props, quads, bucket):
        if not self._carregar_ctm():
            return quads, False
        novos, usou = [], False
        for q in quads:
            tid, tint, cull, sombra, verts, uvs = q
            face = self._dir_quad(verts)
            r = self._regra_para(nome, props, tid, face) if not tid.startswith(("cor:", "@")) else None
            if r is None:
                novos.append(q)
                continue
            usou = True
            if bucket is None:
                novos.append(q)
                continue
            if r["metodo"] == "fixed":
                i = 0
            else:
                tot, pos = sum(r["pesos"]), (bucket + 0.5) / self.BUCKETS
                acum, i = 0, len(r["tiles"]) - 1
                for k, w in enumerate(r["pesos"]):
                    acum += w
                    if pos * tot < acum:
                        i = k
                        break
            novos.append((r["tiles"][i], tint, cull, sombra, verts, uvs))
        return novos, usou

    def info_bloco(self, nome, props, bucket=None):
        chave = (nome, tuple(sorted(props.items())), bucket)
        r = self._infos.get(chave)
        if r is not None:
            return r
        quads, fallback, alea = None, None, False
        if nome in ("minecraft:water", "minecraft:lava"):
            quads = self._quads_fluido(nome)
        else:
            vars_ = self._variantes(nome, props, bucket)
            alea = self._alea
            if vars_:
                quads = []
                for ref, rx, ry, uvl in vars_:
                    m = self._modelo_achatado(ref)
                    if m["elementos"]:
                        quads += self._quads(m["elementos"], m["texturas"], rx, ry, uvl)
                if not quads:
                    quads = None
                    fallback = "modelo especial, sem geometria no arquivo (carregador do mod, baú, cama...)"
                    m = self._modelo_achatado(vars_[0][0])
                    tid = self._tex_ref(m["texturas"], "#particle")
                    if tid is None:
                        for v in m["texturas"].values():
                            tid = self._tex_ref(m["texturas"], v)
                            if tid:
                                break
                    if tid:
                        quads = self._quads_cubo(nome, tid)
            else:
                fallback = "sem blockstate nos jars (mod sem assets ou não indicado)"
            if quads is None:
                h = cor_do_bloco(nome)
                quads = self._quads_cubo(nome, "cor:%02x%02x%02x" % h)
        quads, usa_ctm = self._ctm_quads(nome, props, quads, bucket)
        if self.folhas_opacas and "leaves" in nome:
            quads = [self._face_opaca(q) for q in quads]
        r = self._analisar(nome, quads, fallback)
        r["ctm"] = usa_ctm or alea
        r["fallback"] = fallback
        self._infos[chave] = r
        return r

    @staticmethod
    def _face_opaca(q):
        tid, tint, cull, sombra, verts, uvs = q
        if tid.startswith("cor:") or tid.endswith("#opaca"):
            return q
        for eixo in range(3):
            c = [v[eixo] for v in verts]
            if all(abs(x) < 1e-4 for x in c) or all(abs(x - 16) < 1e-4 for x in c):
                o = [k for k in range(3) if k != eixo]
                if all(min(v[k] for v in verts) < 1e-4 and max(v[k] for v in verts) > 16 - 1e-4 for k in o):
                    return (tid + "#opaca", tint, cull, sombra, verts, uvs)
        return q

    def _analisar(self, nome, quads, fallback):
        geom = [False] * 6
        opaco_d = [False] * 6
        translucido = False
        for tid, tint, cull, sombra, verts, uvs in quads:
            opaca, parcial = self._alfa(tid)
            if parcial:
                translucido = True
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            zs = [v[2] for v in verts]
            for d, (eixo, valor) in enumerate(((ys, 0), (ys, 16), (zs, 0), (zs, 16), (xs, 0), (xs, 16))):
                if all(abs(e - valor) < 1e-4 for e in eixo):
                    outros = [(xs, zs), (xs, zs), (xs, ys), (xs, ys), (zs, ys), (zs, ys)][d]
                    if all(min(o) < 1e-4 and max(o) > 16 - 1e-4 for o in outros):
                        geom[d] = True
                        if opaca:
                            opaco_d[d] = True
        cubo = all(geom)
        opaco = all(opaco_d)
        if fallback and not self.tem_fontes_para(nome):
            opaco = not e_transparente(nome)
        flags = 0
        if opaco:
            flags |= F_OPACO
        else:
            flags |= F_TRANSP
            if cubo:
                flags |= F_CULLSAME
        agua = nome == "minecraft:water"
        if translucido or agua:
            flags |= F_TRANSLUC
        if agua:
            flags |= F_AGUA
        if nome in ("minecraft:water", "minecraft:lava"):
            flags |= F_CULLSAME
        return {"quads": quads, "flags": flags, "tinta": self._tinta(nome, quads), "opaco": opaco}

    def tem_fontes_para(self, nome):
        return self.blockstate(nome) is not None

    @staticmethod
    def _tinta(nome, quads):
        caminho = nome.split(":", 1)[-1]
        if nome == "minecraft:water":
            return 3
        if not any(q[1] >= 0 for q in quads):
            return 0
        if "spruce_leaves" in caminho:
            return 4
        if "birch_leaves" in caminho:
            return 5
        if "lily_pad" in caminho:
            return 6
        if "leaves" in caminho or "vine" in caminho:
            return 2
        return 1


def versao_do_mundo(pasta_mundo):
    try:
        with gzip.open(os.path.join(pasta_mundo, "level.dat")) as f:
            nbt = ler_nbt(f.read())
        return nbt["Data"]["Version"]["Name"]
    except Exception:
        return None


def _bases_acima(pasta_mundo, n=7):
    atual = os.path.abspath(pasta_mundo)
    bases = []
    for _ in range(n):
        atual = os.path.dirname(atual)
        bases += [atual, os.path.join(atual, ".minecraft"), os.path.join(atual, "minecraft"),
                  os.path.join(atual, "Install")]
    return bases


def achar_jar_minecraft(pasta_mundo, versao=None):
    versao = versao or versao_do_mundo(pasta_mundo) or "1.20.1"
    home = os.path.expanduser("~")
    bases = []
    if os.environ.get("APPDATA"):
        bases.append(os.path.join(os.environ["APPDATA"], ".minecraft"))
    bases += [os.path.join(home, ".minecraft"),
              os.path.join(home, "Library", "Application Support", "minecraft")]
    bases += _bases_acima(pasta_mundo)
    for b in bases:
        for c in (os.path.join(b, "versions", versao, versao + ".jar"),
                  os.path.join(b, "libraries", "com", "mojang", "minecraft", versao,
                               "minecraft-%s-client.jar" % versao)):
            if os.path.isfile(c):
                return c
    return None


def achar_pasta_mods(pasta_mundo):
    m = os.path.abspath(pasta_mundo)
    cand = [os.path.join(m, "mods"), os.path.join(os.path.dirname(m), "mods"),
            os.path.join(os.path.dirname(os.path.dirname(m)), "mods")]
    for b in _bases_acima(pasta_mundo, 4):
        cand.append(os.path.join(b, "mods"))
    for c in cand:
        if os.path.isdir(c):
            return c
    return None


def png_rgba(arr):
    try:
        from PIL import Image
        b = io.BytesIO()
        Image.fromarray(arr).save(b, "PNG", optimize=True)
        return b.getvalue()
    except ImportError:
        h, w = arr.shape[:2]
        raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _pot2(n, minimo=16):
    p = minimo
    while p < n:
        p *= 2
    return p


def _redimensionar(a, th, tw):
    h, w = a.shape[:2]
    if (h, w) == (th, tw):
        return a
    if w >= tw and h >= th and w % tw == 0 and h % th == 0:
        fy, fx = h // th, w // tw
        return a.reshape(th, fy, tw, fx, 4).astype(np.float32).mean(axis=(1, 3)).round().astype(np.uint8)
    iy = (np.arange(th) * h // th)
    ix = (np.arange(tw) * w // tw)
    return a[iy][:, ix]


def montar_atlas(recursos, tids, tile_max=256, animar=None):
    arrs, falhas = [], []
    for t in tids:
        a = recursos.textura(t)
        if a is None:
            falhas.append(t)
            a = recursos.textura("minecraft:missing")
        arrs.append(a)
    if not arrs:
        arrs = [recursos.textura("minecraft:missing")]
    if animar is None:
        animar = getattr(recursos, "animar", True)
    anims, extra_de = [], []
    if animar:
        for i, t in enumerate(tids):
            an = recursos.animacao(t) if hasattr(recursos, "animacao") else None
            if not an:
                continue
            seq = an["seq"]
            quad_idx = {}
            primeiro = seq[0][0]
            quad_idx[primeiro] = i
            for k in sorted(an["quadros"]):
                if k not in quad_idx:
                    quad_idx[k] = len(arrs)
                    arrs.append(an["quadros"][k])
                    extra_de.append(i)
            from math import gcd
            g = 0
            for _, tk in seq:
                g = gcd(g, tk)
            passos = []
            for k, tk in seq:
                passos += [quad_idx[k]] * (tk // g)
            if passos:
                anims.append({"tx": i, "dt": g, "f": passos})
    AW, AH_MAX = 4096, 8192
    cap = max(16, tile_max)
    capx = cap
    while True:
        tam = [(_pot2(min(a.shape[0], cap)), _pot2(min(a.shape[1], cap))) for a in arrs]
        for k, i0 in enumerate(extra_de):
            tam[len(tids) + k] = (min(tam[i0][0], capx), min(tam[i0][1], capx))
        ordem = sorted(range(len(arrs)), key=lambda i: (-tam[i][0], -tam[i][1]))
        rects = [None] * len(arrs)
        x = y = lin_h = 0
        for i in ordem:
            th, tw = tam[i]
            if x + tw > AW:
                x, y, lin_h = 0, y + lin_h, 0
            if x == 0:
                lin_h = th
            rects[i] = [x, y, tw, th]
            x += tw
        altura = y + lin_h
        if altura <= AH_MAX or (cap <= 16 and capx <= 16):
            break
        if capx > 16 and extra_de:
            capx //= 2
        else:
            cap //= 2
    altura = -(-max(altura, 16) // 16) * 16
    atlas = np.zeros((altura, AW, 4), np.uint8)
    for i, a in enumerate(arrs):
        x0, y0, tw, th = rects[i]
        atlas[y0:y0 + th, x0:x0 + tw] = _redimensionar(a, th, tw)
    info = {"tile": 16, "rects": rects, "n": len(tids), "largura": AW, "altura": altura}
    if anims:
        info["anim"] = anims
    return png_rgba(atlas), info, falhas


class Paleta:

    def __init__(self, guardar_estados=True, recursos=None):
        self.chaves = ["minecraft:air"]
        self.transp = [True]
        self.infos = [None]
        self.partes = [None]
        self.diag = {"be": Counter(), "amostra": {}, "cc_ok": 0, "cc_sem": 0, "quadros": 0, "erros": []}
        self._var = {}
        self.sobre = {}
        self.pai_var = {}
        self._lut_ov = {}
        self.indice = {}
        self.guardar = guardar_estados
        self.recursos = recursos if recursos is not None else Recursos()

    def _props(self, nome, entrada):
        pr = entrada.get("Properties")
        if not pr or not self.guardar:
            return {}
        if "copycat" in nome or nome.endswith(":blackboard"):
            return {k: str(pr[k]) for k in sorted(pr)}
        rel = self.recursos.props_relevantes(nome) if self.recursos.tem_fontes else PROPS_VISUAIS
        return {k: pr[k] for k in sorted(pr) if k in rel}

    def id_de(self, entrada):
        nome = entrada["Name"]
        if nome in AR:
            return 0
        props = self._props(nome, entrada)
        k = nome + ("[" + ",".join("%s=%s" % kv for kv in props.items()) + "]" if props else "")
        i = self.indice.get(k)
        if i is None:
            i = len(self.chaves)
            if i >= 65534:
                raise ValueError("Tipos de bloco demais para o formato (limite 65534).")
            info = self.recursos.info_bloco(nome, props)
            self.chaves.append(k)
            self.infos.append(info)
            self.partes.append((nome, props))
            self.transp.append(not info["opaco"])
            self.indice[k] = i
        return i

    def variantes(self, base_id):
        if base_id in self._var:
            return self._var[base_id]
        res = None
        info = self.infos[base_id]
        if info and info.get("ctm") and self.partes[base_id]:
            nome, props = self.partes[base_id]
            ids, vistos = [], {}
            for b in range(Recursos.BUCKETS):
                inf = self.recursos.info_bloco(nome, props, b)
                assinatura = tuple((q[0], q[1], q[2]) for q in inf["quads"])
                i = vistos.get(assinatura)
                if i is None:
                    if len(self.chaves) >= 65534:
                        i = base_id
                    else:
                        i = len(self.chaves)
                        self.chaves.append("%s~v%d" % (self.chaves[base_id], b))
                        self.infos.append(inf)
                        self.partes.append(None)
                        self.transp.append(not inf["opaco"])
                        self.pai_var[i] = base_id
                    vistos[assinatura] = i
                ids.append(i)
            res = ids if len(set(ids)) > 1 else None
        self._var[base_id] = res
        return res

    def nome_de(self, i):
        while i in self.sobre:
            i = self.sobre[i][0]
        while self.partes[i] is None and i in self.pai_var:
            i = self.pai_var[i]
        p = self.partes[i]
        return p[0] if p else None

    def lut_overlay(self, ri):
        regra = self.recursos.overlays()[ri]
        a, c = self._lut_ov.get(ri, (np.zeros(0, bool), np.zeros(0, bool)))
        n = len(self.chaves) + 1
        if len(a) < n:
            a2, c2 = np.zeros(n, bool), np.zeros(n, bool)
            a2[:len(a)], c2[:len(c)] = a, c
            for i in range(max(len(a), 1), n - 1):
                nm = self.nome_de(i)
                a2[i] = nm in regra["alvo"]
                c2[i] = nm in regra["conn"]
            a, c = a2, c2
            self._lut_ov[ri] = (a, c)
        return a, c

    def id_overlay(self, base_id, ri, tiles):
        raiz, extras = self.sobre.get(base_id, (base_id, ()))
        extras = extras + ((ri, tiles),)
        k = "%s+ov:%s" % (self.chaves[raiz], ";".join("%d:%s" % (r, "-".join(map(str, t))) for r, t in extras))
        i = self.indice.get(k)
        if i is None:
            if len(self.chaves) >= 65534 or self.infos[raiz] is None:
                return base_id
            info = self.recursos.info_overlays(self.infos[raiz], extras)
            i = len(self.chaves)
            self.chaves.append(k)
            self.infos.append(info)
            self.partes.append(None)
            self.transp.append(not info["opaco"])
            self.indice[k] = i
            self.sobre[i] = (raiz, extras)
        return i

    def id_quadro(self, base_id, pixels):
        if not self.partes[base_id]:
            return base_id
        nome_b, props_b = self.partes[base_id]
        info = self.recursos.info_quadro(nome_b, props_b, pixels)
        k = "%s|%s" % (self.chaves[base_id], info["tid"])
        i = self.indice.get(k)
        if i is None:
            i = len(self.chaves)
            if i >= 65534:
                return base_id
            self.chaves.append(k)
            self.infos.append(info)
            self.partes.append(None)
            self.transp.append(not info["opaco"])
            self.indice[k] = i
        return i

    def id_material(self, base_id, mats):
        if not self.partes[base_id] or not mats:
            return base_id
        nome_b, props_b = self.partes[base_id]
        limpos = {}
        for parte, m in mats.items():
            nome_m = m.get("Name")
            if not isinstance(nome_m, str) or nome_m in AR:
                continue
            pr = m.get("Properties") or {}
            limpos[parte] = (nome_m, self._props(nome_m, {"Properties": pr}) if pr else {})
        if not limpos:
            return base_id
        k = "%s|%s" % (self.chaves[base_id], ";".join(
            "%s=%s%s" % (p, v[0], "[" + ",".join("%s=%s" % kv for kv in v[1].items()) + "]" if v[1] else "")
            for p, v in sorted(limpos.items())))
        i = self.indice.get(k)
        if i is None:
            i = len(self.chaves)
            if i >= 65534:
                return base_id
            info = self.recursos.info_copycat(nome_b, props_b, limpos)
            self.chaves.append(k)
            self.infos.append(info)
            self.partes.append(None)
            self.transp.append(not info["opaco"])
            self.indice[k] = i
        return i


def desempacotar(dados, bits, quantidade):
    vpl = 64 // bits
    mask = np.uint64((1 << bits) - 1)
    d = np.asarray(dados, dtype=np.uint64)
    out = np.empty(len(d) * vpl, dtype=np.uint64)
    for k in range(vpl):
        out[k::vpl] = (d >> np.uint64(k * bits)) & mask
    return out[:quantidade]


def decodificar_secao(sec):
    bs = sec.get("block_states")
    if not bs:
        return None
    paleta = bs.get("palette") or []
    n = len(paleta)
    if n == 0:
        return None
    dados = bs.get("data")
    if dados is None or n == 1:
        return np.zeros(4096, np.uint16), paleta
    bits = max(4, (n - 1).bit_length())
    return desempacotar(dados, bits, 4096).astype(np.uint16), paleta


def chunk_completo(nbt):
    if nbt is None or "sections" not in nbt:
        return False
    st = nbt.get("Status", "")
    return (not st) or ("full" in st)


def decodificar_chunk(nbt, pal, ymin, ymax, cx, cz, x1, x2, z1, z2):
    H = ymax - ymin + 1
    arr = np.zeros((H, 16, 16), np.uint16)
    if not chunk_completo(nbt):
        return arr
    for sec in nbt["sections"]:
        base = int(sec["Y"]) * 16
        if base + 15 < ymin or base > ymax:
            continue
        res = decodificar_secao(sec)
        if res is None:
            continue
        idx, paleta_sec = res
        mapa = np.array([pal.id_de(e) for e in paleta_sec], np.uint16)
        blocos = mapa[idx].reshape(16, 16, 16)
        y0 = max(base, ymin)
        y1 = min(base + 15, ymax)
        arr[y0 - ymin:y1 - ymin + 1] = blocos[y0 - base:y1 - base + 1]
    for be in (nbt.get("block_entities") or []):
        try:
            if not isinstance(be, dict) or "x" not in be:
                continue
            bx, by, bz = int(be["x"]), int(be["y"]), int(be["z"])
            if not (x1 <= bx <= x2 and z1 <= bz <= z2 and ymin <= by <= ymax):
                continue
            bid = str(be.get("id", "?"))
            dg = pal.diag
            dg["be"][bid] += 1
            if bid not in dg["amostra"]:
                dg["amostra"][bid] = sorted(k for k in be if k not in ("x", "y", "z", "id", "keepPacked"))
            ly, lz, lx = by - ymin, bz - cz * 16, bx - cx * 16
            base = int(arr[ly, lz, lx])
            if not base or not pal.partes[base]:
                continue
            nome_b = pal.partes[base][0]
            if nome_b.endswith(":blackboard"):
                pix = None
                for k, v in be.items():
                    if isinstance(v, np.ndarray) and v.dtype == np.uint64 and len(v) == 16 and "pixel" in k.lower():
                        pix = [[(int(v[r]) >> (4 * c)) & 15 for c in range(16)] for r in range(16)]
                    elif isinstance(v, (bytes, bytearray)) and len(v) == 256 and "pixel" in k.lower():
                        pix = [[v[r * 16 + c] & 15 for c in range(16)] for r in range(16)]
                arr[ly, lz, lx] = pal.id_quadro(base, pix)
                dg["quadros"] += 1
                continue
            mats = {}
            m1 = be.get("Material")
            if isinstance(m1, dict) and isinstance(m1.get("Name"), str):
                mats[""] = m1
            md = be.get("material_data")
            if isinstance(md, dict):
                for chave_parte, item in md.items():
                    if isinstance(item, dict) and isinstance(item.get("material"), dict):
                        mats[str(chave_parte)] = item["material"]
            if not mats:
                for k, v in be.items():
                    if isinstance(v, dict) and isinstance(v.get("Name"), str) and ":" in v["Name"]:
                        mats[""] = v
                        break
            if mats:
                novo = pal.id_material(base, mats)
                arr[ly, lz, lx] = novo
                dg["cc_ok"] += 1 if novo != base else 0
            elif "copycat" in nome_b:
                dg["cc_sem"] += 1
        except Exception as e:
            if len(pal.diag["erros"]) < 8:
                pal.diag["erros"].append("%s: %s" % (type(e).__name__, e))
            continue
    if pal.recursos.tem_fontes:
        usados = np.unique(arr)
        for base in usados:
            base = int(base)
            if base == 0:
                continue
            var = pal.variantes(base)
            if not var:
                continue
            m = arr == base
            yy, zz, xx = np.nonzero(m)
            gx = (xx + cx * 16).astype(np.uint64)
            gy = (yy + ymin).astype(np.int64).astype(np.uint64)
            gz = (zz + cz * 16).astype(np.uint64)
            h = (gx * np.uint64(73856093)) ^ (gy * np.uint64(19349663)) ^ (gz * np.uint64(83492791))
            h ^= h >> np.uint64(13)
            h *= np.uint64(0x9E3779B1)
            h ^= h >> np.uint64(15)
            bk = (h % np.uint64(Recursos.BUCKETS)).astype(np.int64)
            arr[yy, zz, xx] = np.array(var, np.uint16)[bk]
    xs = np.arange(16) + cx * 16
    zs = np.arange(16) + cz * 16
    arr[:, :, ~((xs >= x1) & (xs <= x2))] = 0
    arr[:, ~((zs >= z1) & (zs <= z2)), :] = 0
    return arr


_DIRS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


_OV_BORDAS = {
    (1, 0, 0, 0): (15,), (0, 1, 0, 0): (1,), (0, 0, 1, 0): (9,), (0, 0, 0, 1): (7,),
    (0, 1, 0, 1): (3,), (0, 1, 1, 0): (4,), (1, 0, 0, 1): (10,), (1, 0, 1, 0): (11,),
    (0, 0, 1, 1): (9, 7), (1, 1, 0, 0): (15, 1),
    (0, 1, 1, 1): (5,), (1, 1, 1, 0): (6,), (1, 1, 0, 1): (12,), (1, 0, 1, 1): (13,),
    (1, 1, 1, 1): (8,),
}


def _tiles_overlay(n, s_, w, e, nw, ne, sw, se):
    t = list(_OV_BORDAS.get((n, s_, w, e), ()))
    if se and not s_ and not e:
        t.append(0)
    if sw and not s_ and not w:
        t.append(2)
    if ne and not n and not e:
        t.append(14)
    if nw and not n and not w:
        t.append(16)
    return tuple(sorted(t))


def aplicar_overlays(pal, C, viz):
    regras = pal.recursos.overlays() if pal.recursos.tem_fontes else []
    if not regras:
        return
    H = C.shape[0]
    tr = np.array(list(pal.transp) + [True], dtype=bool)
    acima = np.zeros_like(C)
    acima[:-1] = C[1:]
    yy, zz, xx = np.nonzero((C > 0) & tr[acima])
    if not len(yy):
        return
    P = np.zeros((H + 1, 18, 18), np.uint16)
    P[:H, 1:17, 1:17] = C
    for (dx, dz), A in viz.items():
        if A is None:
            continue
        zs = slice(1, 17) if dz == 0 else (slice(0, 1) if dz < 0 else slice(17, 18))
        xs = slice(1, 17) if dx == 0 else (slice(0, 1) if dx < 0 else slice(17, 18))
        za = slice(0, 16) if dz == 0 else (slice(15, 16) if dz < 0 else slice(0, 1))
        xa = slice(0, 16) if dx == 0 else (slice(15, 16) if dx < 0 else slice(0, 1))
        P[:H, zs, xs] = A[:, za, xa]
    atuais = C[yy, zz, xx].astype(np.int64)
    for ri in range(len(regras)):
        tr = np.array(list(pal.transp) + [True], dtype=bool)
        alvo, conn = pal.lut_overlay(ri)
        pos = alvo[atuais]
        if not pos.any():
            continue
        y, z, x = yy[pos], zz[pos], xx[pos]

        def vizinho(dz, dx):
            ids = P[y, z + 1 + dz, x + 1 + dx]
            topo = P[y + 1, z + 1 + dz, x + 1 + dx]
            return conn[ids] & tr[topo]
        n, s_, w, e = vizinho(-1, 0), vizinho(1, 0), vizinho(0, -1), vizinho(0, 1)
        nw, ne, sw, se = vizinho(-1, -1), vizinho(-1, 1), vizinho(1, -1), vizinho(1, 1)
        cod = (n * 1 + s_ * 2 + w * 4 + e * 8 + nw * 16 + ne * 32 + sw * 64 + se * 128).astype(np.int64)
        tem = cod > 0
        if not tem.any():
            continue
        idx = np.nonzero(pos)[0][tem]
        chave = atuais[idx] * 256 + cod[tem]
        for k in np.unique(chave):
            b, c = int(k) // 256, int(k) % 256
            t = _tiles_overlay(c & 1, (c >> 1) & 1, (c >> 2) & 1, (c >> 3) & 1,
                               (c >> 4) & 1, (c >> 5) & 1, (c >> 6) & 1, (c >> 7) & 1)
            if not t:
                continue
            novo = pal.id_overlay(b, ri, t)
            if novo != b:
                sel = idx[chave == k]
                atuais[sel] = novo
    C[yy, zz, xx] = atuais.astype(np.uint16)


def cortar_casca(C, oeste, leste, norte, sul, tr_lista):
    H = C.shape[0]
    sentinela = len(tr_lista)
    tr = np.array(list(tr_lista) + [False], dtype=bool)
    P = np.zeros((H + 2, 18, 18), np.uint16)
    P[0, :, :] = sentinela
    P[1:H + 1, 1:17, 1:17] = C
    if oeste is not None:
        P[1:H + 1, 1:17, 0] = oeste[:, :, 15]
    if leste is not None:
        P[1:H + 1, 1:17, 17] = leste[:, :, 0]
    if norte is not None:
        P[1:H + 1, 0, 1:17] = norte[:, 15, :]
    if sul is not None:
        P[1:H + 1, 17, 1:17] = sul[:, 0, :]
    vis = np.zeros(C.shape, bool)
    for dy, dz, dx in _DIRS:
        V = P[1 + dy:H + 1 + dy, 1 + dz:17 + dz, 1 + dx:17 + dx]
        vis |= tr[V] & (V != C)
    vis &= (C != 0)
    return np.where(vis, C, 0).astype(np.uint16)


def codificar_colunas(V):
    H = V.shape[0]
    cols = V.transpose(1, 2, 0).reshape(256, H)
    nz = cols != 0
    ant = np.zeros_like(cols)
    ant[:, 1:] = cols[:, :-1]
    prox = np.zeros_like(cols)
    prox[:, :-1] = cols[:, 1:]
    ci, yi = np.nonzero(nz & (cols != ant))
    _, ye = np.nonzero(nz & (cols != prox))
    ids = cols[ci, yi]
    comp = (ye - yi + 1).astype(np.int64)
    yi = yi.astype(np.int64)
    if len(comp) and comp.max() > 255:
        pecas = (comp + 254) // 255
        total = int(pecas.sum())
        ini = np.cumsum(pecas) - pecas
        off = np.arange(total) - np.repeat(ini, pecas)
        ci = np.repeat(ci, pecas)
        ids = np.repeat(ids, pecas)
        yi = np.repeat(yi, pecas) + off * 255
        comp = np.minimum(255, np.repeat(comp, pecas) - off * 255)
    fim = yi + comp
    ant_fim = np.roll(fim, 1)
    mesma = np.zeros(len(ci), bool)
    if len(ci) > 1:
        mesma[1:] = ci[1:] == ci[:-1]
    vazios = yi - np.where(mesma, ant_fim, 0)
    contagens = np.bincount(ci, minlength=256).astype(np.uint16)
    return (contagens, vazios.astype(np.uint16), comp.astype(np.uint8),
            ids.astype(np.uint16))


def _num(v):
    v = round(float(v), 3)
    return int(v) if v == int(v) else v


def escanear(pasta_regioes, x1, z1, x2, z2, ymin, ymax, saida,
             guardar_estados=True, dimensao="Overworld",
             progresso=None, cancelar=None, recursos=None, tile_max=256):
    if recursos is None:
        recursos = Recursos()
    if x1 > x2:
        x1, x2 = x2, x1
    if z1 > z2:
        z1, z2 = z2, z1
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    H = ymax - ymin + 1
    regs = PastaRegioes(pasta_regioes)
    pal = Paleta(guardar_estados, recursos)
    cx0, cx1, cz0, cz1 = x1 >> 4, x2 >> 4, z1 >> 4, z2 >> 4
    ncx, ncz = cx1 - cx0 + 1, cz1 - cz0 + 1
    total = ncx * ncz
    cache = {}

    def pegar(cx, cz):
        if not (cx0 <= cx <= cx1 and cz0 <= cz <= cz1):
            return None
        k = (cx, cz)
        if k not in cache:
            nbt = regs.chunk(cx, cz)
            cache[k] = decodificar_chunk(nbt, pal, ymin, ymax, cx, cz, x1, x2, z1, z2)
        return cache[k]

    L_cont, L_vaz, L_comp, L_ids = [], [], [], []
    feito = 0
    for cz in range(cz0, cz1 + 1):
        for cx in range(cx0, cx1 + 1):
            if cancelar is not None and cancelar.is_set():
                raise Cancelado()
            C = pegar(cx, cz)
            if C.any():
                if recursos.tem_fontes:
                    aplicar_overlays(pal, C, {(dx, dz): pegar(cx + dx, cz + dz)
                                              for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz})
                V = cortar_casca(C, pegar(cx - 1, cz), pegar(cx + 1, cz),
                                 pegar(cx, cz - 1), pegar(cx, cz + 1), pal.transp)
                c, v, l, i = codificar_colunas(V)
            else:
                c = np.zeros(256, np.uint16)
                v = np.zeros(0, np.uint16)
                l = np.zeros(0, np.uint8)
                i = np.zeros(0, np.uint16)
            L_cont.append(c)
            L_vaz.append(v)
            L_comp.append(l)
            L_ids.append(i)
            feito += 1
            if progresso is not None and (feito % 4 == 0 or feito == total):
                progresso(feito, total, "Escaneando chunks (%d de %d)" % (feito, total))
        for k in [k for k in cache if k[1] < cz]:
            del cache[k]

    contagens = np.concatenate(L_cont)
    vazios = np.concatenate(L_vaz) if L_vaz else np.zeros(0, np.uint16)
    comps = np.concatenate(L_comp) if L_comp else np.zeros(0, np.uint8)
    ids = np.concatenate(L_ids) if L_ids else np.zeros(0, np.uint16)
    n_cols, n_runs = len(contagens), len(ids)

    if progresso is not None:
        progresso(total, total, "Montando modelos e texturas")
    usados = np.unique(ids)
    contagem_ids = np.bincount(ids, weights=comps.astype(np.int64), minlength=len(pal.chaves) + 1)
    lut = np.zeros(len(pal.chaves) + 1, np.uint16)
    lut[usados] = np.arange(1, len(usados) + 1, dtype=np.uint16)
    ids = lut[ids]
    tix, modelos, chave_modelo = {}, [], {}
    entradas = [{"n": "minecraft:air", "m": -1, "f": F_TRANSP, "t": 0}]
    for velho in usados:
        info = pal.infos[int(velho)]
        qs = []
        for tid, tint, cull, sombra, verts, uvs in info["quads"]:
            t = tix.setdefault(tid, len(tix))
            linha = [t, tint, cull, sombra]
            for v in verts:
                linha += [_num(c) for c in v]
            for u, vv in uvs:
                linha += [_num(u), _num(vv)]
            qs.append(linha)
        js = json.dumps(qs, separators=(",", ":"))
        m = chave_modelo.get(js)
        if m is None:
            m = len(modelos)
            chave_modelo[js] = m
            modelos.append(qs)
        entradas.append({"n": pal.chaves[int(velho)], "m": m, "f": info["flags"], "t": info["tinta"]})
    png, info_atlas, falhas = montar_atlas(recursos, list(tix), tile_max)

    cab = {
        "formato": "mcscan",
        "versao": VERSAO_FORMATO,
        "dimensao": dimensao,
        "area": {"x1": x1, "z1": z1, "x2": x2, "z2": z2, "ymin": ymin, "ymax": ymax},
        "chunks": {"cx0": cx0, "cz0": cz0, "ncx": ncx, "ncz": ncz},
        "altura": H,
        "paleta": entradas,
        "modelos": modelos,
        "atlas": info_atlas,
        "tintas": TINTAS,
        "n_colunas": n_cols,
        "n_runs": n_runs,
        "streams": ["contagens:u16", "vazios:u16", "ids:u16", "comprimentos:u8"],
        "ordem": "chunks por z depois x; colunas por z depois x; y relativo a ymin",
        "flags": "1=transparente 2=opaco(cubo cheio) 4=translucido 8=agua 16=esconde faces iguais",
    }
    if progresso is not None:
        progresso(total, total, "Comprimindo e salvando")
    payload = (contagens.astype("<u2").tobytes() + vazios.astype("<u2").tobytes()
               + ids.astype("<u2").tobytes() + comps.astype("u1").tobytes())
    payload_c = zlib.compress(payload, 9)
    cab_c = zlib.compress(json.dumps(cab, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    with open(saida, "wb") as f:
        f.write(MAGIA + bytes([VERSAO_FORMATO]) + struct.pack("<III", len(cab_c), len(payload_c), len(png)))
        f.write(cab_c)
        f.write(payload_c)
        f.write(png)
    n_blocos = int(comps.astype(np.int64).sum())

    sem_modelo = {}
    if recursos.tem_fontes:
        for velho in usados:
            fb = pal.infos[int(velho)]["fallback"]
            if fb:
                base = pal.chaves[int(velho)].split("[", 1)[0]
                atual = sem_modelo.get(base, [fb, 0])
                atual[1] += int(contagem_ids[int(velho)])
                sem_modelo[base] = atual
    sem_modelo = sorted(((n, v[0], v[1]) for n, v in sem_modelo.items()), key=lambda t: -t[2])
    relatorio = None
    if recursos.tem_fontes:
        relatorio = saida + ".relatorio.txt"
        linhas = ["Relatório do scan: %s" % os.path.basename(saida), "",
                  "Blocos guardados: %d | tipos: %d | texturas no atlas: %d" % (n_blocos, len(usados), len(tix)), ""]
        linhas.append("BLOCOS QUE VIRARAM CUBO (sem modelo próprio): %d tipo(s)" % len(sem_modelo))
        for n, motivo, q in sem_modelo:
            linhas.append("  %s  (%d blocos) - %s" % (n, q, motivo))
        dg = pal.diag
        linhas += ["BLOCOS-ENTIDADE LIDOS NO MUNDO (copycats, quadros, placas...): %d tipo(s)" % len(dg["be"])]
        for bid, qtd in dg["be"].most_common(40):
            linhas.append("  %s  (%d)  campos: %s" % (bid, qtd, ", ".join(dg["amostra"].get(bid, [])) or "-"))
        linhas.append("  Copycats com material aplicado: %d | sem material no NBT: %d | quadros-negros desenhados: %d"
                      % (dg["cc_ok"], dg["cc_sem"], dg["quadros"]))
        for e in dg["erros"]:
            linhas.append("  ERRO: " + e)
        linhas.append("")
        regras = recursos._carregar_ctm()
        ign = getattr(recursos, "ctm_ignorados", {})
        linhas += ["", "REGRAS DE TEXTURA OPTIFINE/CTM aplicadas: %d (random/fixed) + %d (overlay)" % (len(regras), len(recursos.overlays()))]
        if ign:
            linhas.append("  não suportadas ainda (ignoradas): " + ", ".join("%s=%d" % kv for kv in sorted(ign.items())))
        linhas += ["", "TEXTURAS NÃO ENCONTRADAS (aparecem em magenta): %d" % len(falhas)]
        linhas += ["  " + t for t in falhas]
        if recursos.avisos:
            linhas += ["", "AVISOS:"] + ["  " + a for a in recursos.avisos]
        try:
            with open(relatorio, "w", encoding="utf-8") as f:
                f.write("\n".join(linhas) + "\n")
        except OSError:
            relatorio = None
    return {"arquivo": saida, "bytes": os.path.getsize(saida), "blocos": n_blocos,
            "trechos": n_runs, "tipos": len(usados), "chunks": total,
            "texturas": len(tix), "texturas_faltando": falhas, "avisos": list(recursos.avisos),
            "sem_modelo": sem_modelo, "relatorio": relatorio,
            "bytes_atlas": len(png), "bytes_cabecalho": len(cab_c), "bytes_dados": len(payload_c)}


def ler_mcscan(caminho):
    with open(caminho, "rb") as f:
        dados = f.read()
    if dados[:4] != MAGIA or dados[4] != VERSAO_FORMATO:
        raise ValueError("Arquivo inválido")
    lc, lp, la = struct.unpack_from("<III", dados, 5)
    cab = json.loads(zlib.decompress(dados[17:17 + lc]).decode("utf-8"))
    raw = zlib.decompress(dados[17 + lc:17 + lc + lp])
    atlas_png = dados[17 + lc + lp:17 + lc + lp + la]
    nc, nr = cab["n_colunas"], cab["n_runs"]
    cont = np.frombuffer(raw, "<u2", nc, 0)
    vaz = np.frombuffer(raw, "<u2", nr, 2 * nc)
    ids = np.frombuffer(raw, "<u2", nr, 2 * nc + 2 * nr)
    comp = np.frombuffer(raw, "u1", nr, 2 * nc + 4 * nr)
    ncx = cab["chunks"]["ncx"]
    trechos = []
    r = 0
    for col in range(nc):
        chunk, loc = col >> 8, col & 255
        x = (cab["chunks"]["cx0"] + chunk % ncx) * 16 + (loc & 15)
        z = (cab["chunks"]["cz0"] + chunk // ncx) * 16 + (loc >> 4)
        y = 0
        for _ in range(int(cont[col])):
            y += int(vaz[r])
            trechos.append((x, cab["area"]["ymin"] + y, z, int(ids[r]), int(comp[r])))
            y += int(comp[r])
            r += 1
    return cab, trechos, atlas_png


_CORES_COR = {
    "white": (235, 235, 235), "orange": (216, 127, 51), "magenta": (178, 76, 216),
    "light_blue": (102, 153, 216), "yellow": (229, 229, 51), "lime": (127, 204, 25),
    "pink": (242, 127, 165), "gray": (76, 76, 76), "light_gray": (153, 153, 153),
    "cyan": (76, 127, 153), "purple": (127, 63, 178), "blue": (51, 76, 178),
    "brown": (102, 76, 51), "green": (102, 127, 51), "red": (153, 51, 51),
    "black": (25, 25, 25),
}
_cache_cores = {}


def cor_do_bloco(nome):
    c = _cache_cores.get(nome)
    if c is not None:
        return c
    caminho = nome.split(":", 1)[-1]
    c = None
    regras = (
        ("water", (45, 85, 200)), ("lava", (230, 90, 20)), ("leaves", (50, 115, 40)),
        ("grass", (95, 160, 55)), ("moss", (80, 120, 45)), ("podzol", (95, 70, 40)),
        ("dirt", (134, 96, 67)), ("mud", (60, 50, 50)), ("path", (150, 120, 70)),
        ("sand", (219, 207, 142)), ("gravel", (131, 127, 126)),
        ("snow", (240, 250, 250)), ("ice", (160, 200, 240)),
        ("log", (102, 81, 50)), ("wood", (102, 81, 50)), ("planks", (160, 130, 80)),
        ("deepslate", (70, 70, 75)), ("cobble", (110, 110, 110)),
        ("brick", (150, 90, 80)), ("netherrack", (110, 50, 50)),
        ("terracotta", (152, 94, 67)), ("glass", (170, 210, 220)),
        ("stone", (125, 125, 125)), ("bedrock", (50, 50, 50)),
        ("asphalt", (60, 60, 65)), ("road", (60, 60, 65)),
    )
    for chave, cor in regras:
        if chave in caminho:
            c = cor
            break
    if c is None:
        for nome_cor, cor in _CORES_COR.items():
            if caminho.startswith(nome_cor + "_"):
                c = cor
                break
    if c is None:
        h = (sum(ord(ch) * (i + 7) for i, ch in enumerate(caminho)) % 360) / 360.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.35, 0.75)
        c = (int(r * 255), int(g * 255), int(b * 255))
    _cache_cores[nome] = c
    return c


def listar_regioes(pasta):
    regs = []
    for f in os.listdir(pasta):
        m = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", f)
        if m and os.path.getsize(os.path.join(pasta, f)) >= 8192:
            regs.append((int(m.group(1)), int(m.group(2))))
    return regs


def gerar_visao(pasta, progresso=None, cancelar=None):
    regs = listar_regioes(pasta)
    if not regs:
        raise ValueError("Nenhum arquivo de região (.mca) encontrado.")
    rx0 = min(r[0] for r in regs)
    rx1 = max(r[0] for r in regs)
    rz0 = min(r[1] for r in regs)
    rz1 = max(r[1] for r in regs)
    nreg = max(rx1 - rx0 + 1, rz1 - rz0 + 1)
    res = 8 if nreg <= 6 else (4 if nreg <= 32 else (2 if nreg <= 64 else 1))
    passo = 16 // res
    offs = [passo * i + passo // 2 for i in range(res)]
    w = (rx1 - rx0 + 1) * 32 * res
    h = (rz1 - rz0 + 1) * 32 * res
    rgb = np.empty((h, w, 3), np.uint8)
    rgb[:] = (28, 28, 32)
    topo = np.full((h, w), -9999, np.int16)
    topo_max = np.full((h, w), -9999, np.int16)
    nome_idx = np.full((h, w), -1, np.int32)
    nomes, nomes_ix = [], {}
    pasta_r = PastaRegioes(pasta)
    total = len(regs) * 1024
    feito = 0
    for rx, rz in sorted(regs):
        for lz in range(32):
            for lx in range(32):
                feito += 1
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado()
                if progresso is not None and feito % 64 == 0:
                    progresso(feito, total, "Lendo o mapa de cima")
                cx, cz = rx * 32 + lx, rz * 32 + lz
                nbt = pasta_r.chunk(cx, cz)
                if not chunk_completo(nbt):
                    continue
                hm = (nbt.get("Heightmaps") or {}).get("WORLD_SURFACE")
                if hm is None:
                    continue
                bits = None
                for b in range(1, 17):
                    if -(-256 // (64 // b)) == len(hm):
                        bits = b
                        break
                if bits is None:
                    continue
                alturas = desempacotar(hm, bits, 256).astype(np.int64)
                min_y = int(nbt.get("yPos", -4)) * 16
                if int(alturas.max()) > 0:
                    py0 = (cz - rz0 * 32) * res
                    px0 = (cx - rx0 * 32) * res
                    topo_max[py0:py0 + res, px0:px0 + res] = int(alturas.max()) - 1 + min_y
                secs = {int(s["Y"]): s for s in nbt["sections"]}
                dec = {}
                for iz, z in enumerate(offs):
                    for ix, x in enumerate(offs):
                        v = int(alturas[z * 16 + x])
                        if v <= 0:
                            continue
                        y = v - 1 + min_y
                        sy = y >> 4
                        if sy not in dec:
                            dec[sy] = decodificar_secao(secs[sy]) if sy in secs else None
                        if dec[sy] is None:
                            continue
                        idx, paleta = dec[sy]
                        nome = paleta[int(idx[((y & 15) * 16 + z) * 16 + x])]["Name"]
                        py = ((cz - rz0 * 32) * res) + iz
                        px = ((cx - rx0 * 32) * res) + ix
                        rgb[py, px] = cor_do_bloco(nome)
                        topo[py, px] = y
                        k = nomes_ix.get(nome)
                        if k is None:
                            k = len(nomes)
                            nomes.append(nome)
                            nomes_ix[nome] = k
                        nome_idx[py, px] = k
    ys, xs = np.nonzero(nome_idx >= 0)
    if ys.size == 0:
        raise ValueError("Não encontrei chunks gerados nessa dimensão.")
    i0, j0 = max(int(xs.min()) - res, 0), max(int(ys.min()) - res, 0)
    i1, j1 = min(int(xs.max()) + res + 1, w), min(int(ys.max()) + res + 1, h)
    f = 16 // res
    return {"res": res, "x0": rx0 * 512 + i0 * f, "z0": rz0 * 512 + j0 * f, "w": i1 - i0, "h": j1 - j0,
            "topo_max": topo_max[j0:j1, i0:i1], "rgb": np.ascontiguousarray(rgb[j0:j1, i0:i1]),
            "topo": topo[j0:j1, i0:i1], "nome_idx": nome_idx[j0:j1, i0:i1], "nomes": nomes}


def iniciar_janela():
    import mapscan_gui
    mapscan_gui.iniciar()


def main():
    ap = argparse.ArgumentParser(description="Scap")
    ap.add_argument("--mundo", help="pasta do mundo (a que contém 'region')")
    ap.add_argument("--dim", default="Overworld", help="Overworld, Nether, End ou namespace:nome")
    for k in ("x1", "z1", "x2", "z2", "ymin", "ymax"):
        ap.add_argument("--" + k, type=int)
    ap.add_argument("--saida", default="cidade.scap")
    ap.add_argument("--sem-estados", action="store_true", help="não guardar estados (escadas, portas...)")
    ap.add_argument("--jar", help="jar do Minecraft (ex.: .../versions/1.20.1/1.20.1.jar); se omitido, tenta achar")
    ap.add_argument("--mods", help="pasta de mods; se omitida, tenta achar")
    ap.add_argument("--pacotes", nargs="*", default=[], help="resource packs (.zip ou pasta); o último vence")
    ap.add_argument("--sem-texturas", action="store_true", help="não usar texturas (cubos coloridos)")
    ap.add_argument("--folhas-vazadas", action="store_true", help="folhas com buracos transparentes (mais pesado e mais ruidoso)")
    ap.add_argument("--tile", type=int, default=256, help="tamanho máximo de cada textura no arquivo (16, 32, 64...)")
    ap.add_argument("--sem-animacao", action="store_true", help="não guardar os quadros das texturas animadas (arquivo menor)")
    ap.add_argument("--visualizar", help="abre o visualizador 3D com este arquivo .scap")
    ap.add_argument("--titulo", help="(interno) título da janela do visualizador")
    ap.add_argument("--sem-moldura", action="store_true", help="(interno) visualizador sem moldura, para embutir no app")
    ap.add_argument("--pai", help="(interno) pid do app que embute o visualizador")
    a = ap.parse_args()
    if a.visualizar:
        import mapscan_viewer
        sys.exit(mapscan_viewer.executar(a.visualizar, a.titulo, a.sem_moldura, a.pai))
    if not a.mundo:
        iniciar_janela()
        return
    dims = dict(achar_dimensoes(a.mundo))
    if a.dim not in dims:
        sys.exit("Dimensão '%s' não encontrada. Disponíveis: %s" % (a.dim, ", ".join(dims) or "nenhuma"))
    falta = [k for k in ("x1", "z1", "x2", "z2", "ymin", "ymax") if getattr(a, k) is None]
    if falta:
        sys.exit("Faltam: " + ", ".join("--" + k for k in falta))

    def prog(f, t, m):
        sys.stderr.write("\r%s   " % m)
        sys.stderr.flush()
    rec = None
    if not a.sem_texturas:
        jar = a.jar or achar_jar_minecraft(a.mundo)
        mods = a.mods or achar_pasta_mods(a.mundo)
        print("Jar do Minecraft:", jar or "(não encontrado)")
        print("Pasta de mods:", mods or "(não encontrada)")
        rec = Recursos(jar, mods, a.pacotes, [])
        rec.folhas_opacas = not a.folhas_vazadas
        rec.animar = not a.sem_animacao
        if not rec.tem_fontes:
            sys.exit("Nenhuma textura encontrada. Use --jar e --mods, ou --sem-texturas.")
    r = escanear(dims[a.dim], a.x1, a.z1, a.x2, a.z2, a.ymin, a.ymax, a.saida,
                 not a.sem_estados, a.dim, prog, None, rec, a.tile)
    sys.stderr.write("\n")
    print("Salvo: %s | %.2f MB (texturas %.2f MB) | %d blocos | %d tipos | %d texturas" % (
        r["arquivo"], r["bytes"] / 1048576, r["bytes_atlas"] / 1048576, r["blocos"], r["tipos"], r["texturas"]))
    if r["texturas_faltando"]:
        print("Texturas não encontradas (%d): %s" % (len(r["texturas_faltando"]), ", ".join(r["texturas_faltando"][:10])))
    if r["sem_modelo"]:
        print("Blocos sem modelo próprio, viraram cubo (%d tipos): %s" % (
            len(r["sem_modelo"]), ", ".join("%s (%d)" % (n, q) for n, _, q in r["sem_modelo"][:10])))
    if r["relatorio"]:
        print("Relatório completo:", r["relatorio"])
    for av in r["avisos"][:5]:
        print("Aviso:", av)


if __name__ == "__main__":
    main()
