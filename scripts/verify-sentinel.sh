#!/usr/bin/env bash
# Quick public verify for Sentinel family after nginx/static deploy
set -euo pipefail
for u in \
  https://sentinel.dannygc.cloud/ \
  https://stratus.dannygc.cloud/ \
  https://phantom.dannygc.cloud/ \
  https://voice.dannygc.cloud/ \
  https://ghosts.dannygc.cloud/
do
  code=$(curl -sS -o /tmp/v.body -w "%{http_code}" -A 'Mozilla/5.0' "$u" --max-time 15)
  title=$(python3 -c "import re;b=open('/tmp/v.body','rb').read().decode('utf-8','replace');m=re.search(r'<title[^>]*>(.*?)</title>',b,re.I|re.S);print(m.group(1).strip() if m else 'NO')")
  echo "$code  $u  =>  $title"
done
