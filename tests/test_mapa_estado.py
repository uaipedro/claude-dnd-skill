"""Mapa de batalha ao vivo: regras e DSL (LOCAL PATCH mesa-ptbr)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "skills", "dnd", "display"))
import mapa_estado as M  # noqa: E402

CENARIO = """
grade 10x8
titulo "Cais"
parede A1-J1
dificil D4-D6
agua A8-J8
porta F1 fechada
rotulo B2 "armazém"
token caspio@B4:pj:30 "Caspio de Luna"
token snig@H4:ini:30 "Snig"
"""


@pytest.fixture
def est():
    return M.carregar_cenario(CENARIO)


def test_cenario_carrega(est):
    assert (est["w"], est["h"], est["titulo"]) == (10, 8, "Cais")
    assert est["terreno"]["0,0"] == "parede"
    assert est["tokens"]["caspio"]["nome"] == "Caspio de Luna"
    assert est["tokens"]["snig"]["lado"] == "ini"


def test_erro_de_cenario_diz_a_linha():
    with pytest.raises(M.ErroMapa, match="linha 2"):
        M.carregar_cenario("grade 5x5\nparede Z9")


def test_diagonal_custa_5():
    e = M.carregar_cenario("grade 6x6\ntoken a@A1:pj")
    novo, txt, ev = M.aplicar(e, "mv a>D4")
    assert novo["tokens"]["a"]["usou"] == 15
    assert ev[0]["rota"][0] == [0, 0] and ev[0]["rota"][-1] == [3, 3]


def test_terreno_dificil_e_limite_de_deslocamento(est):
    # B4→F4 cruza a coluna D difícil: 5+10+5+5 = 25, ou contorna por D3/D7
    novo, _, _ = M.aplicar(est, "mv caspio>F4")
    assert novo["tokens"]["caspio"]["usou"] <= 25
    with pytest.raises(M.ErroMapa, match="só tem"):
        M.aplicar(novo, "mv caspio>J4")
    forc, _, _ = M.aplicar(novo, "mv caspio>J4!")
    assert forc["tokens"]["caspio"]["pos"] == [9, 3]


def test_lote_e_atomico(est):
    with pytest.raises(M.ErroMapa, match="nada foi aplicado"):
        M.aplicar(est, "mv caspio>C4; mv fantasma>C5")
    assert est["tokens"]["caspio"]["pos"] == [1, 3]


def test_parede_e_porta_bloqueiam(est):
    with pytest.raises(M.ErroMapa, match="parede"):
        M.aplicar(est, "mv caspio>C1")
    with pytest.raises(M.ErroMapa, match="porta fechada"):
        M.aplicar(est, "mv caspio>F1")


def test_ataque_de_oportunidade(est):
    e, _, _ = M.aplicar(est, "mv caspio>G4!; turno caspio")
    _, txt, _ = M.aplicar(e, "mv caspio>D3")
    assert "AdO: snig" in txt


def test_sem_ado_quando_fica_adjacente(est):
    e, _, _ = M.aplicar(est, "mv caspio>G4!; turno caspio")
    _, txt, _ = M.aplicar(e, "mv caspio>G5")
    assert "AdO" not in txt


def test_area_diz_quem_esta_dentro(est):
    _, txt, ev = M.aplicar(est, "area esfera10 H4 \"bola de fogo\"")
    assert "bola de fogo" in txt and "snig" in txt
    assert ev[0]["t"] == "area" and [7, 3] in ev[0]["celulas"]


def test_cone_tem_largura_igual_ao_comprimento():
    e = M.novo(20, 20)
    cels = M.celulas_area(e, "cone", 15, (0, 10), (5, 10))
    assert {(1, 10), (2, 10), (3, 10)} <= set(cels)
    assert (3, 11) in cels and (1, 12) not in cels


def test_hp_dano_e_morto(est):
    e, _, _ = M.aplicar(est, "hp snig 12/20; atk caspio>snig acerto 5")
    assert e["tokens"]["snig"]["hp"] == [7, 20]
    e, txt, _ = M.aplicar(e, "dano snig 9; rm snig morto")
    assert e["tokens"]["snig"]["hp"][0] == 0 and "mortos: snig" in txt


def test_desfazer(est):
    e, _, _ = M.aplicar(est, "mv caspio>C4")
    e, _, _ = M.aplicar(e, "mv caspio>C5")
    e, txt, _ = M.aplicar(e, "desfazer")
    assert e["tokens"]["caspio"]["pos"] == [2, 3] and "desfeito" in txt


def test_prefixo_unico_resolve_token(est):
    e, _, _ = M.aplicar(est, "mv cas>C4")
    assert e["tokens"]["caspio"]["pos"] == [2, 3]


def test_nevoa_esconde_token_da_tela():
    e = M.carregar_cenario("grade 6x6\ntoken a@A1:pj\ntoken b@F6\nnevoa\nrevelar A1-C3")
    pub = M.publico(e)
    assert "a" in pub["tokens"] and "b" not in pub["tokens"]
    assert "_desfazer" not in pub


def test_base_v_so_muda_com_croqui(est):
    e, _, _ = M.aplicar(est, "mv caspio>C4")
    assert e["base_v"] == est["base_v"]
    e2, _, _ = M.aplicar(e, "porta F1 abrir")
    assert e2["base_v"] == e["base_v"] + 1


def test_ver_resume(est):
    _, txt, _ = M.aplicar(est, "ver caspio")
    assert "caspio B4" in txt and "snig 30ft" in txt


def test_svg_valido(est):
    import xml.dom.minidom
    xml.dom.minidom.parseString(M.svg(est, com_tokens=True))


def test_ver_em_lote_e_recusado(est):
    with pytest.raises(M.ErroMapa, match="sozinhos"):
        M.aplicar(est, "ver; mv caspio>C4")


def test_inimigo_caido_ainda_bloqueia_e_faz_ado(est):
    e, _, _ = M.aplicar(est, "mv caspio>G4!; cond snig +caido; turno caspio")
    _, txt, _ = M.aplicar(e, "mv caspio>D3")
    assert "AdO: snig" in txt
    with pytest.raises(M.ErroMapa, match="ocupada"):
        M.aplicar(e, "mv caspio>H4")


def test_desfazer_nao_altera_o_estado_original(est):
    e, _, _ = M.aplicar(est, "mv caspio>C4")
    n = len(e["_desfazer"])
    M.aplicar(e, "desfazer")
    assert len(e["_desfazer"]) == n


def test_eventos_na_nevoa_nao_vao_para_a_tela():
    e = M.carregar_cenario("grade 6x6\ntoken a@A1:pj\ntoken b@F6\nnevoa\nrevelar A1-C3")
    e, _, ev = M.aplicar(e, "mv b>F5; mv a>B2")
    assert [x["id"] for x in M.eventos_publicos(e, ev)] == ["a"]
