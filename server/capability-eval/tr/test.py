import json, resource, time, sys

def rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)

t0 = time.perf_counter()
import zeyrek
import_s = time.perf_counter() - t0

t1 = time.perf_counter()
analyzer = zeyrek.MorphAnalyzer()
load_s = time.perf_counter() - t1
print(json.dumps({"import_s": round(import_s, 2), "load_s": round(load_s, 2),
                  "rss_mb_after_load": rss_mb()}, ensure_ascii=False))

# The actual decision this has to make, on the real failing cases.
CASES = [
    ("yap", True), ("gönder", True), ("kaldır", True), ("artır", True),
    ("kapat", True), ("yayınla", True), ("güncelleyin", True), ("durdurun", True),
    ("yapabiliyoruz", False), ("kaldırabilir", False), ("değiştirmek", False),
    ("yapmalıyız", False), ("nasılsın", False), ("indirim", False),
    ("yapmayın", False), ("kapatsak", False),
]

print("\nword           imperative?  expected  analyses")
ok = 0
t2 = time.perf_counter()
for word, expected in CASES:
    results = analyzer.analyze(word)
    flat = [a for group in results for a in (group if isinstance(group, list) else [group])]
    formatted = []
    imperative = False
    for a in flat:
        s = str(a)
        formatted.append(s[:70])
        if "Imp" in s:
            imperative = True
    hit = (imperative == expected)
    ok += hit
    mark = "OK " if hit else "MISS"
    print(f"{mark} {word:<14} {str(imperative):<12} {str(expected):<9} {formatted[:1]}")
per_call_ms = (time.perf_counter() - t2) / len(CASES) * 1000
print(json.dumps({"correct": f"{ok}/{len(CASES)}",
                  "per_word_ms": round(per_call_ms, 2),
                  "rss_mb_final": rss_mb()}, ensure_ascii=False))
