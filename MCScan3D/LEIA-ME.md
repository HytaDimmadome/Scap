# Scap

Escaneia a sua cidade no Minecraft (Java 1.20.1, Forge, com mods) e gera um arquivo `.scap` pequeno, com os blocos em 3D e as texturas do jogo e dos mods. Uma página HTML (`visualizador.html`) abre esse arquivo e mostra a cidade em câmera isométrica (45°).

O que acompanha:

| Arquivo | Para quê |
|---|---|
| `mcscan.py` | O scanner (janela para escolher a área) |
| `visualizador.html` + `mcscan_leitor.js` + `mcscan_visualizador.js` | A página que mostra o mapa |
| `exemplo/cidade_exemplo.scap` | Um mapa de teste, para ver o visualizador funcionando antes de escanear |
| `criar_exe.bat` / `rodar_sem_exe.bat` | Criar um `.exe` ou abrir o scanner direto |

## 1. Instalar e abrir o scanner

1. Instale o Python 3.9 ou mais novo (python.org). Marque **"Add Python to PATH"**.
2. Dê duplo clique em `rodar_sem_exe.bat` (ele instala o que falta e abre a janela).
   Para gerar o instalador, veja a seção do instalador abaixo.

## 2. Escanear a cidade

1. **Escolher pasta do mundo**: a pasta do mundo, a que contém a pasta `region` (ex.: `saves\MinhaCidade`).
   O programa tenta achar sozinho o jar do Minecraft e a pasta de mods. Se não achar, indique em **Texturas**:
   - **Jar do Minecraft**: normalmente `.minecraft\versions\1.20.1\1.20.1.jar`
   - **Pasta de mods**: a pasta `mods` do seu jogo (os `.jar` dos mods têm as texturas dos blocos deles)
   - **Resource packs** (opcional): se a cidade usa um pack de texturas, adicione o `.zip`. O último da lista vence.
2. **Carregar mapa de cima**: desenha o mundo visto de cima. Mundos grandes demoram (cada chunk precisa ser lido).
3. Arraste com o botão esquerdo para marcar a cidade. Botão direito move o mapa, roda do mouse dá zoom.
   O programa sugere o **Y mín.** (chão - 3) e o **Y máx.** (ponto mais alto da área). Ajuste se a cidade tiver porões mais fundos ou torres mais altas.
4. **Escanear área selecionada** e escolha onde salvar (ex.: `cidade.scap`). Ao final aparece o tamanho do arquivo, as texturas não encontradas e os blocos que não tiveram modelo próprio. A lista completa fica no arquivo `cidade.scap.relatorio.txt`, ao lado do scan.

Por terminal (sem janela):

```
python mcscan.py --mundo "C:\caminho\do\mundo" --x1 0 --z1 0 --x2 800 --z2 800 --ymin 60 --ymax 160 --jar "C:\...\1.20.1.jar" --mods "C:\...\mods" --saida cidade.scap
```

Opções úteis: `--pacotes pack1.zip pack2.zip`, `--tile 64` (limita o tamanho das texturas no arquivo, mais leve; o padrão é 256), `--sem-estados`, `--sem-texturas`.

## 3. Ver o mapa

Coloque `visualizador.html`, `mcscan_leitor.js`, `mcscan_visualizador.js` e o seu `cidade.scap` na mesma pasta do site.
A página carrega `cidade.scap` sozinha (ou `visualizador.html?arquivo=outro.scap`). Precisa estar num servidor: abrir o HTML direto do disco não deixa o navegador baixar o arquivo, mas o botão **Abrir .scap** funciona nesse caso.

Controles: arrastar move, roda do mouse dá zoom, dois dedos dão zoom no celular. Afaste para ver a cidade inteira e aproxime para ver os blocos com textura. Os botões ⟲ ⟳ giram a câmera de canto em canto (sempre isométrica).

Para embutir em outra página:

```html
<canvas id="mapa" style="width:100%;height:600px"></canvas>
<script src="mcscan_leitor.js"></script>
<script src="mcscan_visualizador.js"></script>
<script>
  McScan.carregar("cidade.scap").then(scan => McScanView.criar(document.getElementById("mapa"), scan));
</script>
```

## O que é guardado no arquivo

- Só os blocos que encostam em ar ou em algo transparente. Terra e pedra enterradas ficam de fora, e o interior das construções entra por conta própria (paredes, chão, móveis).
- Tudo abaixo do **Y mín.** é ignorado, então cavernas e minas ficam de fora.
- Os modelos dos blocos (escadas, lajes, cercas, portas, plantas...) com direção e posição, mais as texturas num único atlas PNG.
- Folhas, grama e água recebem a cor padrão de bioma "planície".

## Limites desta versão

