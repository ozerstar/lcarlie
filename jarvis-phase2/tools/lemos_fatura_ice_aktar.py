"""Mikro'dan indirilen Lemos fatura PDF'lerini içe aktar (02.11.2026). Kullanım: python neva_ice_aktar.py [--yaz] pdf...

--yaz olmadan yalnız okur ve gösterir. Satıcı / yön / tarih / toplam / kalemler faturanın kendi metninden;
kalemler faturayı tutmazsa saklanmaz (fatura toplamı kullanılır).
"""
import re
import sys

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2/webconsole")
import pymupdf  # noqa: E402

import invoice_analysis  # noqa: E402
import invoice_lines  # noqa: E402
import invoice_pdf  # noqa: E402
import money_invoices  # noqa: E402

write = "--yaz" in sys.argv
rows = []
for path in [a for a in sys.argv[1:] if a != "--yaz"]:
    doc = pymupdf.open(path)
    pages = [p.get_text() for p in doc]
    lemos = invoice_pdf.lemos_vkn(pages)
    for inv in invoice_pdf.split_invoices(pages):
        row = invoice_pdf.read(inv, lemos)
        lines = invoice_lines.read_lines(list(doc), inv["text"], row["payable_cents"], row["tax_cents"], row["party"])
        row["lines"] = lines or []
        if not row["number"]:  # 'M012025000000230': GİB numarası 3 karakter + 13 rakam (tek harfle başlayabilir)
            found = re.search(r"Fatura\s*No\s*:?\s*([A-Z0-9]{3}20\d{11})", inv["text"])
            row["number"] = found.group(1) if found else ""
        net = sum(line["net_cents"] for line in row["lines"])
        print(f"{row['date']} {row['box']} {row['number'] or '-':<17} {row['party'][:40]:<40} VKN {row['party_vkn']} "
              f"ödenecek {row['payable_cents'] / 100:,.2f} KDV {row['tax_cents'] / 100:,.2f} kalem {len(row['lines'])} "
              f"kalem toplamı {net / 100:,.2f} {'TUTUYOR' if net == row['payable_cents'] - row['tax_cents'] else 'TUTMUYOR'}")
        rows.append(row)
if write:
    print("içe aktarma:", money_invoices.import_pdf("operator", "lemos", rows))
    from expense_vault import _connect
    with _connect() as conn, conn.cursor() as cur:  # zaten kayıtlı olup numarası okunamamış faturalar
        for row in rows:
            if row["number"]:
                cur.execute("""UPDATE core.jarvis_invoice SET number=%s WHERE owner='operator' AND document_id=%s
                    AND coalesce(number,'')=''""", (row["number"], row["ettn"]))
                if cur.rowcount:
                    print("   numara eklendi:", row["number"])
    print("yeniden sınıflandırılan:", invoice_analysis.classify_all("operator"))
    costs = invoice_analysis.product_costs("operator")
    print(len(costs), "ürünün gerçek maliyeti:")
    for name, c in sorted(costs.items()):
        print(f"   {name:<14} {c['unit'] / 100:>7.2f} TL  {c['date']}  {int(c['qty'])} adet")
