# Fork mesa-ptbr

Fork de [neuralinitiative/claude-dnd-skill](https://github.com/neuralinitiative/claude-dnd-skill) (AGPL-3.0), feito sobre a versão 2.4.0.

## O que muda

- **Tela em português.** Ajuda (`dm_help.py`) e textos da interface.
- **Dados 3D na tela.** `display/dice3d/` e `scripts/dice.py`. Permite rolagens simultâneas e tem limite de dados.
- **Vozes dos NPCs via OpenRouter.** `display/tts.py`, com fila de voz.
- **Galeria de lugares e caderno tático.** Ficam embutidos na tela: botão 📜 Caderno ou tecla C.
- **Mapa de batalha ao vivo.** `display/mapa_estado.py` (regras e DSL), `display/mapa.py` (CLI), botão 🗺 Mapa ou tecla M. Cenários em `<campanha>/mapas/`.
- **Skin MU.** Inventário em grade e ícones, em `display/icons/mu*`.
- **Ferramentas em `skills/dnd/extras/`:**
  - `rolar.py`: rola dados na tela;
  - `galeria.py`: galeria de lugares e caderno tático;
  - `gerar_imagem.py`: gera imagens via OpenRouter;
  - `monstruario.py`;
  - `trilha.sh`: música ambiente.

  `galeria.py` e `monstruario.py` usam a campanha em `DND_CAMPANHA`.

## Instalar

```
/plugin marketplace add uaipedro/claude-dnd-skill
/plugin install dm@mesa-ptbr
```

A chave da OpenRouter fica em `~/.openrouter_api_key`. Ela nunca vai para o repositório.

## Atualizar a partir do original

```bash
git fetch upstream && git merge upstream/main
```
