#!/usr/bin/env python3
"""Gera uma imagem via OpenRouter, opcionalmente a partir de imagens de referência.

Uso:
  python3 gerar_imagem.py --saida imagens/tavien.png --prompt "..." \
      [--estilo misto] [--ref imagens/tavien-ficha.png ...] [--modelo google/gemini-3-pro-image] [--so-figurino | --so-estilo]

A chave é lida de OPENROUTER_API_KEY ou de ~/.openrouter_api_key.
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_PADRAO = "google/gemini-3.1-flash-lite-image"

# Blocos de estilo: colados iguais em todo prompt para manter a identidade visual.
ESTILOS = {
    "oldschool": (
        "Style: 1980s tabletop RPG rulebook illustration. Hand-painted gouache over visible "
        "ink linework, slightly flat lighting, muted earthy palette with one strong accent "
        "color, grainy paper texture, static heroic pose, simple painterly background. "
        "Not digital-looking, not photorealistic, no modern anime influence."
    ),
    "caderno": (
        "Style: quick black ink line art sketched in a field notebook, like a 1st-edition "
        "1970s-80s monster manual illustration. Pen hatching and cross-hatching, no color, "
        "no shading gradients, confident linework with a few loose construction lines, "
        "drawn directly on slightly yellowed lined notebook paper with a faint coffee stain. "
        "Single creature, full body, neutral study pose, no background scenery."
    ),
    "tatico": (
        "Style: a page from a field cartographer's tactical notebook. Top-down tactical "
        "diagram drawn in sepia and black ink with light watercolor washes (muted blue, "
        "rust red, ochre), on aged cream paper with faint grid lines, ink blots and small "
        "coffee stains. Figures shown as simple labeled tokens and small hand-drawn icons, "
        "movement arrows, dotted lines of fire, hatched cover, measured distances with tick "
        "marks, a small compass rose in a corner, tidy handwritten margin notes. Looks hand "
        "made by a meticulous ex-diplomat mapmaker. No photorealism, no 3D render."
    ),
    "eberron": (
        "Style: dynamic pulp-noir fantasy illustration for a magitech post-war setting. "
        "Angular, energetic painted figures, exaggerated gear with straps, buckles and worn "
        "leather, arcane industrial details, dramatic low-angle lighting, gritty desaturated "
        "palette with ember-orange and steel-blue accents."
    ),
    "misto": (
        "Style: 1980s fantasy paperback cover painting, hand-painted gouache and oil with "
        "visible brushwork and ink linework, grainy paper texture, muted earthy palette with "
        "one strong accent color. Subject matter is pulp-noir magitech post-war fantasy: worn "
        "leather, brass arcane instruments, salvaged wartime gear, ash-gray wasteland mist. "
        "Not digital-looking, not photorealistic, no modern anime influence."
    ),
}

SEM_TEXTO = "No text, no lettering, no watermark, no border, no signature."


def ler_chave():
    chave = os.environ.get("OPENROUTER_API_KEY")
    if chave:
        return chave.strip()
    arq = Path.home() / ".openrouter_api_key"
    if arq.exists():
        return arq.read_text().strip()
    sys.exit("Chave não encontrada: defina OPENROUTER_API_KEY ou crie ~/.openrouter_api_key")


def data_url(caminho):
    mime = mimetypes.guess_type(caminho)[0] or "image/png"
    dados = base64.b64encode(Path(caminho).read_bytes()).decode()
    return f"data:{mime};base64,{dados}"


def gerar(prompt, saida, modelo, refs, proporcao):
    conteudo = [{"type": "text", "text": prompt}]
    for ref in refs:
        conteudo.append({"type": "image_url", "image_url": {"url": data_url(ref)}})
    corpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": conteudo}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": proporcao},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {ler_chave()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            dados = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Erro HTTP {e.code}: {e.read().decode()[:500]}")

    if "error" in dados:
        sys.exit(f"Erro da API: {json.dumps(dados['error'])[:500]}")
    msg = dados["choices"][0]["message"]
    imagens = msg.get("images") or []
    if not imagens:
        sys.exit(f"O modelo não devolveu imagem. Texto: {str(msg.get('content'))[:300]}")

    url = imagens[0]["image_url"]["url"]
    cabecalho, b64 = url.split(",", 1)
    ext = ".jpg" if "jpeg" in cabecalho else ".png"
    destino = Path(saida).with_suffix(ext)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(base64.b64decode(b64))
    custo = (dados.get("usage") or {}).get("cost")
    print(f"{destino}  |  modelo: {modelo}  |  custo: {custo}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prompt", required=True, help="descrição do personagem ou da cena")
    p.add_argument("--saida", required=True, help="arquivo de saída (a extensão é ajustada)")
    p.add_argument("--estilo", choices=sorted(ESTILOS), default="misto")
    p.add_argument("--ref", action="append", default=[], help="imagem de referência (pode repetir)")
    p.add_argument("--modelo", default=MODELO_PADRAO)
    p.add_argument("--proporcao", default="3:4", help="ex.: 3:4, 1:1, 16:9")
    p.add_argument("--so-figurino", action="store_true",
                   help="usa a referência só para roupa, equipamento e estilo; rosto e corpo seguem o prompt")
    p.add_argument("--so-estilo", action="store_true",
                   help="usa a referência só para o estilo de arte; o personagem é outro")
    args = p.parse_args()

    partes = [args.prompt.strip()]
    if args.ref and args.so_estilo:
        partes.append(
            "The reference image shows a DIFFERENT character. Use it only to match the art "
            "style: linework, rendering, palette and background treatment. Do not copy its "
            "face, clothing or gear."
        )
    elif args.ref and args.so_figurino:
        partes.append(
            "Use the reference image(s) only for clothing, gear and art style. The face, age "
            "and body build must follow the text description, not the reference."
        )
    elif args.ref:
        partes.append(
            "Keep the character exactly as shown in the reference image(s): same face, hair, "
            "build, clothing and gear."
        )
    partes += [ESTILOS[args.estilo], SEM_TEXTO]
    gerar("\n\n".join(partes), args.saida, args.modelo, args.ref, args.proporcao)


if __name__ == "__main__":
    main()
