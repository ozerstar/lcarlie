import json, resource, sys, time
from docling.document_converter import DocumentConverter

path = sys.argv[1]
t0 = time.perf_counter()
conv = DocumentConverter()
t_init = time.perf_counter() - t0

t1 = time.perf_counter()
result = conv.convert(path)
t_conv = time.perf_counter() - t1

doc = result.document
md = doc.export_to_markdown()
tables = getattr(doc, "tables", []) or []
texts = getattr(doc, "texts", []) or []
headings = [t.text for t in texts if getattr(t, "label", "") == "section_header"]

print(json.dumps({
    "init_s": round(t_init, 2),
    "convert_s": round(t_conv, 2),
    "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    "markdown_chars": len(md),
    "tables": len(tables),
    "text_blocks": len(texts),
    "headings_found": headings[:8],
    "provenance_available": bool(getattr(texts[0], "prov", None)) if texts else False,
    "markdown_head": md[:600],
}, ensure_ascii=False, indent=1))
