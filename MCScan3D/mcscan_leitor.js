/*
 * mcscan_leitor.js — lê arquivos .scap (versão 2, gerados por mcscan.py) no navegador
 * e prepara os dados para o visualizador: índice de colunas, culling de faces e
 * malhas por pedaço (chunk) e em baixa resolução (LOD).
 *
 *   const scan = await McScan.carregar("cidade.scap");
 *   McScan.indexar(scan);
 *
 * O desenho em WebGL fica em mcscan_visualizador.js.
 * Precisa de um navegador atual (usa DecompressionStream).
 */
(function (raiz) {
  "use strict";

  var F_TRANSP = 1, F_OPACO = 2, F_TRANSLUC = 4, F_AGUA = 8, F_CULLSAME = 16;
  var SUB = 64;                  // subdivisões por bloco nas posições dos vértices (1/64 de bloco)
  var BIAS = 4 * SUB;            // somado às posições para aceitar modelos que saem até 4 blocos da célula
  var DX = [0, 0, 0, 0, -1, 1], DY = [-1, 1, 0, 0, 0, 0], DZ = [0, 0, -1, 1, 0, 0];

  // Descompacta direto num buffer do tamanho exato (se conhecido), sem cópias extras na memória.
  async function inflar(u8, tamanho) {
    var fluxo = new Blob([u8]).stream().pipeThrough(new DecompressionStream("deflate"));
    if (!tamanho) return new Response(fluxo).arrayBuffer();
    var saida = new Uint8Array(tamanho), pos = 0, leitor = fluxo.getReader();
    for (;;) {
      var r = await leitor.read();
      if (r.done) break;
      if (pos + r.value.length > tamanho) {            // tamanho previsto errado: cresce em vez de falhar
        var maior = new Uint8Array(Math.max(tamanho * 2, pos + r.value.length));
        maior.set(saida.subarray(0, pos)); saida = maior; tamanho = maior.length;
      }
      saida.set(r.value, pos); pos += r.value.length;
    }
    return saida.length === pos ? saida.buffer : saida.buffer.slice(0, pos);
  }
  function etapa(nome, e) {
    var m = (e && e.message) || String(e);
    return new Error(m + " [etapa: " + nome + "]");
  }

  async function decodificar(buf) {
    var dv = new DataView(buf);
    var magia = new TextDecoder().decode(new Uint8Array(buf, 0, 4));
    if (magia !== "MCSC") throw new Error("Arquivo .scap inválido");
    var versao = dv.getUint8(4);
    if (versao !== 2) throw new Error("Versão do .scap não suportada: " + versao + " (gere o arquivo de novo com o mcscan.py atual)");
    var lc = dv.getUint32(5, true), lp = dv.getUint32(9, true), la = dv.getUint32(13, true);
    var cab, raw;
    try { cab = JSON.parse(new TextDecoder().decode(await inflar(new Uint8Array(buf, 17, lc)))); }
    catch (e) { throw etapa("cabeçalho", e); }
    var nc = cab.n_colunas, nr = cab.n_runs;
    try { raw = await inflar(new Uint8Array(buf, 17 + lc, lp), 2 * nc + 5 * nr); }
    catch (e) { throw etapa("descompactar " + Math.round((2 * nc + 5 * nr) / 1048576) + " MB", e); }
    return {
      cab: cab,
      contagens: new Uint16Array(raw, 0, nc),
      vazios: new Uint16Array(raw, 2 * nc, nr),
      ids: new Uint16Array(raw, 2 * nc + 2 * nr, nr),
      comprimentos: new Uint8Array(raw, 2 * nc + 4 * nr, nr),
      atlasPng: new Uint8Array(buf, 17 + lc + lp, la)
    };
  }

  async function carregar(url) {
    var resp = await fetch(url);
    if (!resp.ok) throw new Error("Não consegui baixar " + url);
    return decodificar(await resp.arrayBuffer());
  }

  /* Percorre os trechos: fn(x, y, z, id, comprimento) */
  function percorrer(scan, fn) {
    var cab = scan.cab, ncx = cab.chunks.ncx;
    var r = 0;
    for (var col = 0; col < scan.contagens.length; col++) {
      var chunk = col >> 8, loc = col & 255;
      var x = (cab.chunks.cx0 + (chunk % ncx)) * 16 + (loc & 15);
      var z = (cab.chunks.cz0 + Math.floor(chunk / ncx)) * 16 + (loc >> 4);
      var y = 0;
      for (var k = 0; k < scan.contagens[col]; k++, r++) {
        y += scan.vazios[r];
        fn(x, cab.area.ymin + y, z, scan.ids[r], scan.comprimentos[r]);
        y += scan.comprimentos[r];
      }
    }
  }

  /* Câmera isométrica: 4 cantos (0: sudeste, 1: sudoeste, 2: noroeste, 3: nordeste) */
  function baseCamera(cam) {
    cam = cam & 3;
    var sx = (cam === 0 || cam === 3) ? 1 : -1, sz = (cam === 0 || cam === 1) ? 1 : -1;
    var k = 1 / Math.sqrt(3);
    var f = [-sx * k, -k, -sz * k];
    var r = [-f[2], 0, f[0]];
    var lr = Math.hypot(r[0], r[1], r[2]);
    r = [r[0] / lr, r[1] / lr, r[2] / lr];
    var u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
    var lu = Math.hypot(u[0], u[1], u[2]);
    u = [u[0] / lu, u[1] / lu, u[2] / lu];
    return { r: r, u: u, f: f, sx: sx, sz: sz };
  }

  /* Índices por coluna, topo de cada coluna e topo de cada chunk (coordenadas relativas à área) */
  function indexar(scan) {
    if (scan.colIni) return scan;
    var cab = scan.cab, area = cab.area, ch = cab.chunks;
    var nc = scan.contagens.length, nr = scan.vazios.length, ncx = ch.ncx, ncz = ch.ncz;
    var Wx = area.x2 - area.x1 + 1, Dz = area.z2 - area.z1 + 1;
    var colIni = new Uint32Array(nc + 1), yIni = new Uint16Array(nr);
    var topo = new Int16Array(Wx * Dz).fill(-1000), idTopo = new Uint16Array(Wx * Dz);
    var topoChunk = new Int16Array(ncx * ncz).fill(-1);
    var r = 0;
    for (var col = 0; col < nc; col++) {
      colIni[col] = r;
      var n = scan.contagens[col];
      if (!n) continue;
      var chunk = col >> 8, loc = col & 255;
      var x = (ch.cx0 + (chunk % ncx)) * 16 + (loc & 15) - area.x1;
      var z = (ch.cz0 + ((chunk / ncx) | 0)) * 16 + (loc >> 4) - area.z1;
      var y = 0, t = -1, tid = 0;
      for (var k = 0; k < n; k++, r++) {
        y += scan.vazios[r];
        yIni[r] = y;
        y += scan.comprimentos[r];
        t = y - 1;
        tid = scan.ids[r];
      }
      if (x >= 0 && x < Wx && z >= 0 && z < Dz) {
        topo[z * Wx + x] = t;
        idTopo[z * Wx + x] = tid;
        if (t > topoChunk[chunk]) topoChunk[chunk] = t;
      }
    }
    colIni[nc] = r;
    scan.colIni = colIni; scan.yIni = yIni; scan.topo = topo; scan.idTopo = idTopo; scan.topoChunk = topoChunk;
    scan.Wx = Wx; scan.Dz = Dz; scan.H = cab.altura;
    scan._ctx = {}; scan._grupos = {};
    return scan;
  }

  /* "Horizonte diagonal": D(x,z) = max_k (topo(x+k*sx, z+k*sz) - k). Serve para saber, sem marchar,
     que nada pode esconder uma célula. */
  function horizonte(scan, cam) {
    scan._hz = scan._hz || {};
    if (scan._hz[cam]) return scan._hz[cam];
    var b = baseCamera(cam), sx = b.sx, sz = b.sz, Wx = scan.Wx, Dz = scan.Dz, T = scan.topo;
    var D = new Int16Array(Wx * Dz);
    var x0 = sx > 0 ? Wx - 1 : 0, x1 = sx > 0 ? -1 : Wx, dx = sx > 0 ? -1 : 1;
    var z0 = sz > 0 ? Dz - 1 : 0, z1 = sz > 0 ? -1 : Dz, dz = sz > 0 ? -1 : 1;
    for (var z = z0; z !== z1; z += dz) {
      for (var x = x0; x !== x1; x += dx) {
        var nx = x + sx, nz = z + sz;
        var d = (nx >= 0 && nx < Wx && nz >= 0 && nz < Dz) ? D[nz * Wx + nx] - 1 : -1000;
        var t = T[z * Wx + x];
        D[z * Wx + x] = t > d ? t : d;
      }
    }
    scan._hz[cam] = D;
    return D;
  }

  /* Sol de outono: baixo (~30 graus), vindo de trás e da esquerda da câmera. h = direção horizontal até o sol. */
  var LUZ = { az: 38, elev: 30, noite: 0 };   // az em graus a partir de trás da câmera (+ = esquerda da tela); noite 0/1
  function chaveLuz() { return LUZ.az + "_" + LUZ.elev + "_" + LUZ.noite; }
  function configLuz(c) {
    if (c) { if (c.az != null) LUZ.az = +c.az; if (c.elev != null) LUZ.elev = Math.max(8, Math.min(80, +c.elev)); if (c.noite != null) LUZ.noite = c.noite ? 1 : 0; }
    return { az: LUZ.az, elev: LUZ.elev, noite: LUZ.noite };
  }
  function sol(sx, sz) {
    var SOL_AZ = LUZ.az * Math.PI / 180, SOL_ELEV = LUZ.elev * Math.PI / 180;
    var k = Math.SQRT1_2, bx = sx * k, bz = sz * k, rx = sz * k, rz = -sx * k;   // trás da câmera e direita da tela
    var c = Math.cos(SOL_AZ), sn = Math.sin(SOL_AZ);
    var hx = bx * c - rx * sn, hz = bz * c - rz * sn;
    var ce = Math.cos(SOL_ELEV), se = Math.sin(SOL_ELEV);
    return { hx: hx, hz: hz, lx: hx * ce, ly: se, lz: hz * ce, subida: Math.tan(SOL_ELEV) };
  }

  /* ---------- vértices ---------- */
  function Saida() {
    this.cap = 4096;
    this.buf = new ArrayBuffer(this.cap * 16);
    this.u16 = new Uint16Array(this.buf);
    this.u8 = new Uint8Array(this.buf);
    this.nv = 0;
  }
  Saida.prototype.limpar = function () { this.nv = 0; };
  Saida.prototype.garantir = function (extra) {
    var need = this.nv + extra;
    if (need <= this.cap) return;
    var cap = this.cap;
    while (cap < need) cap *= 2;
    var nb = new ArrayBuffer(cap * 16);
    new Uint8Array(nb).set(this.u8.subarray(0, this.nv * 16));
    this.buf = nb; this.u16 = new Uint16Array(nb); this.u8 = new Uint8Array(nb); this.cap = cap;
  };
  Saida.prototype.bytes = function () { return new Uint8Array(this.buf, 0, this.nv * 16); };
  Saida.prototype.quads = function () { return this.nv >> 2; };

  function hexRGB(h) {
    return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255];
  }

  /* [x, y, largura, altura] da textura no atlas, em pixels (atlas novo com retângulos ou antigo em grade) */
  function retanguloTextura(at, t) {
    if (at.rects) return at.rects[t];
    var C = at.colunas, T = at.tile;
    return [(t % C) * T, Math.floor(t / C) * T, T, T];
  }

  /* Modelo preparado para uma câmera: só as faces viradas para ela, com posições inteiras em 1/16 */
  function prepararModelo(cab, sx, sz, m) {
    var at = cab.atlas;
    var qs = cab.modelos[m], lista = [];
    for (var qi = 0; qi < qs.length; qi++) {
      var q = qs[qi];
      var v = q.slice(4, 16), uv = q.slice(16, 24);
      var nx = 0, ny = 0, nz = 0;
      for (var i = 0; i < 4; i++) {
        var j = (i + 1) & 3;
        var xi = v[i * 3], yi = v[i * 3 + 1], zi = v[i * 3 + 2];
        var xj = v[j * 3], yj = v[j * 3 + 1], zj = v[j * 3 + 2];
        nx += (yi - yj) * (zi + zj);
        ny += (zi - zj) * (xi + xj);
        nz += (xi - xj) * (yi + yj);
      }
      var len = Math.hypot(nx, ny, nz);
      if (len < 1e-6) continue;
      nx /= len; ny /= len; nz /= len;
      if (nx * sx + ny + nz * sz <= 1e-4) continue;      // de costas para a câmera
      var tex = q[0], rc = retanguloTextura(at, tex);
      var pos = new Int16Array(12), uvs = new Uint16Array(8);
      for (var a = 0; a < 12; a++) pos[a] = Math.round(v[a] * (SUB / 16));
      for (var b = 0; b < 4; b++) {
        var uu = Math.min(1, Math.max(0, uv[b * 2])), vv = Math.min(1, Math.max(0, uv[b * 2 + 1]));
        uvs[b * 2] = Math.round((rc[0] + 0.01 + uu * (rc[2] - 0.02)) / at.largura * 65535);
        uvs[b * 2 + 1] = Math.round((rc[1] + 0.01 + vv * (rc[3] - 0.02)) / at.altura * 65535);
      }
      var SO = sol(sx, sz), lam = Math.max(0, nx * SO.lx + ny * SO.ly + nz * SO.lz);
      var sombra = q[3] ? Math.min(1.12, 0.40 + 1.12 * lam) : 1;
      // direção do eixo se a face é alinhada (0..5 como DX/DY/DZ), senão -1 (sem sombra de canto)
      var dir = -1;
      if (Math.abs(nx) > 0.99) dir = nx > 0 ? 5 : 4;
      else if (Math.abs(ny) > 0.99) dir = ny > 0 ? 1 : 0;
      else if (Math.abs(nz) > 0.99) dir = nz > 0 ? 3 : 2;
      lista.push({ tint: q[1], cull: q[2], pos: pos, uv: uvs, sh: sombra, dir: dir, tx: tex, lam: q[3] ? lam : 1, nx: nx, ny: ny, nz: nz });
    }
    return lista;
  }

  /* Contexto por câmera: funções de consulta e de construção de malha */
  function contexto(scan, cam, opc) {
    indexar(scan);
    cam = cam & 3;
    var chave = cam + (opc && opc.semOclusao ? "s" : "") + "|" + chaveLuz();
    if (scan._ctx[chave]) return scan._ctx[chave];

    var cab = scan.cab, area = cab.area, ch = cab.chunks, pal = cab.paleta;
    var cc = baseCamera(cam), sx = cc.sx, sz = cc.sz;
    var Wx = scan.Wx, Dz = scan.Dz, H = scan.H, ncx = ch.ncx;
    var colIni = scan.colIni, yIni = scan.yIni, ids = scan.ids, comps = scan.comprimentos;
    var D = horizonte(scan, cam);
    var semOclusao = !!(opc && opc.semOclusao);
    var tintas = {};
    for (var k in cab.tintas) tintas[k] = hexRGB(cab.tintas[k]);
    var flags = new Uint8Array(pal.length);
    for (var i = 0; i < pal.length; i++) flags[i] = pal[i].f;
    var prep = new Array(cab.modelos.length);
    var ax0 = area.x1 - ch.cx0 * 16, az0 = area.z1 - ch.cz0 * 16;   // área-local -> chunk-local

    /* id do bloco numa célula (coordenadas relativas à área): 0 = ar/fora, -1 = abaixo do limite inferior */
    function idEm(xl, yr, zl) {
      if (yr < 0) return -1;
      if (yr >= H || xl < 0 || xl >= Wx || zl < 0 || zl >= Dz) return 0;
      var xa = xl + ax0, za = zl + az0;
      var col = ((((za >> 4) * ncx + (xa >> 4)) << 8) | ((za & 15) << 4) | (xa & 15));
      for (var r = colIni[col], fim = colIni[col + 1]; r < fim; r++) {
        var y0 = yIni[r];
        if (yr < y0) return 0;
        if (yr < y0 + comps[r]) return ids[r];
      }
      return 0;
    }

    /* A célula está totalmente escondida atrás de um cubo opaco no caminho da câmera? */
    function oculto(xl, yr, zl) {
      var nx = xl + sx, nz = zl + sz;
      if (nx < 0 || nx >= Wx || nz < 0 || nz >= Dz) return false;
      if (D[nz * Wx + nx] - 1 < yr) return false;
      for (var k = 1; ; k++) {
        var ax = xl + k * sx, az = zl + k * sz, ay = yr + k;
        if (ax < 0 || ax >= Wx || az < 0 || az >= Dz || ay >= H) return false;
        if (D[az * Wx + ax] - k < yr) return false;
        var id = idEm(ax, ay, az);
        if (id > 0 && (flags[id] & F_OPACO)) return true;
      }
    }

    var comAO = !(opc && opc.semSombras);
    var T = scan.topo;
    var SO = sol(sx, sz), SOL_HX = SO.hx, SOL_HZ = SO.hz, SOL_SUBIDA = SO.subida, SOL_PASSOS = 28;
    function luz(px, py, pz) {                       // 0 = sombra, 1 = sol (média de 3 raios: penumbra suave)
      var claro = 0;
      for (var r = -1; r <= 1; r++) {
        var ox = -SOL_HZ * r * 0.36, oz = SOL_HX * r * 0.36, livre = 1;
        for (var k = 1; k <= SOL_PASSOS; k++) {
          var x = Math.floor(px + ox + SOL_HX * k * 0.8), z = Math.floor(pz + oz + SOL_HZ * k * 0.8);
          if (x < 0 || x >= Wx || z < 0 || z >= Dz) break;
          if (T[z * Wx + x] + 1 > py + SOL_SUBIDA * k * 0.8 + 0.02) { livre = 0; break; }
        }
        claro += livre;
      }
      return claro / 3;
    }
    /* ---- noite: blocos que emitem luz e luz de bloco aproximada por vértice ---- */
    var NOITE = LUZ.noite === 1, emNivel = new Uint8Array(pal.length), emCache = {};
    if (NOITE) {
      var TAB = [["sea_lantern", 15], ["glowstone", 15], ["shroomlight", 15], ["jack_o_lantern", 15], ["redstone_lamp", 15], ["lava", 15],
        ["campfire", 15], ["froglight", 15], ["beacon", 15], ["lantern", 15], ["end_rod", 14], ["torch", 14], ["fire", 15],
        ["magma", 3], ["candle", 6], ["glow_lichen", 7], ["lit", 13], ["light_block", 15], ["crying_obsidian", 10]];
      for (var pi = 0; pi < pal.length; pi++) {
        var nm = pal[pi].n || "";
        if (nm.indexOf("[lit=false") >= 0 || nm.indexOf("unlit") >= 0 || nm.indexOf("soul_campfire") >= 0 && false) continue;
        for (var ti = 0; ti < TAB.length; ti++) if (nm.indexOf(TAB[ti][0]) >= 0) { emNivel[pi] = TAB[ti][1]; break; }
        if (nm.indexOf("lit=true") >= 0 && !emNivel[pi]) emNivel[pi] = 13;
      }
    }
    function emissores(i, j) {          // lâmpadas do chunk (i,j) e dos vizinhos: [x, y, z, nível] em coordenadas da área
      var k = i + "," + j;
      if (emCache[k]) return emCache[k];
      var lista = [], visto = {};
      for (var jj = j - 1; jj <= j + 1; jj++) for (var ii = i - 1; ii <= i + 1; ii++) {
        if (ii < 0 || jj < 0 || ii >= ncx || jj >= ch.ncz) continue;
        var b0 = (jj * ncx + ii) << 8, ox = (ch.cx0 + ii) * 16 - area.x1, oz = (ch.cz0 + jj) * 16 - area.z1;
        for (var loc = 0; loc < 256; loc++) {
          var col = b0 | loc;
          for (var r = colIni[col], fim = colIni[col + 1]; r < fim; r++) {
            var nv = emNivel[ids[r]];
            if (!nv) continue;
            for (var kk = 0; kk < comps[r]; kk++) {
              var x = ox + (loc & 15), y = yIni[r] + kk, z = oz + (loc >> 4);
              var h = (x >> 1) + "," + (y >> 1) + "," + (z >> 1);   // um por célula 2x2x2 (lagos de lava, etc.)
              if (visto[h]) continue;
              visto[h] = 1; lista.push([x + 0.5, y + 0.5, z + 0.5, nv]);
            }
          }
        }
      }
      if (lista.length > 160) { var pas = lista.length / 160, nl = []; for (var q2 = 0; q2 < 160; q2++) nl.push(lista[Math.floor(q2 * pas)]); lista = nl; }
      return (emCache[k] = lista);
    }
    var AO_TAB = [0.52, 0.7, 0.85, 1];
    function opaco(x, y, z) { var i = idEm(x, y, z); return i > 0 && (flags[i] & F_OPACO) ? 1 : 0; }

    /* Constrói a malha do chunk (i, j) (índices relativos). S = {opaco, transl} (Saida) */
    function malhaChunk(i, j, S) {
      S.opaco.limpar(); S.transl.limpar();
      var chunk = j * ncx + i;
      var base = chunk << 8;
      var cx0l = (ch.cx0 + i) * 16 - area.x1, cz0l = (ch.cz0 + j) * 16 - area.z1;   // origem do chunk, relativa à área
      var EM = NOITE ? emissores(i, j) : null, nEM = EM ? EM.length : 0;
      for (var loc = 0; loc < 256; loc++) {
        var col = base | loc, r0 = colIni[col], r1 = colIni[col + 1];
        if (r0 === r1) continue;
        var lx = loc & 15, lz = loc >> 4;
        var xl = cx0l + lx, zl = cz0l + lz;
        for (var r = r0; r < r1; r++) {
          var id = ids[r], p = pal[id], modelo = prep[p.m];
          if (p.m < 0) continue;
          if (!modelo) modelo = prep[p.m] = prepararModelo(cab, sx, sz, p.m);
          if (!modelo.length) continue;
          var fl = flags[id], dest = (fl & F_TRANSLUC) ? S.transl : S.opaco;
          var tint = p.t ? tintas[p.t] : null;
          var alfa = (fl & F_AGUA) ? 178 : 255;
          for (var kk = 0, n = comps[r]; kk < n; kk++) {
            var yr = yIni[r] + kk;
            if (!semOclusao && oculto(xl, yr, zl)) continue;
            for (var qi = 0; qi < modelo.length; qi++) {
              var q = modelo[qi];
              if (q.cull >= 0) {
                var nb = idEm(xl + DX[q.cull], yr + DY[q.cull], zl + DZ[q.cull]);
                if (nb === -1) continue;
                if (nb > 0) {
                  if (flags[nb] & F_OPACO) continue;
                  if (nb === id && (fl & F_CULLSAME)) continue;
                }
              }
              dest.garantir(4);
              var u16 = dest.u16, u8 = dest.u8, nv = dest.nv;
              var cr = q.sh, cg = q.sh, cb = q.sh;
              if (q.tint >= 0 && tint) { cr *= tint[0]; cg *= tint[1]; cb *= tint[2]; }
              var bx = lx * SUB + BIAS, by = yr * SUB + BIAS, bz = lz * SUB + BIAS;
              var usaAO = comAO && q.dir >= 0 && dest === S.opaco;
              if (usaAO) {
                var d = q.dir, ea = d >> 1;                       // eixo da normal: 0=x 1=y 2=z
                var t1 = ea === 0 ? 1 : 0, t2 = ea === 2 ? 1 : 2;  // eixos tangentes
                var pn = q.pos[0 * 3 + ea];
                usaAO = (d & 1) ? pn >= SUB - 4 : pn <= 4;              // só faces rentes à borda da célula
              }
              for (var v = 0; v < 4; v++) {
                var f = 1;
                if (usaAO) {
                  var p1 = q.pos[v * 3 + t1] >= SUB / 2 ? 1 : -1, p2 = q.pos[v * 3 + t2] >= SUB / 2 ? 1 : -1;
                  var cx = xl + DX[d], cy = yr + DY[d], cz = zl + DZ[d];
                  var sx1 = t1 === 0 ? p1 : 0, sy1 = t1 === 1 ? p1 : 0, sz1 = t1 === 2 ? p1 : 0;
                  var sx2 = t2 === 0 ? p2 : 0, sy2 = t2 === 1 ? p2 : 0, sz2 = t2 === 2 ? p2 : 0;
                  var a1 = opaco(cx + sx1, cy + sy1, cz + sz1), a2 = opaco(cx + sx2, cy + sy2, cz + sz2);
                  var a3 = opaco(cx + sx1 + sx2, cy + sy1 + sy2, cz + sz1 + sz2);
                  f = AO_TAB[(a1 && a2) ? 0 : 3 - (a1 + a2 + a3)];
                }
                var fr = f, fg = f, fb = f;
                if (comAO && dest === S.opaco) {
                  var li = (!NOITE && q.lam > 0.04) ? luz(xl + q.pos[v * 3] / SUB, yr + q.pos[v * 3 + 1] / SUB + 0.03, zl + q.pos[v * 3 + 2] / SUB) : 0;
                  // sombra fria e escura; luz quente e dourada (sol de outono)
                  if (NOITE) {
                    // luar azulado + luz quente das lâmpadas
                    fr *= 0.30; fg *= 0.37; fb *= 0.58;
                    var vx = xl + q.pos[v * 3] / SUB, vy = yr + q.pos[v * 3 + 1] / SUB, vz = zl + q.pos[v * 3 + 2] / SUB, lamp = 0;
                    for (var e = 0; e < nEM; e++) {
                      var E = EM[e], ex = E[0] - vx, ey = E[1] - vy, ez = E[2] - vz, dd = Math.sqrt(ex * ex + ey * ey + ez * ez);
                      var inten = (E[3] - dd) / 15;
                      if (inten <= 0) continue;
                      var cosn = dd > 0.01 ? (q.nx * ex + q.ny * ey + q.nz * ez) / dd : 1;
                      if (cosn < -0.1) continue;
                      inten *= 0.4 + 0.6 * Math.max(0, cosn);
                      if (inten > lamp) lamp = inten + (lamp * 0.3);
                    }
                    if (lamp > 1) lamp = 1;
                    if (emNivel[id]) lamp = 1.6;                       // a própria lâmpada brilha
                    fr += lamp * 1.15; fg += lamp * 0.78; fb += lamp * 0.38;
                  } else {
                    fr *= 0.56 + 0.56 * li; fg *= 0.60 + 0.41 * li; fb *= 0.76 + 0.08 * li;
                  }
                }
                if (NOITE && dest !== S.opaco) { fr *= 0.28; fg *= 0.34; fb *= 0.55; }
                var R8 = Math.min(255, (cr * fr * 255 + 0.5) | 0), G8 = Math.min(255, (cg * fg * 255 + 0.5) | 0), B8 = Math.min(255, (cb * fb * 255 + 0.5) | 0);
                var o = (nv + v) * 8, ob = (nv + v) * 16 + 12;
                u16[o] = bx + q.pos[v * 3];
                u16[o + 1] = by + q.pos[v * 3 + 1];
                u16[o + 2] = bz + q.pos[v * 3 + 2];
                u16[o + 3] = q.tx;
                u16[o + 4] = q.uv[v * 2];
                u16[o + 5] = q.uv[v * 2 + 1];
                u8[ob] = R8; u8[ob + 1] = G8; u8[ob + 2] = B8; u8[ob + 3] = alfa;
              }
              dest.nv = nv + 4;
            }
          }
        }
      }
      return S;
    }

    var c = { cam: cam, sx: sx, sz: sz, idEm: idEm, oculto: oculto, malhaChunk: malhaChunk, horizonte: D };
    scan._ctx[chave] = c;
    return c;
  }

  /* ---------- LOD: pilares em baixa resolução ---------- */

  /* Cor média (r,g,b) de cada tipo de bloco, vista de cima. rgba = pixels do atlas (largura = atlas.largura) */
  function calcularCores(scan, rgba) {
    var cab = scan.cab, at = cab.atlas, W = at.largura, pal = cab.paleta;
    var tintas = {};
    for (var k in cab.tintas) tintas[k] = hexRGB(cab.tintas[k]);
    var medias = {};
    function media(t) {
      if (medias[t]) return medias[t];
      var rc = retanguloTextura(at, t), sr = 0, sg = 0, sb = 0, n = 0;
      for (var y = 0; y < rc[3]; y++) {
        for (var x = 0; x < rc[2]; x++) {
          var o = ((rc[1] + y) * W + rc[0] + x) * 4;
          if (rgba[o + 3] >= 64) { sr += rgba[o]; sg += rgba[o + 1]; sb += rgba[o + 2]; n++; }
        }
      }
      return (medias[t] = n ? [sr / n, sg / n, sb / n] : [128, 128, 128]);
    }
    var cor = new Uint8Array(pal.length * 3).fill(128);
    for (var id = 1; id < pal.length; id++) {
      var p = pal[id];
      if (p.m < 0) continue;
      var qs = cab.modelos[p.m], melhor = null, my = -1;
      for (var qi = 0; qi < qs.length; qi++) {
        var q = qs[qi], y0 = q[5], horiz = true;
        for (var v = 1; v < 4; v++) if (Math.abs(q[4 + v * 3 + 1] - y0) > 1e-3) horiz = false;
        if (horiz && y0 > my) { my = y0; melhor = q; }
      }
      if (!melhor) melhor = qs[0];
      if (!melhor) continue;
      var m = media(melhor[0]), f = [1, 1, 1];
      if (melhor[1] >= 0 && p.t && tintas[p.t]) f = tintas[p.t];
      cor[id * 3] = Math.min(255, m[0] * f[0]);
      cor[id * 3 + 1] = Math.min(255, m[1] * f[1]);
      cor[id * 3 + 2] = Math.min(255, m[2] * f[2]);
    }
    scan.corId = cor;
    return cor;
  }

  /* Agrupa as colunas em blocos de g×g (g = 4, 16...): altura máxima e cor média do topo */
  function construirGrupos(scan, g) {
    indexar(scan);
    if (scan._grupos[g]) return scan._grupos[g];
    var sh = Math.round(Math.log2(g)), Wx = scan.Wx, Dz = scan.Dz;
    var gw = Math.ceil(Wx / g), gd = Math.ceil(Dz / g);
    var alt = new Int16Array(gw * gd).fill(-1000);
    var soma = new Uint32Array(gw * gd * 3), cnt = new Uint16Array(gw * gd);
    var cor = scan.corId || new Uint8Array(scan.cab.paleta.length * 3).fill(128);
    var T = scan.topo, I = scan.idTopo;
    for (var z = 0; z < Dz; z++) {
      for (var x = 0; x < Wx; x++) {
        var t = T[z * Wx + x];
        if (t < -999) continue;
        var gi = (z >> sh) * gw + (x >> sh);
        if (t > alt[gi]) alt[gi] = t;
        var id = I[z * Wx + x];
        soma[gi * 3] += cor[id * 3]; soma[gi * 3 + 1] += cor[id * 3 + 1]; soma[gi * 3 + 2] += cor[id * 3 + 2];
        cnt[gi]++;
      }
    }
    var cm = new Uint8Array(gw * gd * 3);
    for (var i = 0; i < gw * gd; i++) {
      if (!cnt[i]) continue;
      cm[i * 3] = soma[i * 3] / cnt[i]; cm[i * 3 + 1] = soma[i * 3 + 1] / cnt[i]; cm[i * 3 + 2] = soma[i * 3 + 2] / cnt[i];
    }
    return (scan._grupos[g] = { g: g, gw: gw, gd: gd, alt: alt, cor: cm });
  }

  var REGIAO = 32;   // grupos por lado em cada malha grossa

  /* Malha grossa de uma região (rx, rz) de 32×32 grupos */
  function malhaGrossa(scan, cam, gr, rx, rz, S) {
    S.limpar();
    var cc = baseCamera(cam), sx = cc.sx, sz = cc.sz, g = gr.g, gw = gr.gw, gd = gr.gd;
    var Wx = scan.Wx, Dz = scan.Dz;
    var gx0 = rx * REGIAO, gz0 = rz * REGIAO, gx1 = Math.min(gw, gx0 + REGIAO), gz1 = Math.min(gd, gz0 + REGIAO);
    var ox = gx0 * g, oz = gz0 * g;
    function quad(p, R, G, B) {                     // p = 4 vértices [x,y,z] em blocos, relativos a (ox,0,oz)
      S.garantir(4);
      var u16 = S.u16, u8 = S.u8, nv = S.nv;
      for (var v = 0; v < 4; v++) {
        var o = (nv + v) * 8, ob = (nv + v) * 16 + 12;
        u16[o] = Math.round(p[v][0] * SUB) + BIAS; u16[o + 1] = Math.round(p[v][1] * SUB) + BIAS; u16[o + 2] = Math.round(p[v][2] * SUB) + BIAS;
        u16[o + 3] = 0; u16[o + 4] = 0; u16[o + 5] = 0;
        u8[ob] = R; u8[ob + 1] = G; u8[ob + 2] = B; u8[ob + 3] = 255;
      }
      S.nv = nv + 4;
    }
    function alturaDe(gx, gz) {
      if (gx < 0 || gx >= gw || gz < 0 || gz >= gd) return -1;
      var a = gr.alt[gz * gw + gx];
      return a < -999 ? -1 : a;
    }
    for (var gz = gz0; gz < gz1; gz++) {
      for (var gx = gx0; gx < gx1; gx++) {
        var gi = gz * gw + gx, a = gr.alt[gi];
        if (a < -999) continue;
        var top = a + 1;
        var xa = gx * g - ox, xb = Math.min((gx + 1) * g, Wx) - ox, za = gz * g - oz, zb = Math.min((gz + 1) * g, Dz) - oz;
        var R = gr.cor[gi * 3], G = gr.cor[gi * 3 + 1], B = gr.cor[gi * 3 + 2];
        quad([[xa, top, za], [xa, top, zb], [xb, top, zb], [xb, top, za]], R, G, B);
        var bx = Math.max(0, alturaDe(gx + sx, gz) + 1);
        if (bx < top) {                              // lado voltado para +x ou -x
          var xs = sx > 0 ? xb : xa;
          quad([[xs, top, za], [xs, bx, za], [xs, bx, zb], [xs, top, zb]], (R * 0.6) | 0, (G * 0.6) | 0, (B * 0.6) | 0);
        }
        var bz = Math.max(0, alturaDe(gx, gz + sz) + 1);
        if (bz < top) {                              // lado voltado para +z ou -z
          var zs = sz > 0 ? zb : za;
          quad([[xa, top, zs], [xa, bz, zs], [xb, bz, zs], [xb, top, zs]], (R * 0.8) | 0, (G * 0.8) | 0, (B * 0.8) | 0);
        }
      }
    }
    return S;
  }

  var McScan = {
    carregar: carregar, decodificar: decodificar, percorrer: percorrer, indexar: indexar,
    baseCamera: baseCamera, horizonte: horizonte, contexto: contexto, Saida: Saida,
    configLuz: configLuz, calcularCores: calcularCores, construirGrupos: construirGrupos, malhaGrossa: malhaGrossa,
    REGIAO: REGIAO, BIAS: BIAS, retanguloTextura: retanguloTextura, SUB: SUB
  };
  if (typeof module !== "undefined" && module.exports) module.exports = McScan;
  else raiz.McScan = McScan;
})(typeof window !== "undefined" ? window : globalThis);
