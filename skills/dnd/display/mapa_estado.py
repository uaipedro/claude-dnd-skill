"""mapa_estado.py — estado e regras do mapa de batalha ao vivo (LOCAL PATCH mesa-ptbr).

Puro: nada de rede nem de Flask. O servidor guarda um dict `estado`, aplica
comandos de texto com `aplicar(estado, texto)` e manda o resultado pelo SSE.

Coordenadas no estilo xadrez: coluna em letra (A–Z), linha em número (1–99).
Uma casa = 5 ft. Diagonal custa 5 ft (regra do PHB). Terreno difícil custa 10.

Cenário (arquivo .mapa, uma instrução por linha, # comenta):
    grade 20x14
    titulo "Cais de Brindol — noite"
    parede A1-T1 A2-A14        # retângulos de casas; bloqueia
    obstaculo F8               # bloqueia (pilar, árvore grossa)
    dificil F5 G5-G6           # custa o dobro
    agua A10-T14               # difícil, desenhada como água
    porta K3 fechada           # fechada bloqueia
    rotulo M2 "armazém"
    nevoa                      # começa tudo encoberto
    revelar A1-H8
    token snig@H7:ini:30 "Snig"

Comandos de mesa (separe vários com ;):
    add id@C4[:pj|ali|ini][:30][:a10] ["Nome"]   mv id>F5[!] (ou id@F5) ...   rm id [morto]
    atk a>b [acerto|erro|crit] [N]   area cone15 C4>E4 ["rótulo"] [fixa]
    hp id 12/20   dano id 5   cura id 5   cond id +caido -envenenado
    turno id   rodada N   porta K3 abrir|fechar   revelar A1-H8   esconder A1-H8
    limpar-areas   desfazer   ver [id]
"""
from __future__ import annotations

import copy
import heapq
import math
import re
import shlex

LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LADOS = {"pj": "pj", "ali": "ali", "aliado": "ali", "ini": "ini", "inimigo": "ini"}
TERRENOS = {"parede", "obstaculo", "dificil", "agua"}
MAX_DESFAZER = 30
MAX_LOG = 200


class ErroMapa(ValueError):
    pass


# ─── Coordenadas ─────────────────────────────────────────────────────────────

_CASA = re.compile(r"^([A-Za-z])(\d{1,2})$")


def casa(txt: str, est: dict | None = None) -> tuple[int, int]:
    m = _CASA.match(txt.strip())
    if not m:
        raise ErroMapa(f"casa inválida: {txt!r} (use letra+número, ex. C4)")
    x, y = LETRAS.index(m.group(1).upper()), int(m.group(2)) - 1
    if est is not None and not (0 <= x < est["w"] and 0 <= y < est["h"]):
        raise ErroMapa(f"{txt.upper()} está fora da grade {est['w']}x{est['h']}")
    return x, y


def nome_casa(c) -> str:
    return f"{LETRAS[c[0]]}{c[1] + 1}"


def faixa(txt: str, est: dict) -> list[tuple[int, int]]:
    """'C4' ou 'A1-T1' (retângulo) → lista de casas."""
    if "-" in txt:
        a, b = txt.split("-", 1)
        (x1, y1), (x2, y2) = casa(a, est), casa(b, est)
        return [(x, y) for x in range(min(x1, x2), max(x1, x2) + 1)
                for y in range(min(y1, y2), max(y1, y2) + 1)]
    return [casa(txt, est)]


def dist(a, b) -> int:
    return 5 * max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _k(c) -> str:
    return f"{c[0]},{c[1]}"


def _c(k: str) -> tuple[int, int]:
    x, y = k.split(",")
    return int(x), int(y)


# ─── Estado ──────────────────────────────────────────────────────────────────

def novo(w: int = 20, h: int = 14) -> dict:
    return {"w": w, "h": h, "titulo": "", "terreno": {}, "portas": {}, "rotulos": [],
            "nevoa": [], "tokens": {}, "areas": [], "rodada": 0, "vez": None,
            "base_v": 0, "v": 0, "log": [], "_desfazer": []}


