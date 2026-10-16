# Scap

Lê um mundo de Minecraft Java (1.18+) e salva a área escolhida num `.scap`, que o visualizador abre em câmera isométrica.

- `mcscan.py`: o scanner
- `mapscan_*.py`: o app do Windows
- `visualizador.html`, `mcscan_leitor.js`, `mcscan_visualizador.js`: o visualizador 3D

## Rodar

```
pip install -r requirements.txt
python mapscan_gui.py
```

## Terminal

```
python mcscan.py --mundo "C:\mundo" --x1 0 --z1 0 --x2 800 --z2 800 --ymin 60 --ymax 160 --jar "C:\...\1.20.1.jar" --mods "C:\...\mods" --saida cidade.scap
```

Também aceita `--pacotes`, `--tile`, `--sem-estados`, `--sem-texturas` e `--folhas-vazadas`.

## Instalador

O workflow "Gerar instalador do Scap" compila o `Scap-Setup.exe` e publica numa Release a cada commit em `Scan/` com a versão nova.
