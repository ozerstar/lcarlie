#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Revise only rejected creative frames, carry reviewer feedback, and re-review."""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys
KOK = pathlib.Path(__file__).resolve().parents[1]
def _karar(x): return str(x.get("direktor_karari") or "").upper()
def _notlar(x):
    out=[]
    for gorus in x.get("inceleme") or []:
        if str(gorus.get("karar") or "").upper()=="GECER": continue
        for kusur in gorus.get("kusurlar") or []:
            kusur=str(kusur).strip()
            if kusur and kusur not in out: out.append(kusur[:260])
        gerekce=str(gorus.get("gerekce") or "").strip()
        if gerekce and gerekce not in out: out.append(gerekce[:260])
    director=str(x.get("direktor_gerekce") or "").strip()
    if director and director not in out: out.insert(0,"Jarvis art director decision: "+director[:260])
    return out[:10]
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brief",type=pathlib.Path); ap.add_argument("inceleme",type=pathlib.Path)
    ap.add_argument("--urun-gorsel",required=True)
    ap.add_argument("--logo",default=str(KOK/"varliklar"/"logo"/"lcarlie-logo.png"))
    ap.add_argument("--azami-tur",type=int,default=2); a=ap.parse_args()
    brief=json.loads(a.brief.read_text(encoding="utf-8"))
    guncel=json.loads(a.inceleme.read_text(encoding="utf-8"))
    parti=a.brief.stem; son_parti=a.inceleme.parent.name.removesuffix("-gorseller")
    for tur in range(1,max(0,min(a.azami_tur,3))+1):
        rows=guncel.get("gorseller") or []
        redler=[x for x in rows if _karar(x) in ("DUZELT","RED")]
        if not redler: break
        secilen=[]
        for x in redler:
            kaynak=next((g for g in brief.get("gorseller") or [] if g.get("ad")==x.get("sahne")),None)
            if kaynak is None:
                idx=max(0,rows.index(x)); kaynak=(brief.get("gorseller") or [])[idx]
            yeni=dict(kaynak); yeni["onceki_inceleme_notlari"]=_notlar(x); secilen.append(yeni)
        rev=dict(brief); rev["gorseller"]=secilen
        bp=a.brief.parent/f"{parti}-revizyon-{tur}.json"
        bp.write_text(json.dumps(rev,ensure_ascii=False,indent=2),encoding="utf-8")
        out=a.brief.parent/f"{parti}-revizyon-{tur}-gorseller"
        print(f"REVİZYON {tur}: {len(secilen)} reddedilen kare yeniden üretiliyor",flush=True)
        run=subprocess.run([sys.executable,str(KOK/"scripts"/"gorsel-uret.py"),str(bp),
          "--urun-gorsel",a.urun_gorsel,"--logo",a.logo,"--cikti",str(out)],cwd=KOK,check=False)
        if run.returncode: print(f"REVİZYON {tur} üretim hatası; önceki teslim korunuyor",file=sys.stderr); break
        run=subprocess.run([sys.executable,str(KOK/"scripts"/"kreatif-inceleme.py"),str(out),
          "--urun-gorsel",a.urun_gorsel],cwd=KOK,check=False)
        rap=out/"inceleme.json"
        if run.returncode or not rap.exists(): print(f"REVİZYON {tur} inceleme raporu yok; onay verilmedi",file=sys.stderr); break
        guncel=json.loads(rap.read_text(encoding="utf-8")); son_parti=out.name.removesuffix("-gorseller")
        kalan=sum(1 for x in guncel.get("gorseller") or [] if _karar(x) in ("DUZELT","RED"))
        print(f"REVİZYON {tur}: {len(secilen)-kalan}/{len(secilen)} kare direktörden geçti",flush=True)
        if not kalan: break
    print("FINAL_PARTI="+son_parti)
    return 0
if __name__=="__main__": raise SystemExit(main())
