#!/usr/bin/env python3
"""Monstruário da campanha: o caderno de desenhos do Corrin.

Os dados ficam em <campanha>/monstruario.json; cada entrada tem um "prompt"
para o desenho a nanquim e um caminho "imagem" relativo à pasta da campanha.

Uso:
  python3 monstruario.py desenhar [id ...]   # gera os desenhos que faltam (ou os ids dados)
  python3 monstruario.py montar              # gera <campanha>/monstruario.html
  python3 monstruario.py tudo                # desenhar + montar
"""

import os
import base64
import html
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CAMPANHA = Path.home() / ".claude/dnd/campaigns" / os.environ.get("DND_CAMPANHA", "minha-campanha")
DADOS = CAMPANHA / "monstruario.json"
SAIDA = CAMPANHA / "monstruario.html"


def carregar():
    return json.loads(DADOS.read_text(encoding="utf-8"))


def desenhar_um(entrada, forcar):
    destino = CAMPANHA / entrada["imagem"]
    if destino.exists() and not forcar:
        return f"{entrada['id']}: já existe"
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(AQUI / "gerar_imagem.py"),
           "--estilo", "caderno", "--proporcao", "3:4",
           "--prompt", entrada["prompt"], "--saida", str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return f"{entrada['id']}: FALHOU\n{r.stderr.strip()}"
    return f"{entrada['id']}: desenhado"


def desenhar(ids):
    entradas = [e for e in carregar()["entradas"] if not ids or e["id"] in ids]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for msg in ex.map(lambda e: desenhar_um(e, bool(ids)), entradas):
            print(msg)


def imagem_embutida(caminho_rel):
    # A extensão é ajustada pelo gerador; aceitar qualquer uma.
    base = CAMPANHA / caminho_rel
    for c in [base, *base.parent.glob(base.stem + ".*")]:
        if c.exists():
            tipo = {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp"}.get(c.suffix[1:].lower(), "png")
            return f"data:image/{tipo};base64," + base64.b64encode(c.read_bytes()).decode()
    return ""


def pagina(e, n):
    esc = html.escape
    img = imagem_embutida(e["imagem"])
    figura = f'<img src="{img}" alt="Desenho de {esc(e["nome"])}">' if img else '<div class="vazio">(desenho por fazer)</div>'
    itens = "".join(f"<li>{esc(o)}</li>" for o in e["observado"])
    return f"""
<article class="pagina">
  <div class="num">p. {n}</div>
  <figure>{figura}</figure>
  <div class="texto">
    <h2>{esc(e["nome"])}</h2>
    <p class="tipo">{esc(e["tipo"])}</p>
    <p class="onde">{esc(e["onde"])} · {esc(e["quando"])} · abatidos: {e["abatidos"]}</p>
    <h3>O que vimos</h3>
    <ul>{itens}</ul>
    <h3>Ponto fraco</h3>
    <p>{esc(e["fraquezas"])}</p>
    <p class="nota">{esc(e["nota"])}<br><span>— C. V.</span></p>
  </div>
</article>"""


def montar():
    d = carregar()
    paginas = "".join(pagina(e, i + 1) for i, e in enumerate(d["entradas"]))
    SAIDA.write_text(f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(d["titulo"])}</title>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Special+Elite&display=swap" rel="stylesheet">
<style>
:root {{ --papel:#efe6cf; --linha:#b9c7d6; --tinta:#2a2620; --margem:#c0504d; --fundo:#2b2621; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fundo); color:var(--tinta); font-family:"Caveat",cursive; padding:24px 16px; }}
header {{ max-width:900px; margin:0 auto 24px; color:#e8dcc0; text-align:center; }}
header h1 {{ font-size:3rem; margin:0; }}
header p {{ font-size:1.5rem; margin:0; opacity:.8; }}
.pagina {{ position:relative; max-width:900px; margin:0 auto 32px; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); gap:24px;
  padding:40px 32px 32px 64px; background:var(--papel);
  background-image:linear-gradient(90deg,transparent 46px,var(--margem) 46px,var(--margem) 48px,transparent 48px),
                   repeating-linear-gradient(transparent 0 31px,var(--linha) 31px 32px);
  box-shadow:0 8px 24px rgba(0,0,0,.5); border-radius:2px 6px 6px 2px; }}
.num {{ position:absolute; top:10px; right:18px; font-size:1.3rem; opacity:.6; }}
figure {{ margin:0; }}
figure img {{ width:100%; display:block; mix-blend-mode:multiply; transform:rotate(-1deg); }}
.vazio {{ aspect-ratio:3/4; display:grid; place-items:center; border:2px dashed #999; font-size:1.5rem; }}
h2 {{ font-family:"Special Elite",monospace; font-size:1.9rem; margin:0; }}
h3 {{ font-size:1.6rem; margin:16px 0 0; text-decoration:underline; }}
.tipo {{ font-size:1.4rem; margin:0; font-style:italic; }}
.onde {{ font-family:"Special Elite",monospace; font-size:.85rem; margin:6px 0 0; opacity:.75; }}
ul {{ margin:4px 0; padding-left:20px; }}
li, p {{ font-size:1.45rem; line-height:32px; }}
p {{ margin:0; }}
.nota {{ margin-top:16px; color:#3b4a7a; transform:rotate(-.6deg); }}
.nota span {{ display:block; text-align:right; }}
@media (max-width:700px) {{ .pagina {{ grid-template-columns:1fr; padding:32px 16px 24px 56px; }} header h1 {{ font-size:2.2rem; }} }}
</style></head><body>
<header><h1>{html.escape(d["titulo"])}</h1><p>{html.escape(d["subtitulo"])}</p></header>
{paginas}
</body></html>
""", encoding="utf-8")
    print(f"montado: {SAIDA}")


if __name__ == "__main__":
    cmd, *resto = sys.argv[1:] or ["tudo"]
    if cmd in ("desenhar", "tudo"):
        desenhar(resto if cmd == "desenhar" else [])
    if cmd in ("montar", "tudo"):
        montar()
