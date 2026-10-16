import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "HytaDimmadome/Scap"
API = (os.environ.get("SCAP_API") or "https://api.github.com").rstrip("/")
ARQUIVO = "Scap-Setup.exe"
UA = "Scap-Atualizador"


def numeros(v):
    m = re.search(r"\d+(?:\.\d+)*", str(v or ""))
    if not m:
        return (0, 0, 0)
    p = [int(x) for x in m.group(0).split(".")][:3]
    return tuple(p + [0] * (3 - len(p)))


def _pedido(url):
    return urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})


def buscar(versao_atual, timeout=12):
    try:
        with urllib.request.urlopen(_pedido("%s/repos/%s/releases/latest" % (API, REPO)), timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": True, "nova": False, "versao": str(versao_atual), "notas": "", "url": "", "tamanho": 0}
        if e.code in (403, 429):
            return {"ok": False, "erro": "Tente de novo em alguns minutos."}
        return {"ok": False, "erro": "Não deu para verificar agora."}
    except Exception:
        return {"ok": False, "erro": "Sem conexão com a internet."}
    tag = str(dados.get("tag_name") or "")
    url, tam = "", 0
    for a in dados.get("assets") or []:
        if str(a.get("name", "")).lower() == ARQUIVO.lower():
            url, tam = a.get("browser_download_url", ""), int(a.get("size") or 0)
            break
    nova = numeros(tag) > numeros(versao_atual)
    if nova and not url:
        return {"ok": False, "erro": "Não deu para baixar a versão %s." % tag.lstrip("vV")}
    return {"ok": True, "nova": nova, "versao": tag.lstrip("vV"), "notas": str(dados.get("body") or "").strip(),
            "url": url, "tamanho": tam}


def baixar(url, destino, progresso=None, cancelar=None, tamanho=0):
    tmp = destino + ".parte"
    try:
        with urllib.request.urlopen(_pedido(url), timeout=30) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or tamanho or 0)
            lido = 0
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise InterruptedError
                bloco = r.read(256 * 1024)
                if not bloco:
                    break
                f.write(bloco)
                lido += len(bloco)
                if progresso and total:
                    progresso(min(1.0, lido / total))
        if os.path.getsize(tmp) < 100000:
            raise ValueError("arquivo pequeno demais")
        with open(tmp, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("não é um instalador do Windows")
        if os.path.exists(destino):
            os.remove(destino)
        os.replace(tmp, destino)
        return None
    except InterruptedError:
        erro = "Download cancelado."
    except (urllib.error.URLError, OSError):
        erro = "Falha ao baixar. Tente de novo."
    except Exception:
        erro = "O arquivo baixado é inválido."
    try:
        os.remove(tmp)
    except OSError:
        pass
    return erro


def instalar(caminho):
    args = [caminho, "/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS"]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200
    subprocess.Popen(args, close_fds=True, **kw)


def pode_instalar():
    return os.name == "nt" and bool(getattr(sys, "frozen", False))
