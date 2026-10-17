#!/usr/bin/env python3
"""Galeria de lugares da campanha atual (variável DND_CAMPANHA).

Imagens em ~/.claude/dnd/campaigns/$DND_CAMPANHA/galeria/, catálogo em galeria.json.

Uso:
    python3 galeria.py adicionar ID --lugar "Salvation" --titulo "..." --credito "..." \
        (--url URL | --arquivo caminho.jpg) [--tipo oficial|fanart|mapa|gerada] [--fonte URL] [--nota "..."]
    python3 galeria.py mostrar ID        # abre a imagem na tela (localhost:5001)
    python3 galeria.py esconder          # fecha a imagem na tela
    python3 galeria.py listar
    python3 galeria.py html              # refaz galeria.html (abre no navegador)

    --colecao taticas (antes do subcomando) usa a segunda galeria, de anotações
    táticas do grupo: pasta galeria-tatica/, página taticas.html.
"""

import argparse
import datetime
import html
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

CAMPANHA = Path.home() / ".claude/dnd/campaigns" / os.environ.get("DND_CAMPANHA", "minha-campanha")
PASTA = CAMPANHA / "galeria"
CATALOGO = PASTA / "galeria.json"
PAGINA = CAMPANHA / "galeria.html"
TELA = "http://localhost:5001"
TOKEN = Path.home() / ".claude/dnd/.runtime/.token"
COLECOES = {
    "lugares": ("galeria", "galeria.html", "Galeria da campanha",
                "Lugares que o grupo conheceu. Imagens de terceiros só para uso pessoal na mesa; créditos em cada uma."),
    "taticas": ("galeria-tatica", "taticas.html", "Caderno tático",
                "Anotações táticas do grupo: formações, aberturas e truques do grupo."),
}
TITULO, SUBTITULO = COLECOES["lugares"][2:]


def usar_colecao(nome: str) -> None:
    global PASTA, CATALOGO, PAGINA, TITULO, SUBTITULO
    pasta, pagina, TITULO, SUBTITULO = COLECOES[nome]
    PASTA = CAMPANHA / pasta
    CATALOGO = PASTA / "galeria.json"
    PAGINA = CAMPANHA / pagina


AGENTE = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def carregar() -> list:
    if CATALOGO.exists():
        return json.loads(CATALOGO.read_text(encoding="utf-8"))
    return []


def salvar(itens: list) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    CATALOGO.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")


def achar(itens: list, ident: str) -> dict:
    for item in itens:
        if item["id"] == ident:
            return item
    sys.exit(f"galeria: não achei '{ident}'. Use 'listar'.")


