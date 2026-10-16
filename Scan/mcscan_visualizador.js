(function (raiz) {
  "use strict";

  var BIAS = McScan.BIAS;
  var LIMITE_QUADS = 2500000;
  var ZOOM_DETALHE = 2;
  var ZOOM_MEDIO = 0.6;

  var VS = "#version 300 es\n" +
    "in vec4 aPos; in vec2 aUv; in vec4 aCol;\n" +
    "uniform vec3 uC, uR, uU, uF, uOrigin; uniform vec2 uPan, uScale; uniform float uDepth, uTempo, uVento;\n" +
    "out vec2 vUv; out vec4 vCol; out float vZ; out float vSn; out float vPd; out vec3 vW; flat out int vTx;\n" +
    "void main(){ float fv = step(32768.0, aPos.w); float fl = fv * step(0.95, aCol.a);\n" +
    "  float ampl = fv * (1.0 - fl) * aCol.a * 0.16 * uVento;\n" +
    "  vec3 wp = uOrigin + (aPos.xyz - " + BIAS + ".0) / " + McScan.SUB + ".0;\n" +
    "  float t = uTempo * 0.05;\n" +
    "  vec3 wv = ampl * vec3(sin(t*1.7 + wp.x*0.9 - wp.z*0.6 + wp.y*0.5), 0.15*sin(t*1.1 + wp.x*0.7), sin(t*1.3 + wp.z*0.8 + wp.x*0.4 + wp.y*0.6));\n" +
    "  vec3 d = wp + wv - uC;\n" +
    "  float zz = dot(d,uF)*uDepth;\n" +
    "  gl_Position = vec4((dot(d,uR)-uPan.x)*uScale.x, (dot(d,uU)-uPan.y)*uScale.y, zz, 1.0);\n" +
    "  float br = 1.0 + fl * uVento * 0.11 * sin(t*1.25 + wp.x*0.55 + wp.z*0.45 + wp.y*0.8);\n" +
    "  vUv = aUv; vCol = vec4(aCol.rgb * br, mix(aCol.a, 1.0, fv)); float a8 = aCol.a * 255.0; vSn = (1.0 - fv + fl) * step(abs(a8 - 244.0), 1.5); vPd = (1.0 - fv) * step(abs(a8 - 238.0), 1.5); vW = wp; vZ = zz; vTx = int(aPos.w - 32768.0*fv + 0.5); }\n";
  var FS = "#version 300 es\n" +
    "precision highp float;\n" +
    "in vec2 vUv; in vec4 vCol; in float vZ; in float vSn; in float vPd; in vec3 vW; flat in int vTx; uniform float uCinza, uPoca; uniform sampler2D uTex; uniform sampler2D uRect; uniform float uCorte; uniform float uSolido; uniform vec3 uTonSolido; uniform sampler2D uAnim; uniform sampler2D uSteps; uniform float uAnimOn; uniform float uTempo; uniform float uNeblina; uniform vec3 uCorNeblina; out vec4 o;\n" +
    "vec4 amostra(){\n" +
    "  vec2 ts = vec2(textureSize(uTex, 0)); vec2 px = vUv * ts;\n" +
    "  vec2 dx = dFdx(px), dy = dFdy(px);\n" +
    "  float rho = max(dot(dx, dx), dot(dy, dy));\n" +
    "  float L = clamp(0.5 * log2(max(rho, 1e-8)), 0.0, 4.0);\n" +
    "  float mt = 0.5 * exp2(ceil(L));\n" +
    "  vec4 r = texelFetch(uRect, ivec2(vTx & 2047, vTx >> 11), 0);\n" +
    "  if (uAnimOn > 0.5) { vec4 a = texelFetch(uAnim, ivec2(vTx & 2047, vTx >> 11), 0);\n" +
    "    if (a.y > 0.5) { float st = floor(mod(uTempo / a.z, a.y)); int k = int(a.x + st);\n" +
    "      vec2 fo = texelFetch(uSteps, ivec2(k & 2047, k >> 11), 0).xy; px += fo - r.xy; r.xy = fo; } }\n" +
    "  px = clamp(px, r.xy + mt, r.xy + r.zw - mt);\n" +
    "  return textureGrad(uTex, px / ts, dFdx(vUv), dFdy(vUv)); }\n" +
    "float hs(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }\n" +
    "float vn(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);\n" +
    "  return mix(mix(hs(i), hs(i + vec2(1.0, 0.0)), f.x), mix(hs(i + vec2(0.0, 1.0)), hs(i + vec2(1.0, 1.0)), f.x), f.y); }\n" +
    "vec3 poca(vec3 c){\n" +
    "  float n = vn(vW.xz * 0.55) * 0.62 + vn(vW.xz * 1.7 + 9.0) * 0.38;\n" +
    "  float m = smoothstep(0.50, 0.58, n) * uPoca;\n" +
    "  vec2 g = vW.xz * 3.2; vec2 ce = floor(g); float ph = fract(uTempo * 0.018 + hs(ce) * 3.7); vec2 cc = ce + 0.25 + 0.5 * vec2(hs(ce + 3.1), hs(ce + 7.7));\n" +
    "  float rd = length(g - cc); float anel = smoothstep(0.07, 0.0, abs(rd - ph * 0.62)) * (1.0 - ph) * m;\n" +
    "  vec3 molhado = c * (1.0 - 0.16 * uPoca);\n" +
    "  vec3 agua = mix(c * 0.42, uCorNeblina * vec3(0.92, 1.0, 1.12), 0.46) + vec3(0.10) * anel;\n" +
    "  return mix(molhado, agua, m); }\n" +
    "vec3 nevoa(vec3 c){ c = mix(c, vec3(dot(c, vec3(0.30, 0.59, 0.11))) * 0.88, uCinza); float fz = clamp(vZ * 0.5 + 0.5, 0.0, 1.0); float f = uNeblina * pow(smoothstep(0.32, 1.0, fz), 1.4); return mix(c, uCorNeblina, f); }\n" +
    "void main(){\n" +
    "  if (uSolido > 0.5) { o = vec4(nevoa(vCol.rgb * uTonSolido), 1.0); return; }\n" +
    "  vec4 t = amostra();\n" +
    "  if (uSolido < 0.5 && vCol.a > 0.97 && vCol.a < 0.995) {\n" +
    "    float q = smoothstep(0.55, 1.0, t.a); vec3 g = vCol.rgb * 0.19 * mix(1.0, 0.35, q);\n" +
    "    if (t.a > 0.25 && t.a < 0.9) g *= mix(vec3(1.0), t.rgb * 1.3, 0.5);\n" +
    "    o = vec4(nevoa(g), 1.0); return; }\n" +
    "  if (uCorte > 0.0) { if (t.a < uCorte) discard; vec3 c = t.rgb * vCol.rgb;\n" +
    "    if (vSn > 0.01) { float lu = dot(t.rgb, vec3(0.33)); vec3 lz = mix(vCol.rgb, vec3(dot(vCol.rgb, vec3(0.33))) * vec3(0.96, 1.0, 1.06), 0.6); c = mix(c, vec3(0.94, 0.97, 1.0) * (0.86 + 0.30 * lu) * lz, vSn * 0.93); }\n" +
    "    if (vPd > 0.5) c = poca(c);\n" +
    "    o = vec4(nevoa(c), 1.0); }\n" +
    "  else { if (t.a < 0.02) discard; o = vec4(nevoa(t.rgb * vCol.rgb), t.a * vCol.a); } }\n";

  var VS_TELA = "#version 300 es\nout vec2 vP;\nvoid main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); vP = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }\n";
  var FS_CEU = "#version 300 es\nprecision highp float;\nin vec2 vP; uniform vec3 uTopo, uHorizonte; out vec4 o;\n" +
    "void main(){ float k = pow(clamp(vP.y, 0.0, 1.0), 0.8); o = vec4(mix(uHorizonte, uTopo, k), 1.0); }\n";
  var FS_BRILHO = "#version 300 es\nprecision highp float;\nin vec2 vP; uniform sampler2D uCena; uniform vec2 uPx; out vec4 o;\n" +
    "void main(){ vec3 c = vec3(0.0);\n" +
    "  for (int i = 0; i < 4; i++) { vec2 d = vec2(float(i & 1) - 0.5, float(i >> 1) - 0.5) * uPx * 2.0; vec3 s = texture(uCena, vP + d).rgb;\n" +
    "    float l = max(s.r, max(s.g, s.b)); c += s * smoothstep(0.62, 0.95, l); }\n" +
    "  o = vec4(c * 0.25, 1.0); }\n";
  var FS_BORRA = "#version 300 es\nprecision highp float;\nin vec2 vP; uniform sampler2D uImg; uniform vec2 uDir; out vec4 o;\n" +
    "void main(){ vec3 c = texture(uImg, vP).rgb * 0.2270270270;\n" +
    "  c += (texture(uImg, vP + uDir * 1.3846153846).rgb + texture(uImg, vP - uDir * 1.3846153846).rgb) * 0.3162162162;\n" +
    "  c += (texture(uImg, vP + uDir * 3.2307692308).rgb + texture(uImg, vP - uDir * 3.2307692308).rgb) * 0.0702702703;\n" +
    "  o = vec4(c, 1.0); }\n";
  var FS_JUNTA = "#version 300 es\nprecision highp float;\nin vec2 vP; uniform sampler2D uCena, uBrilho; uniform float uForca; out vec4 o;\n" +
    "void main(){ o = vec4(texture(uCena, vP).rgb + texture(uBrilho, vP).rgb * uForca, 1.0); }\n";

  var VS_TEMPO = "#version 300 es\nprecision highp float;\nuniform float uT, uEsc, uModo; uniform vec2 uPx; out vec2 vL; out float vA;\n" +
    "float h(float n){ return fract(sin(n * 12.9898) * 43758.5453); }\n" +
    "void main(){ int id = gl_VertexID / 6; int k = gl_VertexID - id * 6; float fi = float(id);\n" +
    "  vec2 cq = vec2((k == 1 || k == 2 || k == 4) ? 1.0 : 0.0, (k == 2 || k == 4 || k == 5) ? 1.0 : 0.0); vL = cq;\n" +
    "  float d = h(fi * 1.31), ph; vec2 c, p;\n" +
    "  if (uModo < 0.5) {\n" +
    "    ph = fract(h(fi * 2.7) + uT * (0.50 + 0.55 * d)); float y = 1.15 - ph * 2.3, x = h(fi * 5.1) * 2.5 - 1.25 + ph * 0.23;\n" +
    "    vec2 dir = normalize(vec2(0.20 * uPx.y, -1.0 * uPx.x)); vec2 dpx = normalize(vec2(0.20, -1.0));\n" +
    "    float len = (10.0 + 20.0 * d) * uEsc, w = (1.1 + 0.6 * d) * uEsc; vec2 pe = vec2(-dpx.y, dpx.x);\n" +
    "    p = vec2(x, y) + (-dpx * len * cq.y + pe * w * (cq.x - 0.5)) * uPx; vA = 0.16 + 0.30 * d; }\n" +
    "  else {\n" +
    "    ph = fract(h(fi * 2.7) + uT * (0.045 + 0.06 * d)); float y = 1.08 - ph * 2.16;\n" +
    "    float x = h(fi * 5.1) * 2.5 - 1.25 + 0.05 * sin(uT * (0.7 + d) + fi) + ph * 0.10;\n" +
    "    float sz = (2.0 + 4.2 * d) * uEsc; p = vec2(x, y) + (cq - 0.5) * sz * uPx; vA = 0.45 + 0.45 * d; }\n" +
    "  gl_Position = vec4(p, 0.0, 1.0); }\n";
  var FS_TEMPO = "#version 300 es\nprecision highp float;\nin vec2 vL; in float vA; uniform float uModo; uniform vec3 uCor; out vec4 o;\n" +
    "void main(){ float a = vA;\n" +
    "  if (uModo < 0.5) a *= 0.25 + 0.75 * vL.y; else a *= smoothstep(1.0, 0.55, length(vL - 0.5) * 2.0);\n" +
    "  o = vec4(uCor, a); }\n";

  function compilar(gl, tipo, fonte) {
    var s = gl.createShader(tipo);
    gl.shaderSource(s, fonte);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("Shader: " + gl.getShaderInfoLog(s));
    return s;
  }

  async function criar(canvas, scan, opc) {
    opc = opc || {};
    try { McScan.indexar(scan); } catch (e) { throw new Error(((e && e.message) || e) + " [etapa: indexar " + (scan.cab.n_colunas||0) + " colunas]"); }
    var cab = scan.cab, area = cab.area, ch = cab.chunks, ncx = ch.ncx, ncz = ch.ncz;
    var Wx = scan.Wx, Dz = scan.Dz, H = scan.H;
    var gl = canvas.getContext("webgl2", { antialias: false, alpha: false, preserveDrawingBuffer: !!opc.preservar });
    if (!gl) throw new Error("Este navegador não suporta WebGL2.");
    var prog = gl.createProgram();
    gl.attachShader(prog, compilar(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, compilar(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("Programa: " + gl.getProgramInfoLog(prog));
    var loc = {};
    ["uC", "uR", "uU", "uF", "uOrigin", "uPan", "uScale", "uDepth", "uTex", "uRect", "uCorte", "uSolido", "uTonSolido", "uAnim", "uSteps", "uAnimOn", "uTempo", "uVento", "uNeblina", "uCorNeblina", "uCinza", "uPoca"].forEach(function (n) { loc[n] = gl.getUniformLocation(prog, n); });
    var aPos = gl.getAttribLocation(prog, "aPos"), aUv = gl.getAttribLocation(prog, "aUv"), aCol = gl.getAttribLocation(prog, "aCol");

    function criarTela(fonte, nomes) {
      var pg = gl.createProgram();
      gl.attachShader(pg, compilar(gl, gl.VERTEX_SHADER, VS_TELA));
      gl.attachShader(pg, compilar(gl, gl.FRAGMENT_SHADER, fonte));
      gl.linkProgram(pg);
      if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) throw new Error("Programa: " + gl.getProgramInfoLog(pg));
      var u = {}; nomes.forEach(function (n) { u[n] = gl.getUniformLocation(pg, n); });
      return { pg: pg, u: u };
    }
    var pCeu = null, pBrilho = null, pBorra = null, pJunta = null, vaoTela = gl.createVertexArray();
    try {
      pCeu = criarTela(FS_CEU, ["uTopo", "uHorizonte"]);
      pBrilho = criarTela(FS_BRILHO, ["uCena", "uPx"]);
      pBorra = criarTela(FS_BORRA, ["uImg", "uDir"]);
      pJunta = criarTela(FS_JUNTA, ["uCena", "uBrilho", "uForca"]);
    } catch (e) { console.error(e); pCeu = pBrilho = pBorra = pJunta = null; }
    var pTempo = null;
    try {
      pTempo = (function () {
        var pg = gl.createProgram();
        gl.attachShader(pg, compilar(gl, gl.VERTEX_SHADER, VS_TEMPO)); gl.attachShader(pg, compilar(gl, gl.FRAGMENT_SHADER, FS_TEMPO));
        gl.linkProgram(pg);
        if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) throw new Error("Programa: " + gl.getProgramInfoLog(pg));
        var u = {}; ["uT", "uEsc", "uModo", "uPx", "uCor"].forEach(function (n) { u[n] = gl.getUniformLocation(pg, n); });
        return { pg: pg, u: u };
      })();
    } catch (e) { console.error(e); pTempo = null; }
    var fb = { cena: null, w: 0, h: 0, brilho: [null, null] };
    function alvo(w, h, profundidade) {
      var t = gl.createTexture(), f = gl.createFramebuffer();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.bindFramebuffer(gl.FRAMEBUFFER, f);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
      var rb = null;
      if (profundidade) {
        rb = gl.createRenderbuffer();
        gl.bindRenderbuffer(gl.RENDERBUFFER, rb);
        gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, w, h);
        gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, rb);
      }
      var ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      return { t: t, f: f, rb: rb, w: w, h: h, ok: ok };
    }
    function soltarAlvo(a) { if (!a) return; gl.deleteTexture(a.t); gl.deleteFramebuffer(a.f); if (a.rb) gl.deleteRenderbuffer(a.rb); }
    function prepararAlvos(w, h) {
      if (fb.cena && fb.w === w && fb.h === h) return fb.cena.ok;
      soltarAlvo(fb.cena); soltarAlvo(fb.brilho[0]); soltarAlvo(fb.brilho[1]);
      var bw = Math.max(1, w >> 2), bh = Math.max(1, h >> 2);
      fb.cena = alvo(w, h, true); fb.brilho = [alvo(bw, bh, false), alvo(bw, bh, false)]; fb.w = w; fb.h = h;
      return fb.cena.ok && fb.brilho[0].ok && fb.brilho[1].ok;
    }

    var bmp; try { bmp = await createImageBitmap(new Blob([scan.atlasPng], { type: "image/png" }),
      { premultiplyAlpha: "none", colorSpaceConversion: "none" }); }
    catch (e) { throw new Error(((e && e.message) || e) + " [etapa: atlas de texturas]"); }
    var tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    var niv = 4;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAX_LEVEL, niv);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    var texR = gl.createTexture();
    (function () {
      var nT = cab.atlas.rects ? cab.atlas.rects.length : (cab.atlas.n || cab.atlas.colunas * cab.atlas.linhas);
      var W = 2048, Hh = Math.max(1, Math.ceil(nT / W)), dados = new Float32Array(W * Hh * 4);
      for (var t = 0; t < nT; t++) { var rc = McScan.retanguloTextura(cab.atlas, t); dados.set(rc, t * 4); }
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, texR);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, W, Hh, 0, gl.RGBA, gl.FLOAT, dados);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
    })();
    var texA = gl.createTexture(), texS = gl.createTexture(), temAnim = false;
    (function () {
      var an = cab.atlas.anim;
      if (!an || !an.length || !cab.atlas.rects) return;
      var nT = cab.atlas.rects.length, W = 2048, Hh = Math.max(1, Math.ceil(nT / W)), tab = new Float32Array(W * Hh * 4);
      var total = 0; an.forEach(function (a) { total += a.f.length; });
      var Hs = Math.max(1, Math.ceil(total / W)), passos = new Float32Array(W * Hs * 4), k = 0;
      an.forEach(function (a) {
        tab.set([k, a.f.length, a.dt, 0], a.tx * 4);
        a.f.forEach(function (ri) { var rc = cab.atlas.rects[ri]; passos[k * 4] = rc[0]; passos[k * 4 + 1] = rc[1]; k++; });
      });
      function subir(t, unidade, w, h, d) {
        gl.activeTexture(gl.TEXTURE0 + unidade); gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, w, h, 0, gl.RGBA, gl.FLOAT, d);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      }
      subir(texA, 2, W, Hh, tab); subir(texS, 3, W, Hs, passos);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
      temAnim = true;
    })();
    (function () {
      var c2 = document.createElement("canvas");
      c2.width = bmp.width; c2.height = bmp.height;
      var cx = c2.getContext("2d", { willReadFrequently: true });
      cx.drawImage(bmp, 0, 0);
      McScan.calcularCores(scan, cx.getImageData(0, 0, bmp.width, bmp.height).data);
    })();

    var estado = {
      camera: opc.camera | 0, zoom: 1, panX: 0, panY: 0, base: null, modo: 2,
      animar: temAnim && opc.animar !== false, fundo: opc.fundo || [0.53, 0.72, 0.93], semOclusao: !!opc.semOclusao,
      noite: 0, tempo: "", termo: -1, vento: opc.vento !== false, neblina: opc.neblina !== false, ceu: opc.ceu !== false, brilho: opc.brilho !== false
    };
    var CEU = { nascer: { topo: [0.40, 0.52, 0.86], hor: [1.0, 0.82, 0.74] }, poente: { topo: [0.30, 0.36, 0.72], hor: [0.99, 0.72, 0.52] }, dia: { topo: [0.22, 0.43, 0.88], hor: [0.80, 0.89, 0.97] }, noite: { topo: [0.012, 0.022, 0.07], hor: [0.07, 0.10, 0.20] } };
    var CEU_TEMPO = { chuva: { dia: { topo: [0.40, 0.44, 0.50], hor: [0.62, 0.65, 0.69] }, noite: { topo: [0.020, 0.030, 0.060], hor: [0.08, 0.10, 0.14] } },
                      neve:  { dia: { topo: [0.62, 0.67, 0.74], hor: [0.84, 0.86, 0.89] }, noite: { topo: [0.05, 0.06, 0.10], hor: [0.16, 0.18, 0.24] } } };
    function corCeu() {
      var b = estado.noite ? CEU.noite : (estado.clima === "poente" ? CEU.poente : estado.clima === "nascer" ? CEU.nascer : CEU.dia);
      var tp = CEU_TEMPO[estado.tempo];
      if (!tp) return b;
      var alvo = estado.noite ? tp.noite : tp.dia, k = estado.noite ? 0.8 : (estado.clima === "dia" ? 0.8 : 0.6);
      return { topo: [0, 1, 2].map(function (i) { return b.topo[i] + (alvo.topo[i] - b.topo[i]) * k; }), hor: [0, 1, 2].map(function (i) { return b.hor[i] + (alvo.hor[i] - b.hor[i]) * k; }) };
    }
    var dpr = 1, quadroN = 0, pendentes = 0;
    var cache = new Map();
    var totalQuads = 0;
    var S = { opaco: new McScan.Saida(), transl: new McScan.Saida() };
    var centro = [Wx / 2, H / 2, Dz / 2];

    var idxBuf = null, idxCap = 0;
    function indicesPara(nq) {
      if (nq > idxCap) {
        idxCap = Math.max(nq, idxCap * 2, 65536);
        var a = new Uint32Array(idxCap * 6);
        for (var q = 0; q < idxCap; q++) {
          var b = q * 4, o = q * 6;
          a[o] = b; a[o + 1] = b + 1; a[o + 2] = b + 2; a[o + 3] = b; a[o + 4] = b + 2; a[o + 5] = b + 3;
        }
        idxBuf = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, a, gl.STATIC_DRAW);
      }
      return idxBuf;
    }

    function enviar(saida) {
      var nq = saida.quads();
      if (!nq) return null;
      var vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      var vb = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, vb);
      gl.bufferData(gl.ARRAY_BUFFER, saida.bytes(), gl.STATIC_DRAW);
      gl.enableVertexAttribArray(aPos); gl.vertexAttribPointer(aPos, 4, gl.UNSIGNED_SHORT, false, 16, 0);
      gl.enableVertexAttribArray(aUv); gl.vertexAttribPointer(aUv, 2, gl.UNSIGNED_SHORT, true, 16, 8);
      gl.enableVertexAttribArray(aCol); gl.vertexAttribPointer(aCol, 4, gl.UNSIGNED_BYTE, true, 16, 12);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indicesPara(nq));
      gl.bindVertexArray(null);
      return { vao: vao, vb: vb, n: nq * 6, nq: nq };
    }
    function liberar(m) {
      [m.op, m.tr].forEach(function (p) { if (p) { gl.deleteVertexArray(p.vao); gl.deleteBuffer(p.vb); } });
      totalQuads -= m.quads;
    }
    function limparCache() {
      cache.forEach(liberar);
      cache.clear();
      totalQuads = 0;
    }

    function ctx() { return McScan.contexto(scan, estado.camera, { semOclusao: estado.semOclusao }); }

    function construirDetalhe(i, j) {
      ctx().malhaChunk(i, j, S);
      var m = { op: enviar(S.opaco), tr: enviar(S.transl), origem: [(ch.cx0 + i) * 16 - area.x1, 0, (ch.cz0 + j) * 16 - area.z1], solido: 0, uso: quadroN };
      m.quads = (m.op ? m.op.nq : 0) + (m.tr ? m.tr.nq : 0);
      totalQuads += m.quads;
      return m;
    }
    function construirGrossa(g, rx, rz) {
      var gr = McScan.construirGrupos(scan, g);
      McScan.malhaGrossa(scan, estado.camera, gr, rx, rz, S.opaco);
      var m = { op: enviar(S.opaco), tr: null, origem: [rx * McScan.REGIAO * g, 0, rz * McScan.REGIAO * g], solido: 1, uso: quadroN };
      m.quads = m.op ? m.op.nq : 0;
      totalQuads += m.quads;
      return m;
    }

    function projetar(x, y, z) {
      var b = estado.base, dx = x - centro[0], dy = y - centro[1], dz = z - centro[2];
      return [dx * b.r[0] + dy * b.r[1] + dz * b.r[2], dx * b.u[0] + dy * b.u[1] + dz * b.u[2]];
    }
    function caixaVisivel(x0, y0, z0, x1, y1, z1, vp) {
      var minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
      for (var i = 0; i < 8; i++) {
        var p = projetar(i & 1 ? x1 : x0, i & 2 ? y1 : y0, i & 4 ? z1 : z0);
        if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
      }
      if (maxX < vp[0] || minX > vp[2] || maxY < vp[1] || minY > vp[3]) return null;
      return Math.hypot((minX + maxX) / 2 - estado.panX, (minY + maxY) / 2 - estado.panY);
    }

    function alturaUtil() {
      var m = 0;
      for (var i = 0; i < scan.topoChunk.length; i++) if (scan.topoChunk[i] > m) m = scan.topoChunk[i];
      return Math.max(8, Math.min(H, m + 3));
    }
    function enquadrar() {
      var b = estado.base, d = [Wx, alturaUtil(), Dz], c = centro;
      var minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
      for (var i = 0; i < 8; i++) {
        var p = [(i & 1 ? d[0] : 0) - c[0], (i & 2 ? d[1] : 0) - c[1], (i & 4 ? d[2] : 0) - c[2]];
        var x = p[0] * b.r[0] + p[1] * b.r[1] + p[2] * b.r[2];
        var y = p[0] * b.u[0] + p[1] * b.u[1] + p[2] * b.u[2];
        minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      }
      estado.panX = (minX + maxX) / 2;
      estado.panY = (minY + maxY) / 2;
      estado.zoom = Math.min(canvas.width / (maxX - minX), canvas.height / (maxY - minY)) * 0.94;
      estado.zoomMin = estado.zoom * 0.4;
      estado.zoomMax = Math.max(estado.zoom * 80, 64 * dpr);
    }

    function ajustarTamanho() {
      if (estado.forca) {
        dpr = estado.forca.w / Math.max(1, canvas.clientWidth);
        if (canvas.width !== estado.forca.w || canvas.height !== estado.forca.h) { canvas.width = estado.forca.w; canvas.height = estado.forca.h; return true; }
        return false;
      }
      var nat = Math.min(window.devicePixelRatio || 1, 2);
      var ss = nat >= 2 ? 1.5 : 2;
      var maxL = Math.max(canvas.clientWidth, canvas.clientHeight) || 1;
      dpr = Math.min(nat * ss, 4096 / maxL);
      var w = Math.max(1, Math.round(canvas.clientWidth * dpr)), h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; return true; }
      return false;
    }

    var pendente = false;
    function pedir() {
      if (pendente) return;
      pendente = true;
      requestAnimationFrame(function () { pendente = false; quadro(); });
    }

    function escolherModo(z) {
      var m = estado.modo;
      if (ncx * ncz <= 700) return 0;
      if (z >= ZOOM_DETALHE * (m === 0 ? 0.88 : 1)) return 0;
      if (z >= ZOOM_MEDIO * (m <= 1 ? 0.88 : 1)) return 1;
      return 2;
    }

    function itensVisiveis(modo, vp) {
      var itens = [], i, j, x0, z0, d;
      if (modo === 0) {
        for (j = 0; j < ncz; j++) {
          for (i = 0; i < ncx; i++) {
            var t = scan.topoChunk[j * ncx + i];
            if (t < 0) continue;
            x0 = (ch.cx0 + i) * 16 - area.x1; z0 = (ch.cz0 + j) * 16 - area.z1;
            d = caixaVisivel(Math.max(x0, 0), 0, Math.max(z0, 0), Math.min(x0 + 16, Wx), t + 2, Math.min(z0 + 16, Dz), vp);
            if (d !== null) itens.push({ chave: "d," + estado.camera + "," + i + "," + j, i: i, j: j, d: d });
          }
        }
      } else {
        var g = modo === 1 ? 4 : 16, gr = McScan.construirGrupos(scan, g), R = McScan.REGIAO;
        var nrx = Math.ceil(gr.gw / R), nrz = Math.ceil(gr.gd / R);
        for (j = 0; j < nrz; j++) {
          for (i = 0; i < nrx; i++) {
            x0 = i * R * g; z0 = j * R * g;
            d = caixaVisivel(x0, 0, z0, Math.min(x0 + R * g, Wx), H + 1, Math.min(z0 + R * g, Dz), vp);
            if (d !== null) itens.push({ chave: "g" + g + "," + estado.camera + "," + i + "," + j, g: g, i: i, j: j, d: d });
          }
        }
      }
      return itens;
    }

    function quadro() {
      ajustarTamanho();
      quadroN++;
      var W = canvas.width, Hh = canvas.height;
      var modo = escolherModo(estado.zoom / dpr);
      estado.modo = modo;
      var m = 24 / estado.zoom;
      var hw = W / (2 * estado.zoom) + m, hh = Hh / (2 * estado.zoom) + m;
      var vp = [estado.panX - hw, estado.panY - hh, estado.panX + hw, estado.panY + hh];
      var itens = itensVisiveis(modo, vp);
      itens.sort(function (a, b) { return a.d - b.d; });

      var t0 = performance.now(), falta = 0;
      for (var k = 0; k < itens.length; k++) {
        var it = itens[k];
        if (cache.has(it.chave)) continue;
        if (performance.now() - t0 > 12) { falta++; continue; }
        try {
          cache.set(it.chave, modo === 0 ? construirDetalhe(it.i, it.j) : construirGrossa(it.g, it.i, it.j));
        } catch (e) {
          console.error(e);
          cache.set(it.chave, { op: null, tr: null, quads: 0, origem: [0, 0, 0], solido: 0, uso: quadroN });
        }
      }
      pendentes = falta;

      if (totalQuads > LIMITE_QUADS) {
        var usadas = {};
        itens.forEach(function (it) { usadas[it.chave] = 1; });
        var velhas = [];
        cache.forEach(function (v, c) { if (!usadas[c]) velhas.push([c, v]); });
        velhas.sort(function (a, b) { return a[1].uso - b[1].uso; });
        for (var e = 0; e < velhas.length && totalQuads > LIMITE_QUADS * 0.8; e++) {
          liberar(velhas[e][1]); cache.delete(velhas[e][0]);
        }
      }

      desenhar(itens);
      if (opc.aoQuadro) opc.aoQuadro({ modo: modo, pendentes: pendentes, quads: totalQuads });
      if (falta) pedir();
    }

    function desenhar(itens) {
      var comBrilho = !!(pBrilho && estado.noite && estado.brilho && prepararAlvos(canvas.width, canvas.height));
      if (comBrilho) gl.bindFramebuffer(gl.FRAMEBUFFER, fb.cena.f); else gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(estado.fundo[0], estado.fundo[1], estado.fundo[2], 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      if (estado.ceu && pCeu) {
        var cc = corCeu();
        gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND); gl.depthMask(false);
        gl.useProgram(pCeu.pg); gl.uniform3fv(pCeu.u.uTopo, cc.topo); gl.uniform3fv(pCeu.u.uHorizonte, cc.hor);
        gl.bindVertexArray(vaoTela); gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.depthMask(true);
      }
      var b = estado.base;
      var raio = Math.hypot(Wx, H, Dz) / 2 * 1.05;
      gl.useProgram(prog);
      gl.uniform3f(loc.uC, centro[0], centro[1], centro[2]);
      gl.uniform3fv(loc.uR, b.r); gl.uniform3fv(loc.uU, b.u); gl.uniform3fv(loc.uF, b.f);
      gl.uniform2f(loc.uPan, estado.panX, estado.panY);
      gl.uniform2f(loc.uScale, 2 * estado.zoom / canvas.width, 2 * estado.zoom / canvas.height);
      gl.uniform1f(loc.uDepth, 1 / raio);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.uniform1i(loc.uTex, 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, texR); gl.uniform1i(loc.uRect, 1);
      gl.uniform1f(loc.uAnimOn, estado.animar ? 1 : 0);
      gl.uniform1f(loc.uTempo, performance.now() / 50);
      gl.uniform1f(loc.uVento, estado.vento ? 1 : 0);
      gl.uniform1f(loc.uPoca, estado.tempo === "chuva" ? 1 : 0);
      gl.uniform1f(loc.uCinza, estado.tempo === "chuva" ? (estado.noite ? 0.18 : 0.38) : estado.tempo === "neve" ? (estado.noite ? 0.10 : 0.22) : 0);
      var hz = corCeu().hor;
      gl.uniform1f(loc.uNeblina, estado.neblina ? (estado.noite ? 0.30 : 0.34) : 0);
      gl.uniform3f(loc.uCorNeblina, hz[0], hz[1], hz[2]);
      if (estado.animar) {
        gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, texA); gl.uniform1i(loc.uAnim, 2);
        gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, texS); gl.uniform1i(loc.uSteps, 3);
        gl.uniform1f(loc.uTempo, performance.now() / 50);
      } else { gl.uniform1i(loc.uAnim, 2); gl.uniform1i(loc.uSteps, 3); }
      gl.activeTexture(gl.TEXTURE0);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LESS);
      gl.disable(gl.BLEND); gl.depthMask(true); gl.uniform1f(loc.uCorte, 0.5);
      var prontos = [];
      for (var k = 0; k < itens.length; k++) {
        var mm = cache.get(itens[k].chave);
        if (!mm) continue;
        mm.uso = quadroN;
        prontos.push(mm);
        if (!mm.op) continue;
        gl.uniform3fv(loc.uOrigin, mm.origem);
        gl.uniform1f(loc.uSolido, mm.solido);
        var ton = estado.tonSolido || [1, 1, 1]; gl.uniform3f(loc.uTonSolido, ton[0], ton[1], ton[2]);
        gl.bindVertexArray(mm.op.vao);
        gl.drawElements(gl.TRIANGLES, mm.op.n, gl.UNSIGNED_INT, 0);
      }
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.depthMask(false); gl.uniform1f(loc.uCorte, 0.0);
      for (var q = 0; q < prontos.length; q++) {
        var tm = prontos[q];
        if (!tm.tr) continue;
        gl.uniform3fv(loc.uOrigin, tm.origem);
        gl.uniform1f(loc.uSolido, 0);
        gl.bindVertexArray(tm.tr.vao);
        gl.drawElements(gl.TRIANGLES, tm.tr.n, gl.UNSIGNED_INT, 0);
      }
      gl.depthMask(true); gl.disable(gl.BLEND);
      gl.bindVertexArray(null);
      if (comBrilho) brilhoFinal();
      if (estado.tempo && pTempo) desenharTempo();
    }

    function desenharTempo() {
      var chuva = estado.tempo === "chuva", n = chuva ? 1100 : 750;
      gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false);
      gl.useProgram(pTempo.pg);
      gl.uniform1f(pTempo.u.uT, (performance.now() % 600000) / 1000);
      gl.uniform1f(pTempo.u.uEsc, Math.max(0.6, canvas.height / 800));
      gl.uniform1f(pTempo.u.uModo, chuva ? 0 : 1);
      gl.uniform2f(pTempo.u.uPx, 2 / canvas.width, 2 / canvas.height);
      var c = chuva ? [0.78, 0.86, 1.0] : [0.97, 0.98, 1.0], f = estado.noite ? 0.55 : 1;
      gl.uniform3f(pTempo.u.uCor, c[0] * f, c[1] * f, c[2] * f);
      gl.bindVertexArray(vaoTela);
      gl.drawArrays(gl.TRIANGLES, 0, n * 6);
      gl.bindVertexArray(null); gl.depthMask(true); gl.disable(gl.BLEND);
    }

    function brilhoFinal() {
      var bw = fb.brilho[0].w, bh = fb.brilho[0].h;
      gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND);
      gl.bindVertexArray(vaoTela);
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb.brilho[0].f); gl.viewport(0, 0, bw, bh);
      gl.useProgram(pBrilho.pg); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, fb.cena.t);
      gl.uniform1i(pBrilho.u.uCena, 0); gl.uniform2f(pBrilho.u.uPx, 1 / fb.w, 1 / fb.h);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.useProgram(pBorra.pg); gl.uniform1i(pBorra.u.uImg, 0);
      for (var rodada = 0; rodada < 2; rodada++) {
        var r = 1 + rodada * 1.8;
        gl.bindFramebuffer(gl.FRAMEBUFFER, fb.brilho[1].f); gl.bindTexture(gl.TEXTURE_2D, fb.brilho[0].t);
        gl.uniform2f(pBorra.u.uDir, r / bw, 0); gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.bindFramebuffer(gl.FRAMEBUFFER, fb.brilho[0].f); gl.bindTexture(gl.TEXTURE_2D, fb.brilho[1].t);
        gl.uniform2f(pBorra.u.uDir, 0, r / bh); gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(pJunta.pg);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, fb.cena.t); gl.uniform1i(pJunta.u.uCena, 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, fb.brilho[0].t); gl.uniform1i(pJunta.u.uBrilho, 1);
      gl.uniform1f(pJunta.u.uForca, 1.1);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.bindVertexArray(null);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, texR);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
    }

    var ponteiros = new Map(), distAnt = 0;
    function posCanvas(e) {
      var r = canvas.getBoundingClientRect();
      return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height];
    }
    function zoomEm(mx, my, fator) {
      var z0 = estado.zoom, z1 = Math.min(estado.zoomMax, Math.max(estado.zoomMin, z0 * fator));
      var wx = estado.panX + (mx - canvas.width / 2) / z0, wy = estado.panY - (my - canvas.height / 2) / z0;
      estado.zoom = z1;
      estado.panX = wx - (mx - canvas.width / 2) / z1;
      estado.panY = wy + (my - canvas.height / 2) / z1;
      pedir();
    }
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerdown", function (e) {
      canvas.setPointerCapture(e.pointerId);
      ponteiros.set(e.pointerId, posCanvas(e));
      if (ponteiros.size === 2) { var p = Array.from(ponteiros.values()); distAnt = Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]); }
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!ponteiros.has(e.pointerId)) return;
      var ant = ponteiros.get(e.pointerId), atual = posCanvas(e);
      ponteiros.set(e.pointerId, atual);
      if (ponteiros.size === 1) {
        estado.panX -= (atual[0] - ant[0]) / estado.zoom;
        estado.panY += (atual[1] - ant[1]) / estado.zoom;
        pedir();
      } else if (ponteiros.size === 2) {
        var p = Array.from(ponteiros.values());
        var dist = Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]);
        if (distAnt > 0) zoomEm((p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2, dist / distAnt);
        distAnt = dist;
      }
    });
    function soltar(e) { ponteiros.delete(e.pointerId); distAnt = 0; }
    canvas.addEventListener("pointerup", soltar);
    canvas.addEventListener("pointercancel", soltar);
    canvas.addEventListener("wheel", function (e) {
      e.preventDefault();
      var p = posCanvas(e);
      zoomEm(p[0], p[1], Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });
    window.addEventListener("resize", pedir);

    var relogio = 0;
    function ligarRelogio() {
      clearInterval(relogio); relogio = 0;
      if (estado.animar || estado.vento || estado.tempo) relogio = setInterval(function () { if (!document.hidden) pedir(); }, 50);
    }
    ligarRelogio();
    estado.base = McScan.baseCamera(estado.camera);
    ajustarTamanho();
    enquadrar();
    quadro();

    return {
      estado: estado,
      redesenhar: pedir,
      recentrar: function () { ajustarTamanho(); enquadrar(); pedir(); },
      girar: function (passo) {
        estado.camera = (estado.camera + (passo || 1) + 4) & 3;
        estado.base = McScan.baseCamera(estado.camera);
        limparCache();
        enquadrar();
        pedir();
      },
      estilo: function (c) {
        if (c) { ["vento", "neblina", "ceu", "brilho"].forEach(function (k) { if (c[k] != null) estado[k] = !!c[k]; }); ligarRelogio(); pedir(); }
        return { vento: estado.vento, neblina: estado.neblina, ceu: estado.ceu, brilho: estado.brilho };
      },
      capturar: async function (o) {
        var W = Math.max(16, Math.min(8192, Math.round(o.largura))), Hh = Math.max(16, Math.min(8192, Math.round(o.altura)));
        var salvo = { w: canvas.width, zoom: estado.zoom, panX: estado.panX, panY: estado.panY, zmin: estado.zoomMin, zmax: estado.zoomMax };
        var c2 = document.createElement("canvas");
        try {
          estado.forca = { w: W, h: Hh };
          ajustarTamanho();
          if (o.inteiro) enquadrar(); else estado.zoom = salvo.zoom * (W / salvo.w);
          for (var i = 0; i < 3000; i++) {
            if (o.cancelado && o.cancelado()) throw new Error("cancelado");
            quadro();
            if (pendentes === 0) break;
            if (i % 4 === 3) await new Promise(function (r) { setTimeout(r, 0); });
          }
          quadro();
          c2.width = W; c2.height = Hh;
          c2.getContext("2d").drawImage(canvas, 0, 0);
        } finally {
          estado.forca = null;
          ajustarTamanho();
          estado.zoom = salvo.zoom; estado.panX = salvo.panX; estado.panY = salvo.panY; estado.zoomMin = salvo.zmin; estado.zoomMax = salvo.zmax;
          pedir();
        }
        return c2;
      },
      proporcaoMapa: function () {
        var b = estado.base, d = [Wx, alturaUtil(), Dz], c = centro, minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
        for (var i = 0; i < 8; i++) {
          var p = [(i & 1 ? d[0] : 0) - c[0], (i & 2 ? d[1] : 0) - c[1], (i & 4 ? d[2] : 0) - c[2]];
          var x = p[0] * b.r[0] + p[1] * b.r[1] + p[2] * b.r[2], y = p[0] * b.u[0] + p[1] * b.u[1] + p[2] * b.u[2];
          minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
        }
        return (maxX - minX) / (maxY - minY);
      },
      temAnimacao: temAnim,
      animar: function (lig) { estado.animar = temAnim && !!lig; ligarRelogio(); pedir(); return estado.animar; },
      luz: function (cfg) {
        var c = McScan.configLuz(cfg);
        var chave = [c.az, c.elev, c.noite, c.pos, c.termo, c.tempo].join("_");
        if (chave !== estado.chaveLuz) {
          estado.chaveLuz = chave; scan._ctx = {};
          if (scan._rgba) { McScan.calcularCores(scan, scan._rgba); scan._grupos = {}; }
          limparCache();
        }
        estado.tempo = c.tempo; estado.termo = c.termo; ligarRelogio();
        estado.noite = c.noite ? 1 : 0; estado.pos = c.pos; estado.clima = (c.pos === "o" || c.pos === "s") ? "poente" : ((c.pos === "n" || c.pos === "l") ? "nascer" : "dia");
        estado.fundo = c.noite ? [0.025, 0.04, 0.10] : [0.53, 0.72, 0.93];
        estado.tonSolido = c.noite ? [0.30, 0.37, 0.58] : (estado.clima === "poente" ? [1.10, 0.95, 0.80] : estado.clima === "nascer" ? [1.06, 0.97, 0.90] : [1.06, 1.0, 0.92]);
        pedir();
        return c;
      },
      definirZoom: function (pxPorBloco) { estado.zoom = pxPorBloco * dpr; pedir(); },
      irPara: function (x, z) {
        var p = projetar(x - area.x1, H / 2, z - area.z1);
        estado.panX = p[0]; estado.panY = p[1]; pedir();
      },
      quads: function () { return totalQuads; },
      desenharAgora: quadro
    };
  }

  raiz.McScanView = { criar: criar };
})(typeof window !== "undefined" ? window : globalThis);
