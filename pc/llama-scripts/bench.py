#!/usr/bin/env python3
"""Same measurement as the server, so the two numbers can be compared.

The server runs this exact model on 4 CPU cores and answers a
knowledge-backed product question in about 60 s. This asks the same question
of the same model on the RX 6600 over Vulkan.
"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8099/v1/chat/completions"
BASE = "Sen Jarvis'sin, L'CARLIÉ'nin yapay zekâ iş ortağısın. Kısa ve doğal Türkçe konuş."
FILLER = ("IntimBlanc hassas bölge bakım kremidir; niasinamid, alfa-arbutin ve "
          "traneksamik asit içerir. Kozmetik bakım sınırında anlatılır. ")


def run(extra_chars, label):
    system = BASE + "\n\n" + (FILLER * (extra_chars // len(FILLER) + 1))[:extra_chars]
    body = json.dumps({"messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": "Intimblanc nedir?"}],
                       "max_tokens": 160, "temperature": 0.3,
                       "stream": False, "cache_prompt": True}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    total = time.perf_counter() - t0
    t = data.get("timings") or {}
    u = data.get("usage") or {}
    return {"bilgi": label, "prompt_token": u.get("prompt_tokens"),
            "prompt_sn": round(t.get("prompt_ms", 0) / 1000, 1),
            "uretim_sn": round(t.get("predicted_ms", 0) / 1000, 1),
            "token_sn": round(t.get("predicted_per_second", 0), 1),
            "toplam_sn": round(total, 1)}


# Server numbers, measured earlier tonight on the same model and prompt.
SERVER = {0: 22.6, 1500: 51.3, 3000: 57.0, 6000: 108.0, 9000: 135.8}

print(f"{'bilgi':>10} {'prompt':>8} {'uretim':>8} {'tok/sn':>8} {'GPU':>8} {'CPU':>8} {'kazanc':>8}")
for size in (0, 1500, 3000, 4200, 6000, 9000):
    r = run(size, size)
    cpu = SERVER.get(size)
    gain = f"{cpu / r['toplam_sn']:.1f}x" if cpu else "-"
    cpu_s = f"{cpu:.1f}" if cpu else "-"
    print(f"{size:>10} {r['prompt_sn']:>8.1f} {r['uretim_sn']:>8.1f} "
          f"{r['token_sn']:>8.1f} {r['toplam_sn']:>8.1f} {cpu_s:>8} {gain:>8}")