def _token(est, ident: str) -> dict:
    t = est["tokens"].get(ident)
    if t:
        return t
    cands = [k for k in est["tokens"] if k.startswith(ident)]
    if len(cands) == 1:
        return est["tokens"][cands[0]]
    vivos = ", ".join(est["tokens"]) or "nenhum"
    raise ErroMapa(f"token {ident!r} não existe (tokens: {vivos})")


def _bloqueada(est, c) -> bool:
    k = _k(c)
    return est["terreno"].get(k) in ("parede", "obstaculo") or est["portas"].get(k) == "fechada"


def _custo(est, c) -> int:
    return 10 if est["terreno"].get(_k(c)) in ("dificil", "agua") else 5


INCAPACITANTES = {"incapacitado", "atordoado", "paralisado", "inconsciente", "petrificado"}


def _ativo(t) -> bool:
    """Pode fazer ataque de oportunidade (Caído ainda pode)."""
    return not t.get("morto") and not INCAPACITANTES & set(t.get("cond", []))


def _inimigos(a, b) -> bool:
    return (a["lado"] == "ini") != (b["lado"] == "ini")


def _ocupante(est, c, menos=None):
    for t in est["tokens"].values():
        if t is not menos and not t.get("morto") and tuple(t["pos"]) == tuple(c):
            return t
    return None


def caminho(est, tok, alvo):
    """Dijkstra 8-direções. Passa por aliados, não por inimigos. Devolve (custo, casas)."""
    ini = tuple(tok["pos"])
    alvo = tuple(alvo)
    if _bloqueada(est, alvo):
        raise ErroMapa(f"{nome_casa(alvo)} é parede/obstáculo/porta fechada")
    if _ocupante(est, alvo, tok):
        raise ErroMapa(f"{nome_casa(alvo)} já está ocupada por {_ocupante(est, alvo, tok)['id']}")
    barreira = {tuple(t["pos"]) for t in est["tokens"].values()
                if t is not tok and not t.get("morto") and _inimigos(t, tok)}
    melhor = {ini: 0}
    de = {}
    fila = [(0, ini)]
    while fila:
        g, c = heapq.heappop(fila)
        if c == alvo:
            break
        if g > melhor[c]:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (c[0] + dx, c[1] + dy)
                if (dx, dy) == (0, 0) or not (0 <= n[0] < est["w"] and 0 <= n[1] < est["h"]):
                    continue
                if _bloqueada(est, n) or n in barreira:
                    continue
                if dx and dy and _bloqueada(est, (c[0] + dx, c[1])) and _bloqueada(est, (c[0], c[1] + dy)):
                    continue  # não corta quina de parede
                ng = g + _custo(est, n)
                if ng < melhor.get(n, 1 << 30):
                    melhor[n], de[n] = ng, c
                    heapq.heappush(fila, (ng, n))
    if alvo not in melhor:
        raise ErroMapa(f"{tok['id']} não tem caminho até {nome_casa(alvo)}")
    rota = [alvo]
    while rota[-1] != ini:
        rota.append(de[rota[-1]])
    return melhor[alvo], rota[::-1]


def _avisos_ado(est, tok, rota) -> list[str]:
    out, vistos = [], set()
    for a, b in zip(rota, rota[1:]):
        for e in est["tokens"].values():
            if e is tok or e["id"] in vistos or not _ativo(e) or not _inimigos(e, tok):
                continue
            alc = e.get("alc", 5)
            if dist(a, e["pos"]) <= alc < dist(b, e["pos"]):
                vistos.add(e["id"])
                out.append(f"AdO: {e['id']} pode atacar {tok['id']} (saiu de {nome_casa(a)})")
    return out


# ─── Áreas de efeito ─────────────────────────────────────────────────────────

_AREA = re.compile(r"^(cone|linha|esfera|circulo|cubo|cilindro)(\d+)$")


