#!/usr/bin/env python3
"""mapa.py — CLI do mapa de batalha ao vivo (LOCAL PATCH mesa-ptbr).

Sempre UMA string entre aspas simples (no zsh, `a>B2` sem aspas redireciona):
    mapa.py carregar cais-brindol          # lê <campanha>/mapas/cais-brindol.mapa e abre na tela
    mapa.py 'mv snig>F5 des1>D5; atk snig>caspio acerto 7'
    mapa.py ver [id]                       # resumo em texto, não mexe na tela
    mapa.py mostrar | esconder
    mapa.py caderno ARQUIVO.svg            # salva o croqui com tokens (para galeria.py --colecao taticas)

Sai com código 1 e "ERRO ..." quando o comando é recusado (nada é aplicado).
Comandos e DSL: ver mapa_estado.py.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
from runtime_paths import rt  # noqa: E402

_ESQ = os.path.join(_DIR, ".scheme")
_SCHEME = open(_ESQ, encoding="utf-8").read().strip() if os.path.exists(_ESQ) else "http"
BASE = f"{_SCHEME}://localhost:5001"
_CTX = ssl._create_unverified_context() if _SCHEME == "https" else None


def _req(caminho: str, corpo: dict | None = None) -> tuple[int, str]:
    h = {"Content-Type": "application/json"}
    try:
        h["X-DND-Token"] = open(rt(".token"), encoding="utf-8").read().strip()
    except OSError:
        pass
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(BASE + caminho, data=dados, headers=h,
                               method="POST" if dados else "GET")
    try:
        with urllib.request.urlopen(r, timeout=5, context=_CTX) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, f"ERRO tela fora do ar ({e}); suba com start-display.sh\n"


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    verbo = argv[0]
    if verbo == "carregar" and len(argv) == 2:
        st, txt = _req("/mapa", {"carregar": argv[1]})
    elif verbo in ("mostrar", "esconder") and len(argv) == 1:
        st, txt = _req("/mapa", {verbo: True})
    elif verbo == "caderno" and len(argv) == 2:
        st, txt = _req("/mapa/croqui.svg")
        if st == 200:
            with open(argv[1], "w", encoding="utf-8") as f:
                f.write(txt)
            txt = f"croqui salvo em {argv[1]}\n"
    else:
        st, txt = _req("/mapa", {"cmd": " ".join(argv)})
    sys.stdout.write(txt)
    return 0 if st == 200 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
