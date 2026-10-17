#!/usr/bin/env bash
# Trilha sonora da mesa: baixa o áudio de uma busca no YouTube e manda tocar na tela
# (o navegador toca em loop; pausar e volume ficam no botão 🎵 da tela).
#
# Uso:
#   ./trilha.sh "título exato do vídeo"   # troca a música
#   ./trilha.sh parar                     # silêncio
#   LOCAL=1 ./trilha.sh "..."             # toca direto no PC (ffplay), sem a tela
#   VOLUME=40 LOCAL=1 ./trilha.sh "..."   # volume do modo LOCAL, de 0 a 100 (padrão 35)
#
# Confira o título antes: yt-dlp --js-runtimes node --get-title "ytsearch5:..."

set -euo pipefail

CACHE="$HOME/.claude/dnd/trilhas"
PIDFILE="$CACHE/.tocando.pid"
ATUAL="$CACHE/atual.json"
YTDLP="$HOME/.local/bin/yt-dlp"
mkdir -p "$CACHE"

parar() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
}

if [[ "${1:-}" == "parar" || -z "${1:-}" ]]; then
  parar
  printf '{"arquivo": null, "t": %s}\n' "$(date +%s)" > "$ATUAL"
  echo "trilha parada"
  exit 0
fi

busca="$1"
nome="$(echo "$busca" | tr -c 'a-zA-Z0-9' '-' | tr -s '-' | cut -c1-60)"
arquivo="$(ls "$CACHE/$nome".* 2>/dev/null | grep -v '\.part$' | head -1 || true)"

if [[ -z "$arquivo" ]]; then
  "$YTDLP" -q -x --no-playlist --js-runtimes node --max-filesize 80M \
    -o "$CACHE/$nome.%(ext)s" "ytsearch1:$busca"
  arquivo="$(ls "$CACHE/$nome".* | grep -v '\.part$' | head -1)"
fi

parar
if [[ -n "${LOCAL:-}" ]]; then
  setsid nohup ffplay -nodisp -loglevel quiet -loop 0 -volume "${VOLUME:-35}" "$arquivo" \
    >/dev/null 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
else
  python3 -c 'import json,sys,time; json.dump({"arquivo": sys.argv[1], "titulo": sys.argv[2], "t": time.time()}, open(sys.argv[3], "w"), ensure_ascii=False)' \
    "$(basename "$arquivo")" "$busca" "$ATUAL"
fi
echo "tocando: $busca"