def celulas_area(est, forma: str, tam: int, origem, alvo=None) -> list[tuple[int, int]]:
    ox, oy = origem[0] + .5, origem[1] + .5
    q = tam / 5
    out = []
    if forma in ("esfera", "circulo", "cilindro"):
        # raio a partir do centro da casa de origem
        for x in range(est["w"]):
            for y in range(est["h"]):
                if math.hypot(x + .5 - ox, y + .5 - oy) <= q + .01:
                    out.append((x, y))
        return out
    if forma == "cubo":
        sx = 1 if alvo is None or alvo[0] >= origem[0] else -1
        sy = 1 if alvo is None or alvo[1] >= origem[1] else -1
        n = max(1, int(q))
        return [(origem[0] + sx * i, origem[1] + sy * j) for i in range(n) for j in range(n)
                if 0 <= origem[0] + sx * i < est["w"] and 0 <= origem[1] + sy * j < est["h"]]
    if alvo is None:
        raise ErroMapa(f"{forma} precisa de direção: {forma}{tam} C4>E4")
    dx, dy = alvo[0] - origem[0], alvo[1] - origem[1]
    norma = math.hypot(dx, dy) or 1
    ux, uy = dx / norma, dy / norma
    for x in range(est["w"]):
        for y in range(est["h"]):
            if (x, y) == tuple(origem):
                continue
            vx, vy = x + .5 - ox, y + .5 - oy
            ao_longo = vx * ux + vy * uy
            lado = abs(-vx * uy + vy * ux)
            if forma == "cone" and 0 < ao_longo <= q + .01 and lado <= ao_longo / 2 + .01:
                out.append((x, y))
            elif forma == "linha" and 0 < ao_longo <= q + .01 and lado <= .5:
                out.append((x, y))
    return out


# ─── Comandos ────────────────────────────────────────────────────────────────

def _add(est, spec: str, nome: str | None, eventos):
    if "@" not in spec:
        raise ErroMapa(f"token sem posição: {spec!r} (use id@C4:ini:30)")
    ident, resto = spec.split("@", 1)
    partes = resto.split(":")
    pos = casa(partes[0], est)
    t = {"id": ident, "nome": nome or ident, "pos": list(pos), "lado": "ini",
         "desl": 30, "usou": 0, "cond": []}
    for p in partes[1:]:
        if p in LADOS:
            t["lado"] = LADOS[p]
        elif p.isdigit():
            t["desl"] = int(p)
        elif re.fullmatch(r"a\d+", p):
            t["alc"] = int(p[1:])
        elif p:
            raise ErroMapa(f"atributo desconhecido {p!r} em {spec} (use pj/ali/ini, 30, a10)")
    if ident in est["tokens"] and not est["tokens"][ident].get("morto"):
        raise ErroMapa(f"já existe token {ident!r}")
    if _bloqueada(est, pos) or _ocupante(est, pos):
        raise ErroMapa(f"{nome_casa(pos)} não está livre para {ident}")
    est["tokens"][ident] = t
    eventos.append({"t": "add", "id": ident})


def _cenario_linha(est, args, eventos):
    cmd, a = args[0], args[1:]
    if cmd == "grade":
        m = re.fullmatch(r"(\d+)x(\d+)", a[0] if a else "")
        if not m:
            raise ErroMapa("grade LxA, ex. grade 20x14")
        w, h = int(m.group(1)), int(m.group(2))
        if not (1 <= w <= 26 and 1 <= h <= 99):
            raise ErroMapa("grade vai até 26 colunas x 99 linhas")
        est["w"], est["h"] = w, h
    elif cmd == "titulo":
        est["titulo"] = " ".join(a)
    elif cmd in TERRENOS:
        for f in a:
            for c in faixa(f, est):
                est["terreno"][_k(c)] = cmd
    elif cmd == "porta":
        c = casa(a[0], est)
        est["portas"][_k(c)] = "aberta" if a[1:2] == ["aberta"] else "fechada"
    elif cmd == "rotulo":
        est["rotulos"].append({"pos": list(casa(a[0], est)), "texto": " ".join(a[1:])})
    elif cmd == "nevoa":
        est["nevoa"] = [_k((x, y)) for x in range(est["w"]) for y in range(est["h"])]
    elif cmd == "token":
        _add(est, a[0], " ".join(a[1:]) or None, eventos)
    else:
        return False
    return True


def carregar_cenario(texto: str) -> dict:
    est = novo()
    for n, linha in enumerate(texto.splitlines(), 1):
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        try:
            args = shlex.split(linha)
            if not _cenario_linha(est, args, []) and not _mesa(est, args, []):
                raise ErroMapa(f"instrução desconhecida {args[0]!r}")
        except (ErroMapa, ValueError, IndexError) as e:
            raise ErroMapa(f"linha {n}: {e}") from None
    est["log"] = []
    return est