def adicionar(a) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    if a.url:
        req = urllib.request.Request(a.url, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(req, timeout=30) as r:
            dados = r.read()
            tipo_mime = r.headers.get("content-type", "")
        if not tipo_mime.startswith("image/"):
            sys.exit(f"galeria: a URL não devolveu imagem ({tipo_mime}).")
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(tipo_mime.split(";")[0], ".jpg")
        destino = PASTA / f"{a.id}{ext}"
        destino.write_bytes(dados)
    else:
        origem = Path(a.arquivo)
        destino = PASTA / f"{a.id}{origem.suffix.lower()}"
        shutil.copyfile(origem, destino)

    antigos = {i["id"]: i for i in carregar()}
    itens = [i for i in antigos.values() if i["id"] != a.id]
    publicado = antigos.get(a.id, {}).get("publicado") or datetime.datetime.now().isoformat(timespec="seconds")
    itens.append({
        "id": a.id, "lugar": a.lugar, "titulo": a.titulo, "arquivo": destino.name,
        "credito": a.credito, "tipo": a.tipo, "fonte": a.fonte or a.url or "", "nota": a.nota or "", "publicado": publicado,
    })
    itens.sort(key=lambda i: i.get("publicado", ""))
    salvar(itens)
    gerar_html(itens)
    print(f"galeria: {a.id} → {destino.name}")


def postar(caminho: str, corpo: dict) -> None:
    headers = {"content-type": "application/json"}
    if TOKEN.exists():
        headers["X-DND-Token"] = TOKEN.read_text().strip()
    req = urllib.request.Request(TELA + caminho, data=json.dumps(corpo).encode(), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as e:
        sys.exit(f"galeria: tela indisponível ({e}).")


def mostrar(a) -> None:
    item = achar(carregar(), a.id)
    postar("/cena-imagem", {"arquivo": item["arquivo"], "titulo": item["titulo"], "credito": item["credito"],
                             "colecao": "taticas" if PASTA.name == "galeria-tatica" else "lugares"})
    print(f"galeria: na tela — {item['titulo']}")


def listar(_a) -> None:
    for i in sorted(carregar(), key=lambda i: (i["lugar"], i["id"])):
        print(f"{i['id']:<28} {i['lugar']:<22} {i['tipo']:<8} {i['titulo']}")


def gerar_html(itens: list) -> None:
    lugares: dict = {}
    for i in itens:
        lugares.setdefault(i["lugar"], []).append(i)
    blocos = []
    for lugar, grupo in lugares.items():
        cards = "".join(
            f'<figure><a href="{PASTA.name}/{html.escape(i["arquivo"])}" target="_blank">'
            f'<img src="{PASTA.name}/{html.escape(i["arquivo"])}" loading="lazy" alt="{html.escape(i["titulo"])}"></a>'
            f'<figcaption><b>{html.escape(i["titulo"])}</b>'
            f'<span>{html.escape(i["credito"])} · {html.escape(i["tipo"])}</span>'
            + (f'<em>{html.escape(i["nota"])}</em>' if i.get("nota") else "")
            + f'<code>galeria.py{"" if PASTA.name == "galeria" else " --colecao taticas"} mostrar {html.escape(i["id"])}</code></figcaption></figure>'
            for i in grupo)
        blocos.append(f"<h2>{html.escape(lugar)}</h2><div class=grade>{cards}</div>")
    PAGINA.write_text(f"""<!doctype html><html lang=pt-BR><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(TITULO)}</title>
<style>
body{{margin:0;padding:24px 16px 60px;background:#15120e;color:#e9dcc0;font-family:Georgia,serif}}
h1{{font-weight:normal;letter-spacing:.06em;margin:0 0 4px}} h2{{color:#d9b36a;font-weight:normal;border-bottom:1px solid #4a3d28;padding-bottom:4px;margin-top:40px}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}}
figure{{margin:0;background:#1f1a14;border:1px solid #3a3022}} img{{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}}
figcaption{{padding:8px 10px;display:grid;gap:3px;font-size:.9rem}} span{{color:#a8987a;font-size:.8rem}} em{{font-size:.8rem;color:#c9b996}}
code{{font-size:.72rem;color:#7d6f57}}
</style><h1>{html.escape(TITULO)}</h1><p style="color:#a8987a">{html.escape(SUBTITULO)}</p>
{''.join(blocos)}</html>""", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Galeria de lugares da campanha atual (variável DND_CAMPANHA)")
    p.add_argument("--colecao", default="lugares", choices=list(COLECOES))
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("adicionar")
    ad.add_argument("id")
    ad.add_argument("--lugar", required=True)
    ad.add_argument("--titulo", required=True)
    ad.add_argument("--credito", required=True)
    origem = ad.add_mutually_exclusive_group(required=True)
    origem.add_argument("--url")
    origem.add_argument("--arquivo")
    ad.add_argument("--tipo", default="fanart", choices=["oficial", "fanart", "mapa", "gerada"])
    ad.add_argument("--fonte")
    ad.add_argument("--nota")
    ad.set_defaults(f=adicionar)
    mo = sub.add_parser("mostrar")
    mo.add_argument("id")
    mo.set_defaults(f=mostrar)
    sub.add_parser("esconder").set_defaults(f=lambda a: postar("/cena-imagem", {"esconder": True}) or print("galeria: fechada"))
    sub.add_parser("listar").set_defaults(f=listar)
    sub.add_parser("html").set_defaults(f=lambda a: gerar_html(carregar()) or print(PAGINA))
    a = p.parse_args()
    usar_colecao(a.colecao)
    a.f(a)


if __name__ == "__main__":
    main()
