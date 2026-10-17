#!/usr/bin/env python3
"""Bateria de rolagens: rola tudo de uma vez e manda cada rolagem para a tela (dados 3D).

Uso:
    python3 rolar.py "Fulano|Besta (Sharpshooter)|1d20+5-5+1d4" "Fulano|Dano|1d8+13" \
                     "Errol|Mordida|1d20+5" "!Teck|Percepção secreta|1d20+2"

Cada argumento: "Quem|Rótulo|notação". A notação soma termos com + e -:
    NdS (ex.: 1d20, 2d6), NdSkh1 / NdSkl1 (vantagem / desvantagem: 2d20kh1), números.
Prefixo "!" = rolagem secreta (não vai para a tela).
Dados mistos de uma rolagem (d20 + d4 da Orientação) caem num lançamento só.

Modo cena (dados no meio da narração):
    python3 rolar.py --mudo "Fulano|Besta|1d20+5" ...   rola, guarda e NÃO mostra na tela
    python3 rolar.py --mostrar 1                        mostra na tela a rolagem 1 da última bateria guardada
"""
import json
import os
import random
import re
import ssl
import sys
from pathlib import Path
import urllib.request

TERMO = re.compile(r"([+-]?)\s*(?:(\d*)d(\d+)(k[hl]\d+)?|(\d+))", re.I)
DISPLAY = str(Path(__file__).resolve().parent.parent / "display")


def rolar(notacao: str):
    total, grupos, partes = 0, [], []
    pos = 0
    for m in TERMO.finditer(notacao.replace(" ", "")):
        if m.start() != pos:
            raise ValueError(f"notação inválida: {notacao!r}")
        pos = m.end()
        sinal = -1 if m.group(1) == "-" else 1
        if m.group(3):
            n, lados = int(m.group(2) or 1), int(m.group(3))
            vals = [random.randint(1, lados) for _ in range(n)]
            manter = vals
            if m.group(4):
                k = int(m.group(4)[2:])
                ordem = sorted(vals, reverse=m.group(4)[1].lower() == "h")
                manter = ordem[:k]
            total += sinal * sum(manter)
            grupos.append({"sides": lados, "values": vals})
            txt = f"{n}d{lados}{m.group(4) or ''}[{','.join(map(str, vals))}]"
            partes.append(("-" if sinal < 0 else "+") + txt)
        else:
            total += sinal * int(m.group(5))
            partes.append(("-" if sinal < 0 else "+") + m.group(5))
    if pos != len(notacao.replace(" ", "")) or not grupos:
        raise ValueError(f"notação inválida: {notacao!r}")
    return total, grupos, "".join(partes).lstrip("+")


def mandar(quem, rotulo, total, grupos):
    try:
        esquema = open(os.path.join(DISPLAY, ".scheme")).read().strip() or "http"
    except OSError:
        esquema = "http"
    token = ""
    for tf in (os.path.expanduser("~/.claude/dnd/.runtime/.token"), os.path.join(DISPLAY, ".token")):
        try:
            token = open(tf).read().strip()
            break
        except OSError:
            pass
    corpo = {"who": quem, "label": rotulo, "total": total, "sides": grupos[0]["sides"],
             "values": grupos[0]["values"], "grupos": grupos}
    req = urllib.request.Request(
        f"{esquema}://localhost:5001/dice3d", data=json.dumps(corpo).encode(), method="POST",
        headers={"content-type": "application/json", **({"X-DND-Token": token} if token else {})})
    ctx = ssl._create_unverified_context() if esquema == "https" else None
    try:
        urllib.request.urlopen(req, timeout=2, context=ctx).read()
    except Exception as e:  # tela fora do ar: segue só no terminal
        print(f"rolar.py: tela indisponível ({e})", file=sys.stderr)


GUARDADA = os.path.expanduser("~/.claude/dnd/.runtime/ultima-bateria.json")


def main(args):
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--mostrar":
        bateria = json.load(open(GUARDADA))
        for n in args[1:]:
            r = bateria[int(n) - 1]
            mandar(r["quem"], r["rotulo"], r["total"], r["grupos"])
        return 0
    mudo = args[0] == "--mudo"
    if mudo:
        args = args[1:]
    bateria = []
    for i, arg in enumerate(args, 1):
        secreta = arg.startswith("!")
        quem, rotulo, notacao = (arg.lstrip("!").split("|") + ["", ""])[:3]
        if not notacao:
            quem, rotulo, notacao = "Mestre", "", quem
        total, grupos, det = rolar(notacao)
        d20 = [v for g in grupos if g["sides"] == 20 for v in g["values"]]
        marca = " ★20 NATURAL" if 20 in d20 and len(d20) == 1 else (" ✗1 NATURAL" if d20 == [1] else "")
        num = f"#{i} " if mudo else ""
        print(f"{num}{'[secreta] ' if secreta else ''}{quem} — {rotulo}: {det} = {total}{marca}")
        bateria.append({"quem": quem, "rotulo": rotulo, "total": total, "grupos": grupos})
        if not secreta and not mudo:
            mandar(quem, rotulo, total, grupos)
    if mudo:
        with open(GUARDADA, "w") as f:
            json.dump(bateria, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