def _revelar(est, faixas, revelar: bool):
    nev = set(est["nevoa"])
    for f in faixas:
        for c in faixa(f, est):
            (nev.discard if revelar else nev.add)(_k(c))
    est["nevoa"] = sorted(nev)


def _mesa(est, args, eventos, avisos=None) -> bool:
    avisos = avisos if avisos is not None else []
    cmd, a = args[0], args[1:]
    if cmd == "add":
        i = 0
        while i < len(a):
            nome = a[i + 1] if i + 1 < len(a) and "@" not in a[i + 1] else None
            _add(est, a[i], nome, eventos)
            i += 2 if nome else 1
    elif cmd == "mv":
        for m in a:
            forcar = m.endswith("!")
            ident, _, dest = m.rstrip("!").replace("@", ">").partition(">")
            if not dest:
                raise ErroMapa(f"movimento sem destino: {m!r} (use id>F5)")
            tok = _token(est, ident)
            custo, rota = caminho(est, tok, casa(dest, est))
            livre = tok["desl"] - tok["usou"]
            if custo > livre and not forcar:
                raise ErroMapa(f"{tok['id']} precisa de {custo} ft até {dest.upper()}, mas só tem "
                               f"{livre} ft (de {tok['desl']}); use {m}! para forçar (Disparada etc.)")
            avisos += _avisos_ado(est, tok, rota)
            tok["pos"], tok["usou"] = list(rota[-1]), tok["usou"] + custo
            eventos.append({"t": "mv", "id": tok["id"], "rota": [list(c) for c in rota]})
            avisos.append(f"{tok['id']} → {nome_casa(rota[-1])} ({custo} ft, resta {tok['desl'] - tok['usou']})")
    elif cmd == "rm":
        tok = _token(est, a[0])
        if a[1:2] == ["morto"]:
            tok["morto"] = True
        else:
            del est["tokens"][tok["id"]]
        eventos.append({"t": "rm", "id": tok["id"], "morto": a[1:2] == ["morto"]})
    elif cmd == "atk":
        if not a or ">" not in a[0]:
            raise ErroMapa("atk atacante>alvo [acerto|erro|crit] [dano]")
        x, _, y = a[0].partition(">")
        ta, tb = _token(est, x), _token(est, y)
        res = next((p for p in a[1:] if p in ("acerto", "erro", "crit")), "acerto")
        dano = next((int(p) for p in a[1:] if p.isdigit()), None)
        if dano and tb.get("hp"):
            tb["hp"][0] = max(0, tb["hp"][0] - dano)
        eventos.append({"t": "atk", "de": ta["id"], "para": tb["id"], "res": res, "dano": dano})
        d = dist(ta["pos"], tb["pos"])
        avisos.append(f"{ta['id']} ataca {tb['id']} a {d} ft"
                      + (" (fora do corpo a corpo: só vale à distância)" if d > ta.get("alc", 5) else "")
                      + (" (alvo sem hp no mapa: dano não aplicado)" if dano and not tb.get("hp") else ""))
    elif cmd == "area":
        m = _AREA.match(a[0] if a else "")
        if not m:
            raise ErroMapa("area cone15|linha30|esfera20|cubo10 C4[>E4] [\"rótulo\"] [fixa]")
        o, _, d = a[1].partition(">")
        origem = casa(o, est)
        alvo = casa(d, est) if d else None
        cels = celulas_area(est, m.group(1), int(m.group(2)), origem, alvo)
        resto = a[2:]
        fixa = "fixa" in resto
        rotulo = " ".join(p for p in resto if p != "fixa") or a[0]
        dentro = [t["id"] for t in est["tokens"].values()
                  if not t.get("morto") and tuple(t["pos"]) in set(cels)]
        area = {"forma": m.group(1), "celulas": [list(c) for c in cels], "rotulo": rotulo,
                "origem": list(origem)}
        if fixa:
            est["areas"].append(area)
        eventos.append({"t": "area", **area, "fixa": fixa})
        avisos.append(f"{rotulo}: {len(cels)} casas, dentro: {', '.join(dentro) or 'ninguém'}")
    elif cmd == "limpar-areas":
        est["areas"] = []
    elif cmd in ("hp", "dano", "cura"):
        tok = _token(est, a[0])
        if cmd == "hp":
            cur, _, mx = a[1].partition("/")
            tok["hp"] = [int(cur), int(mx or cur)]
        else:
            if not tok.get("hp"):
                raise ErroMapa(f"{tok['id']} não tem hp no mapa (use hp {tok['id']} 12/20)")
            n = int(a[1]) * (1 if cmd == "cura" else -1)
            tok["hp"][0] = max(0, min(tok["hp"][1], tok["hp"][0] + n))
            eventos.append({"t": cmd, "id": tok["id"], "n": abs(n)})
    elif cmd == "cond":
        tok = _token(est, a[0])
        for p in a[1:]:
            nome = p.lstrip("+-")
            if p.startswith("-"):
                tok["cond"] = [c for c in tok["cond"] if c != nome]
            elif nome not in tok["cond"]:
                tok["cond"].append(nome)
    elif cmd == "turno":
        tok = _token(est, a[0])
        tok["usou"] = 0
        est["vez"] = tok["id"]
        eventos.append({"t": "turno", "id": tok["id"]})
    elif cmd == "rodada":
        est["rodada"] = int(a[0]) if a else est["rodada"] + 1
        for t in est["tokens"].values():
            t["usou"] = 0
    elif cmd == "porta":
        c = casa(a[0], est)
        if _k(c) not in est["portas"]:
            raise ErroMapa(f"não há porta em {nome_casa(c)}")
        est["portas"][_k(c)] = "aberta" if a[1:2] in (["abrir"], ["aberta"]) else "fechada"
    elif cmd in ("revelar", "esconder"):
        _revelar(est, a, cmd == "revelar")
    else:
        return False
    return True


