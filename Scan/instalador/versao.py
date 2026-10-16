import os
import re

aqui = os.path.dirname(os.path.abspath(__file__))
txt = open(os.path.join(aqui, "..", "mapscan_gui.py"), encoding="utf-8").read()
print(re.search(r'^VERSAO = "(\d+\.\d+\.\d+)"', txt, re.M).group(1))