- **Blocos especiais viram cubos** (o relatório do scan lista exatamente quais, de qual mod, e quantos blocos de cada). Baús, camas, placas, banners, cabeças e blocos de mods que desenham o modelo por código (em vez de arquivo de modelo) aparecem como um cubo com a textura do bloco. Se faltar a textura, aparece magenta.
- Não são guardados: entidades, itens, conteúdo de baús, texto de placas.
- A água é desenhada como bloco cheio e parada (sem altura de fluxo nem animação).
- Chunks ainda no formato de versões bem antigas (nunca abertos no 1.18 ou mais novo) são ignorados.
- Em cidades grandes o visualizador mostra de longe uma versão simplificada (pilares coloridos) e só desenha os blocos com textura na parte que está na tela, descartando o que fica escondido atrás de telhados e paredes. Se o zoom de perto ficar pesado no seu computador, afaste um pouco.
- Ainda não existe o clique numa construção para dar zoom e mostrar o interior. Os dados para isso já estão no arquivo.

## Formato do arquivo (resumo)

`MCSC` + versão 2 + tamanhos + cabeçalho JSON comprimido (área, paleta, modelos, atlas) + colunas de trechos de blocos comprimidas + atlas PNG.

## Novidades desta versão
- Atlas novo: cada textura fica no próprio tamanho (16, 32, 64, 128 ou 256 px), em vez de todas caberem num quadrado de 64. Texturas de mods como o canelamnb (postes, bandeiras, placas) mantêm o detalhe. Se o atlas passar do limite, o scanner reduz o teto sozinho.
- Geometria 4× mais precisa (1/64 de bloco): peças finas e inclinadas de modelos do Blockbench não colapsam mais.
- Texturas animadas (com `.mcmeta`) usam só o quadro certo da tira; as sem `.mcmeta` ficam inteiras.
- Formas dos Copycats+ (fatia, fatia vertical, canto, meio degrau, camadas empilhadas) conferidas no código do mod: agora são as medidas reais (por exemplo, a fatia vertical é uma coluna de 2×2 px no canto do bloco).
- Suavização ao afastar o zoom.
- Sombras suaves nos cantos entre blocos.
- Folhas: as faces do cubo ficam sem buracos; planos extras de packs "bushy" continuam vazados. Para tudo vazado: `--folhas-vazadas`.
- Copycats (Create e Copycats+): o scanner lê o material copiado de cada bloco no mundo e aplica a textura (formas aproximadas).
- Grama e outros blocos com modelos sorteados (blockstates com vários modelos e pesos, como o pack Blooming Ground Fusion: flores, trevos, pedrinhas) agora variam de posição em posição, em vez de usar sempre o primeiro modelo.
- Regras `overlay` do OptiFine (franjas de grama sobre terra/caminho/pedra, como no Canela V1.1) são desenhadas conforme os vizinhos.
- Visualizador: sem linhas entre os blocos em nenhum zoom (cada amostra de textura fica presa ao interior da própria textura), antialiasing por supersampling e sol de outono: baixo, dourado, com sombras longas e marcadas projetadas por prédios e árvores. Não precisa refazer o scan para isso.
- **Refaça o scan** da cidade com este mcscan.py para ganhar a resolução nova; `.scap` antigos abrem, mas continuam em 16×16.
- Limites atuais: cor de grama/folhas é a mesma em todos os biomas; texturas animadas usam o primeiro quadro; baús, camas, placas e Copycats são desenhados como cubos.

## Regras do OptiFine / CTM
O scanner lê `optifine/ctm/**/*.properties` dos resource packs (e mods) e aplica `method=random` (texturas sorteadas por posição, com `weights`, `faces`, `matchBlocks`, `matchTiles`) `method=fixed` e `method=overlay` (bordas por cima do bloco, ex.: grama sobre terra). O relatório (`.relatorio.txt`) mostra quantas regras foram aplicadas e quais métodos ainda não são suportados (ex.: `ctm`, `horizontal`, `vertical`, `overlay_random`, `repeat`).

## Blocos-entidade (Copycats, quadro-negro do Supplementaries)
O scanner lê os dados NBT dos blocos: Copycats (Create e Copycats+, inclusive o campo `material_data` com vários materiais) ganham o material copiado, e o quadro-negro do Supplementaries é desenhado com os pixels salvos, usando o formato e as cores do próprio mod. As formas dos Copycats são aproximadas. O `.relatorio.txt` lista os blocos-entidade encontrados no mundo e quantos foram aplicados; se algo não aparecer, esse trecho do relatório mostra por quê.

## Scap
Barra lateral: Mapa, Configurações, Mods, Sobre. Fluxo: Mapa → escolher a pasta do mundo → arrastar a área
→ conferir Y → ESCANEAR → "Ver em 3D" (abre o visualizador numa janela do próprio Scap, sem navegador).
Para ver um scan que já existe: Ctrl+O (ou botão na tela inicial).

## Gerar o instalador único (Scap-Setup.exe)
Sem .bat: suba esta pasta para um repositório no GitHub, abra Actions > "Gerar instalador do Scap" > Run workflow.
Ao terminar, baixe o artefato Scap-Setup. É um só .exe que instala tudo (atalhos e desinstalador inclusos).
Para rodar direto do código: pip install -r requirements.txt e python mcscan.py