def resumo(est, foco: str | None = None) -> str:
    """Texto curto para o agente: quem está onde, de quem é a vez, distâncias."""
    linhas = [f"{est['titulo'] or 'mapa'} {est['w']}x{est['h']} · rodada {est['rodada']}"
              + (f" · vez de {est['vez']}" if est["vez"] else "")]
    vivos = [t for t in est["tokens"].values() if not t.get("morto")]
    for lado, rot in (("pj", "PJ"), ("ali", "aliados"), ("ini", "inimigos")):
        grupo = [t for t in vivos if t["lado"] == lado]
        if grupo:
            linhas.append(f"{rot}: " + " | ".join(
                f"{t['id']} {nome_casa(t['pos'])}"
                + (f" {t['hp'][0]}/{t['hp'][1]}" if t.get("hp") else "")
                + (f" desl {t['desl'] - t['usou']}/{t['desl']}" if t["usou"] else "")
                + (f" [{','.join(t['cond'])}]" if t["cond"] else "") for t in grupo))
    mortos = [t["id"] for t in est["tokens"].values() if t.get("morto")]
    if mortos:
        linhas.append("caídos/mortos: " + ", ".join(mortos))
    alvo = foco or est["vez"]
    if alvo and alvo in est["tokens"]:
        f = est["tokens"][alvo]
        outros = sorted((dist(f["pos"], t["pos"]), t["id"]) for t in vivos if t is not f)
        adj = [i for d, i in outros if d <= 5]
        linhas.append(f"de {f['id']}: " + ", ".join(f"{i} {d}ft" for d, i in outros)
                      + f" · adjacentes: {', '.join(adj) or '—'}")
    if est["areas"]:
        linhas.append("áreas fixas: " + ", ".join(a["rotulo"] for a in est["areas"]))
    return "\n".join(linhas)


def _marca_base(est) -> int:
    """Muda quando muda algo desenhado no croqui-base (e não nos tokens)."""
    return hash(repr([est[k] for k in ("w", "h", "titulo", "terreno", "portas", "rotulos", "nevoa", "areas")]))


def aplicar(est: dict, texto: str) -> tuple[dict, str, list]:
    """Aplica um lote de comandos separados por ; ou quebra de linha.

    Atômico: se qualquer comando falhar, o estado não muda e levanta ErroMapa.
    Devolve (estado_novo, texto_para_o_agente, eventos_para_animar).
    """
    cmds = [c.strip() for c in re.split(r"[;\n]", texto) if c.strip()]
    if not cmds:
        return est, resumo(est), []
    if cmds == ["desfazer"]:
        if not est["_desfazer"]:
            raise ErroMapa("nada para desfazer")
        pilha = list(est["_desfazer"])
        anterior = pilha.pop()
        anterior["_desfazer"] = pilha
        anterior["v"] = est["v"] + 1
        anterior["base_v"] = est["base_v"] + 1
        return anterior, "desfeito.\n" + resumo(anterior), [{"t": "reset"}]
    if any(c.split()[0] in ("ver", "desfazer") for c in cmds) and len(cmds) > 1:
        raise ErroMapa("ver e desfazer vão sozinhos, fora de lote — nada foi aplicado")
    if cmds[0].split()[0] == "ver":
        partes = cmds[0].split()
        return est, resumo(est, partes[1] if len(partes) > 1 else None), []
    novo_est = copy.deepcopy({k: v for k, v in est.items() if k != "_desfazer"})
    eventos, avisos = [], []
    for c in cmds:
        try:
            args = shlex.split(c)
            antes = _marca_base(novo_est)
            if not _mesa(novo_est, args, eventos, avisos) and not _cenario_linha(novo_est, args, eventos):
                raise ErroMapa(f"comando desconhecido {args[0]!r}")
            if antes != _marca_base(novo_est):
                novo_est["base_v"] += 1
        except (ErroMapa, ValueError, IndexError) as e:
            raise ErroMapa(f"{c!r}: {e} — nada foi aplicado") from None
    novo_est["_desfazer"] = (est["_desfazer"] + [{k: v for k, v in est.items() if k != "_desfazer"}])[-MAX_DESFAZER:]
    novo_est["v"] = est["v"] + 1
    novo_est["log"] = (novo_est["log"] + [{"r": novo_est["rodada"], "cmd": c} for c in cmds])[-MAX_LOG:]
    return novo_est, "\n".join(avisos + [resumo(novo_est)]), eventos


def eventos_publicos(est: dict, eventos: list) -> list:
    """Tira da tela os eventos de tokens escondidos na névoa."""
    vis = set(publico(est)["tokens"])
    return [e for e in eventos if all(e.get(k) in vis for k in ("id", "de", "para") if k in e)]


def publico(est: dict) -> dict:
    """O que vai para a tela: sem pilha de desfazer, sem tokens na névoa."""
    nev = set(est["nevoa"])
    out = {k: v for k, v in est.items() if k not in ("_desfazer", "log")}
    out["tokens"] = {i: t for i, t in est["tokens"].items() if _k(t["pos"]) not in nev}
    return out


# ─── SVG do croqui ───────────────────────────────────────────────────────────

S = 40  # px por casa


def svg(est: dict, com_tokens: bool = False) -> str:
    """Croqui de caderno: papel, nanquim tremido, hachura. Base estática da tela."""
    W, H = est["w"] * S, est["h"] * S
    m = 28
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-m} {-m} {W + 2 * m} {H + 2 * m}" '
         f'font-family="Georgia, serif">',
         '<defs><filter id="tinta"><feTurbulence type="fractalNoise" baseFrequency=".04" numOctaves="2" seed="7"/>'
         '<feDisplacementMap in="SourceGraphic" scale="3.5"/></filter>'
         '<pattern id="hach" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         '<line x1="0" y1="0" x2="0" y2="7" stroke="#2b2116" stroke-width="1.6"/></pattern>'
         '<pattern id="onda" width="20" height="10" patternUnits="userSpaceOnUse">'
         '<path d="M0 6 q5 -5 10 0 t10 0" fill="none" stroke="#3d6b8a" stroke-width="1" opacity=".7"/></pattern>'
         '<pattern id="pont" width="8" height="8" patternUnits="userSpaceOnUse">'
         '<circle cx="2" cy="2" r=".9" fill="#5a4630"/><circle cx="6" cy="6" r=".9" fill="#5a4630"/></pattern>'
         '</defs>',
         f'<rect x="{-m}" y="{-m}" width="{W + 2 * m}" height="{H + 2 * m}" fill="#eadcb8"/>',
         '<g filter="url(#tinta)">']
    estilo = {"parede": 'fill="url(#hach)" stroke="#2b2116" stroke-width="1.2"',
              "obstaculo": 'fill="#8a7454" stroke="#2b2116" stroke-width="1.2"',
              "dificil": 'fill="url(#pont)"',
              "agua": 'fill="#9fc0cf" fill-opacity=".45"'}
    for k, tipo in est["terreno"].items():
        x, y = _c(k)
        p.append(f'<rect x="{x * S}" y="{y * S}" width="{S}" height="{S}" {estilo[tipo]}/>')
        if tipo == "agua":
            p.append(f'<rect x="{x * S}" y="{y * S}" width="{S}" height="{S}" fill="url(#onda)"/>')
    for i in range(est["w"] + 1):
        p.append(f'<line x1="{i * S}" y1="0" x2="{i * S}" y2="{H}" stroke="#7a6545" stroke-width=".5" opacity=".45"/>')
    for j in range(est["h"] + 1):
        p.append(f'<line x1="0" y1="{j * S}" x2="{W}" y2="{j * S}" stroke="#7a6545" stroke-width=".5" opacity=".45"/>')
    for k, st in est["portas"].items():
        x, y = _c(k)
        cor = "#8b1a1a" if st == "fechada" else "#6b5a3a"
        p.append(f'<rect x="{x * S + 6}" y="{y * S + 14}" width="{S - 12}" height="12" fill="#c9a66b" '
                 f'stroke="{cor}" stroke-width="2"' + ('' if st == "fechada" else ' stroke-dasharray="4 3"') + '/>')
    p.append('</g>')
    for i in range(est["w"]):
        p.append(f'<text x="{i * S + S / 2}" y="-9" text-anchor="middle" font-size="12" fill="#5a4630">{LETRAS[i]}</text>')
    for j in range(est["h"]):
        p.append(f'<text x="-10" y="{j * S + S / 2 + 4}" text-anchor="middle" font-size="12" fill="#5a4630">{j + 1}</text>')
    for r in est["rotulos"]:
        x, y = r["pos"]
        p.append(f'<text x="{x * S + S / 2}" y="{y * S + S / 2 + 5}" text-anchor="middle" font-size="15" '
                 f'font-style="italic" fill="#3b2a18">{_esc(r["texto"])}</text>')
    if est["titulo"]:
        p.append(f'<text x="{W}" y="{H + 20}" text-anchor="end" font-size="15" font-style="italic" '
                 f'fill="#3b2a18">{_esc(est["titulo"])}</text>')
    for a in est["areas"]:
        for x, y in a["celulas"]:
            p.append(f'<rect x="{x * S}" y="{y * S}" width="{S}" height="{S}" fill="#b0261c" fill-opacity=".18"/>')
    for k in est["nevoa"]:
        x, y = _c(k)
        p.append(f'<rect x="{x * S - .5}" y="{y * S - .5}" width="{S + 1}" height="{S + 1}" fill="#3a3024"/>')
    if com_tokens:
        nev = set(est["nevoa"])
        cores = {"pj": "#2f5d8a", "ali": "#3f7a4a", "ini": "#8b1a1a"}
        for t in est["tokens"].values():
            if _k(t["pos"]) in nev:
                continue
            cx, cy = t["pos"][0] * S + S / 2, t["pos"][1] * S + S / 2
            if t.get("morto"):
                p.append(f'<path d="M{cx - 10} {cy - 10} L{cx + 10} {cy + 10} M{cx + 10} {cy - 10} L{cx - 10} {cy + 10}" '
                         f'stroke="#2b2116" stroke-width="3"/>')
                continue
            p.append(f'<circle cx="{cx}" cy="{cy}" r="15" fill="#f3e9d0" stroke="{cores[t["lado"]]}" stroke-width="3"/>'
                     f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="11" fill="#2b2116">'
                     f'{_esc(t["id"][:3])}</text>')
    p.append('</svg>')
    return "".join(p)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
