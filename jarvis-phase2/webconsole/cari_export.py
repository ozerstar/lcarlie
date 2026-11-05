"""Authenticated, owner-scoped PDF and genuine XLSX reports; no mutations."""
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as xml_escape
import html,re,zipfile,threading
from pathlib import Path
import cari,cari_invoice,cari_reconciliation

# Müşteriye giden belgede durum MÜŞTERİNİN gözünden yazılır; "Alacaklıyız" bizim dilimizdir.
CUSTOMER_STATUS={'Alacaklıyız':'Ödemeniz bekleniyor','Borçluyuz':'Alacak bakiyeniz var','Hesap kapalı':'Hesap kapalı','KDV bekleniyor':'KDV oranı netleşecek'}
def customer_status(status):return CUSTOMER_STATUS.get(status,status)
LABELS={'sale':'Satış','purchase':'Alış','sale_return':'Müşteriden iade','purchase_return':'Tedarikçiye iade','collection':'Tahsilat','payment':'Ödeme','opening_receivable':'Açılış alacağı','opening_payable':'Açılış borcu','gift_out':'Bedelsiz verildi','gift_in':'Bedelsiz alındı'}
FIRM_FILE=Path(__file__).resolve().parent/'cari_firma.json'
FIRM_FIELDS=[('unvan','Unvan'),('vergi_dairesi','Vergi dairesi'),('vergi_no','VKN'),('mersis','MERSİS no'),('adres','Adres'),('telefon','Telefon'),('eposta','E-posta'),('banka','Banka'),('hesap_sahibi','Hesap sahibi'),('iban','IBAN')]
def firm():
    # Sahibin girdiği satıcı bilgisi; dosya yoksa belgeye hiç yazılmaz, uydurulmaz.
    try:
        import json
        data=json.loads(FIRM_FILE.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return {}
    return {k:text(data.get(k,'')).strip() for k,_ in FIRM_FIELDS if text(data.get(k,'')).strip()}
def effective_entries(entries):
    reversed_ids={e['reverses'] for e in entries if e.get('reverses')}
    return [e for e in entries if not e.get('reverses') and e['id'] not in reversed_ids]
def amount(n):return 'Belirlenmedi' if n is None else Decimal(n)/100
def text(value):return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value if value is not None else ''))
def sheets(owner,account_id,scope,as_of=None):
    stamp=datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')
    if scope=='portfolio':
        report=cari.portfolio(owner,as_of)
        rows=[['Cari','Alacak TL','Borç TL','Bakiye TL','KDV durumu']]
        for a in report['accounts']:
            balance=a['balance_cents']
            rows.append([a['name'],amount(max(0,balance)),amount(max(0,-balance)),amount(balance),'Belirsiz KDV var' if a.get('unknown_tax_documents') else 'Kayıtlara göre'])
        return 'Cari hesaplar', [('Rapor bilgisi',[['Alan','Açıklama'],['Hazırlanma',stamp],['Rapor tarihi',report['as_of']],['Kapsam','Kesinleşmiş cari hareketleri. Mutabakat ön hesapları bakiyeye dahil değildir.']]),('Cari hesaplar',rows)]
    statement=cari.statement(owner,account_id)
    a=statement['account'];summary=statement['summary']
    tables=[('Cari özeti',[['Alan','Bilgi'],['Cari',a['name']],['Vergi dairesi / no',' · '.join(x for x in (a.get('tax_office'),a.get('tax_id')) if x)],['Adres',a.get('address','')],['İletişim',' · '.join(x for x in (a.get('contact'),a.get('email'),a.get('phone')) if x)],['Hazırlanma',stamp],['Bakiye TL',amount(summary['balance_cents'])],['Durum',customer_status(summary['status'])],['KDV','Fiyatlar PSF üzerinden, KDV %20 dahil' if any(r.get('price_basis')=='psf_kdv_dahil' for r in statement['product_tables'].get('sale',{}).get('rows',[])) else 'Belgelerdeki KDV oranlarına göre'],['Kapsam','Bakiye kesinleşmiş cari hareketlerine göre hazırlanmıştır.']])]
    if scope=='account':
        for key,label in [('sale','Satın aldığınız ürünler'),('purchase','Bize sattığınız ürünler'),('gift','Bedelsiz ürünler')]:
            data=statement['product_tables'].get(key,{})
            if key=='gift':
                rows=[['Ürün','Adet']]+[[p['name'],p['quantity']] for p in data.get('rows',[])]
            else:
                rows=[['Ürün','Adet','PSF (KDV dahil) TL','İskonto','İskontolu birim KDV hariç TL','İskontolu birim KDV dahil TL','Tutar KDV hariç TL','Tutar KDV dahil TL']]
                for p in data.get('rows',[]):
                    rows.append([p['name'],p['quantity'],amount(p['recommended_price_cents']) if p['recommended_price_cents'] is not None else '—','%'+text(Decimal(p['discount']).normalize()),amount(p['unit_excl_cents']),amount(p['unit_incl_cents']),amount(p['net_excl_cents']),amount(p['net_incl_cents'])])
                if len(rows)>1:rows.append(['GENEL TOPLAM',data['quantity'],'','','','',amount(data['net_excl_cents']),amount(data['net_incl_cents'])])
            tables.append((label,rows))
        # Müşteri belgesi: yalnız geçerli kayıtlar. İptal edilen belge ve onun ters
        # kaydı birbirini sıfırlar; bakiye aynı kalır, belge sadeleşir.
        rows=[['Tarih','Hareket','Belge','Borç TL','Alacak TL','Bakiye TL']];balance=0
        for e in effective_entries(statement['entries']):
            p=e['payload'];signed=p['signed_cents'];balance+=signed
            rows.append(['.'.join(reversed(p['date'].split('-'))),LABELS.get(p['kind'],'Hareket'),p.get('reference',''),amount(max(0,signed)),amount(max(0,-signed)),amount(balance)])
        if len(rows)>1:rows.append(['GÜNCEL BAKİYE','','','','',amount(balance)])
        tables.append(('Hesap ekstresi',rows))
        seller=firm()
        if seller:tables.append(('Ödeme bilgileri',[['Alan','Bilgi']]+[[label,seller[k]] for k,label in FIRM_FIELDS if k in seller]))
    docs=cari_invoice.list_documents(owner,a['id'])['documents']
    active=[d['extracted']['cari_reconciliation'] for d in docs if d['source']=='attachment' and isinstance(d.get('extracted'),dict) and d['extracted'].get('cari_reconciliation',{}).get('status')=='pending']
    if active:tables[0][1][7]=['Durum','Mutabakat bekliyor; bakiye yalnız kesinleşmiş hareketlere aittir.']
    for index,raw in enumerate(active):
        r=cari_reconciliation.recalculate(raw);suffix='' if len(active)==1 else ' '+str(index+1);c=r['price_comparison']
        tables.append(('Mutabakat özeti'+suffix,[['Alan','Bilgi'],['Durum','Ön hesap; kesin mali kayıt değildir'],['İlk liste hesaplanan TL',amount(c['initial_cents'])],['İlk liste gelen ödeme TL',amount(c['initial_received_cents'])],['İlk liste fark TL',amount(c['gap_cents'])],['Ek %5 senaryosu TL',amount(c['initial_alternative_cents'])],['Ek ücretli teslim TL',amount(c['extra_cents'])],['Ek teslim gelen ödeme TL',amount(c['extra_received_cents'])],['Seçilen ek iskonto %',Decimal(r.get('extra_discount_bps',0))/100],['Fatura bilgisi',r.get('invoice_note','')],['Hesap açıklaması',r['estimate_note']],['Bekleyen bilgiler',r['pending_note']]]))
        deliveries=[['Ürün','İlk liste adedi','Liste içi hediye','Ek ücretli adet','İlave hediye','Toplam teslim','PSF TL','Ürün iskontosu %','İndirimli birim TL','İlk liste tutarı TL','Ek birim TL']]
        returns=[['Ürün','İstenen adet','Hediye mahsubu','Ücretli adet','Birim TL','Ön iade tutarı TL','Ek %5 senaryosu TL']]
        prices=[['Ürün','PSF TL','Ürün iskontosu %','İndirimli birim TL','İlk liste bedelli tutarı TL','Ek teslim birim TL']]
        for p in r['products']:
            extra_gift=p.get('additional_gift_quantity',0);delivery=p['initial_quantity']+p['additional_quantity']+extra_gift
            deliveries.append([p['name'],p['initial_quantity'],p.get('initial_gift_quantity',0),p['additional_quantity'],extra_gift,delivery,amount(p.get('reference_psf_cents')),Decimal(p.get('discount_bps',4000))/100,amount(p['initial_discounted_unit_cents']),amount(p['initial_estimate_cents']),amount(p['additional_unit_price_cents'])])
            prices.append([p['name'],amount(p.get('reference_psf_cents')),Decimal(p.get('discount_bps',4000))/100,amount(p['initial_discounted_unit_cents']),amount(p['initial_estimate_cents']),amount(p['additional_unit_price_cents'])])
            if p['return_quantity']:returns.append([p['name'],p['return_quantity'],p['return_gift_offset_quantity'],p['refundable_return_quantity'],amount(p['return_unit_estimate_cents']),amount(p['return_estimate_cents']),amount(p['return_alternative_cents'])])
        total=lambda key:None if any(p[key] is None for p in r['products'] if p['return_quantity']) else sum(p[key] for p in r['products'] if p['return_quantity'])  # noqa: B023
        returns.append(['Toplam',sum(p['return_quantity'] for p in r['products']),sum(p['return_gift_offset_quantity'] for p in r['products']),sum(p['refundable_return_quantity'] for p in r['products']),'',amount(total('return_estimate_cents')),amount(total('return_alternative_cents'))])
        tables.extend([('Teslim ve hediyeler'+suffix,deliveries),('Fiyat ve iskontolar'+suffix,prices),('İade talebi'+suffix,returns),('Bildirilen ödemeler'+suffix,[['Açıklama','Tutar TL','Tarih']]+[[p['label'],amount(p['amount_cents']),p.get('date') or 'Bildirilmedi'] for p in r['payments']])])
    if not active and scope=='reconciliation':raise cari.CariNotFound('Bu caride düzenlenebilir mutabakat bulunamadı.')
    return a['name'],tables

# --------------------------------------------------------------------------
# Tasarım sistemi (sahip brifi 05.11.2026). PDF ve Excel aynı paleti, aynı
# özeti ve aynı hazırlanma zamanını kullanır.
# --------------------------------------------------------------------------
GREEN,SAGE,PAPER,GOLD,CORAL='244F43','DCE9DD','F8F6F1','B58A4A','C8664F'
INK,MUTED,LINE,WHITE='1F2D27','5F6E66','D9DDD3','FFFFFF'
LOGO=Path(__file__).resolve().parent/'static'/'img'/'lcarlie-mark-dark.png'
TOTALS=('GENEL TOPLAM','GÜNCEL BAKİYE','Toplam')
PRODUCT_HEAD=['Ürün','Adet','PSF (KDV dahil) TL','İskonto','İskontolu birim KDV hariç TL','İskontolu birim KDV dahil TL','Tutar KDV hariç TL','Tutar KDV dahil TL']
LEDGER_HEAD=['Tarih','Hareket','Belge','Borç TL','Alacak TL','Bakiye TL']
def is_total(row):return bool(row) and isinstance(row[0],str) and row[0] in TOTALS
def doc_title(title):return 'CARİ HESAP LİSTESİ' if title=='Cari hesaplar' else 'CARİ HESAP EKSTRESİ'
def now():return datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')
def number_text(v):return f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def tl(v):return number_text(v)+' TL' if isinstance(v,Decimal) else text(v)
def split_iban(value):
    m=re.match(r'^(.*?)\s*\(([A-Z]{3})\)\s*$',value or '')
    return (m.group(1),m.group(2)) if m else (value or '',None)

def report_meta(title,tables):
    """PDF ve Excel'in ortak özeti. Her alan tablolardan okunur; yoksa boş kalır."""
    first=dict((r[0],r[1]) for r in tables[0][1][1:] if len(r)>1) if tables and tables[0][1][:1] in ([['Alan','Bilgi']],[['Alan','Açıklama']]) else {}
    stamp=first.get('Hazırlanma') or now()
    sales=next((rows for name,rows in tables if rows and rows[0]==PRODUCT_HEAD),None)
    total=sales[-1] if sales and is_total(sales[-1]) else None
    as_of=first.get('Rapor tarihi')
    if as_of and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(as_of)):as_of='.'.join(reversed(str(as_of).split('-')))
    return {'title':title,'stamp':stamp,'date':as_of or str(stamp)[:10],
            'balance':first.get('Bakiye TL') if isinstance(first.get('Bakiye TL'),Decimal) else None,
            'status':first.get('Durum') or '',
            'products':total[1] if total else None,'kinds':len(sales)-2 if total else None}

# ------------------------------------------------------------------- Excel
def xlsx(tables,title='',meta=None):
    """Tek sayfalık Excel: telefonda alt sekmeler görünmediği için (sahip 05.11.2026)
    PDF'teki sırayla her bölüm aynı sayfada alt alta durur. Toplamlar formüldür."""
    # Inline string cells keep names beginning with =, +, - or @ inert.
    meta=meta or report_meta(title,tables)
    out=BytesIO();ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    col=lambda i:chr(65+i) if i<26 else chr(64+i//26)+chr(65+i%26)
    tables=[t for t in tables if len(t[1])>1] or tables[:1]
    logo=LOGO.read_bytes() if LOGO.exists() else None
    width=max(8,max(len(rows[0]) for _,rows in tables))
    last_col=col(width-1)
    fonts=[('10',INK,''),('10',GREEN,'<b/>'),('22',GREEN,'<b/>'),('9',MUTED,''),('10',INK,'<b/>'),('8',MUTED,'<b/>'),
           ('20',GREEN,'<b/>'),('13',INK,'<b/>'),('8',GOLD,'<b/>'),('14',GREEN,'<b/>'),('10',CORAL,'<b/>'),('11',GREEN,'<b/>'),('13',GREEN,'<b/>')]
    font_xml=''.join(f'<font>{b}<sz val="{sz}"/><color rgb="FF{c}"/><name val="{"Consolas" if i==9 else "Calibri"}"/></font>' for i,(sz,c,b) in enumerate(fonts))
    fill=lambda c:f'<fill><patternFill patternType="solid"><fgColor rgb="FF{c}"/><bgColor indexed="64"/></patternFill></fill>'
    fills='<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'+''.join(fill(c) for c in (GREEN,PAPER,SAGE,GOLD,WHITE))
    side=lambda kind,c,w='thin':f'<{kind} style="{w}"><color rgb="FF{c}"/></{kind}>'
    borders=('<border/>'
             f'<border><left/><right/><top/>{side("bottom",LINE)}<diagonal/></border>'
             f'<border><left/><right/>{side("top",GOLD,"medium")}{side("bottom",LINE)}<diagonal/></border>'
             f'<border>{side("left",GOLD)}{side("right",GOLD)}{side("top",GOLD)}{side("bottom",GOLD)}<diagonal/></border>'
             f'<border><left/><right/><top/>{side("bottom",GOLD)}<diagonal/></border>'
             f'<border><left/><right/><top/>{side("bottom",GREEN)}<diagonal/></border>')
    S={};xfs=[]
    def style(name,font=0,fill_=0,border=0,num=0,h='left',wrap=False,v='center'):
        S[name]=len(xfs)
        xfs.append(f'<xf numFmtId="{num}" fontId="{font}" fillId="{fill_}" borderId="{border}" xfId="0" applyFont="1" applyFill="1" applyBorder="1"'
                   +(' applyNumberFormat="1"' if num else '')+f' applyAlignment="1"><alignment horizontal="{h}" vertical="{v}"'+(' wrapText="1"' if wrap else '')+'/></xf>')
    style('default')
    style('head',1,4,5,0,'center',True);style('head_l',1,4,5,0,'left',True);style('head_r',1,4,5,0,'right',True);style('group',1,4,4,0,'center',True)
    style('text',0,0,1,0,'left',True);style('money',0,0,1,164,'right');style('int',0,0,1,3,'right');style('center',0,0,1,0,'center')
    style('money_strong',11,3,1,164,'right')
    style('title',2);style('sub',3);style('bar',0,5);style('section',12,0,4)
    style('total_text',4,0,2);style('total_money',4,0,2,164,'right');style('total_int',4,0,2,3,'right');style('total_blank',4,0,2)
    style('total_strong',12,3,2,164,'right')
    style('kpi_label',5,0,0);style('kpi_label_gold',8,0,0,0,'right');style('kpi_value',7,0,0);style('kpi_count',7,0,0,165);style('kpi_money_s',7,0,0,164,'left')
    style('kpi_balance',6,0,0,164,'right');style('kpi_note',3,0,0,0,'left',True);style('kpi_note_r',3,0,0,0,'right');style('kpi_status',10,0,0,0,'right')
    style('strip',0,0,1)
    style('key',3,0,1,0,'left',True,'top');style('value',4,0,1,0,'left',True,'top')
    style('iban',9,3,3,0,'left');style('iban_key',8,3,3);style('iban_small',3,3,3,0,'left')
    style('official_key',3,0,0,0,'left',True,'top');style('official_value',0,0,0,0,'left',True,'top')
    cells_by_row={};heights={};merges=[];breaks=[];autofilter=None
    def put(r,ci,value,st,formula=None):
        ref=f'{col(ci)}{r}';s_=S[st]
        if formula is not None:
            xml=f'<c r="{ref}" s="{s_}"><f>{xml_escape(formula)}</f>'+('' if value in (None,'') else f'<v>{value}</v>')+'</c>'
        elif isinstance(value,(int,Decimal)) and not isinstance(value,bool):xml=f'<c r="{ref}" s="{s_}"><v>{value}</v></c>'
        elif value in (None,''):xml=f'<c r="{ref}" s="{s_}"/>'
        else:xml=f'<c r="{ref}" s="{s_}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(text(value))}</t></is></c>'
        cells_by_row.setdefault(r,{})[ci]=xml
    def span(r,a,b,value,st,formula=None):
        put(r,a,value,st,formula)
        for ci in range(a+1,b+1):put(r,ci,None,st)
        if b>a:merges.append(f'{col(a)}{r}:{col(b)}{r}')
    # --- başlık
    heights[1]=40
    span(2,0,width-1,meta.get('title') or title or 'L’CARLIÉ','title');heights[2]=32
    span(3,0,width-1,f"{'Cari hesap listesi' if title=='Cari hesaplar' else 'Cari hesap ekstresi'} · Rapor tarihi {meta['date']} · Hazırlanma {meta['stamp']}",'sub')
    for ci in range(width):put(4,ci,None,'bar')
    heights[4]=4;r=6
    first=dict((x[0],x[1]) for x in tables[0][1][1:] if len(x)>1) if tables else {}
    # Bölüm satır numaraları formül bağları için önceden bilinmeli: önce yerleşimi hesapla.
    plan=[];cursor=r+(5 if meta.get('balance') is not None else 0)
    for name,rows in tables:
        kind='product' if rows[0]==PRODUCT_HEAD else 'ledger' if rows[0]==LEDGER_HEAD else 'pay' if name=='Ödeme bilgileri' else 'pairs' if rows[0] in (['Alan','Bilgi'],['Alan','Açıklama']) else 'grid'
        if kind=='pairs' and name in ('Cari özeti','Rapor bilgisi'):
            extra=[(a,b) for a,b in ((x[0],x[1]) for x in rows[1:]) if a in ('Vergi dairesi / no','Adres','İletişim') and text(b)] if meta.get('balance') is not None else [(x[0],x[1]) for x in rows[1:] if text(x[1])]
            if not extra:continue
            rows=[rows[0]]+[list(x) for x in extra]
        start=cursor+2  # bölüm başlığı + boşluk
        header=2 if kind=='product' else 1 if kind in ('ledger','grid') else 0
        if kind=='pay':
            keys=[x[0] for x in rows[1:] if text(x[1])]
            body_rows=sum(k_ in keys for k_ in ('Banka','Hesap sahibi'))+(2 if 'IBAN' in keys else 0)+2+sum(k_ not in ('Banka','Hesap sahibi','IBAN') for k_ in keys)
        else:
            body_rows=len(rows)-1
        plan.append((name,rows,kind,start,header))
        cursor=start+header+body_rows+1
    def total_cell(kind_,column):
        for _name,rows,kind,start,header in plan:
            if kind==kind_ and is_total(rows[-1]):return f'{column}{start+header+len(rows)-2}'
        return None
    # --- özet (PDF 1. sayfa ile aynı içerik)
    if meta.get('balance') is not None:
        sales=next((rows for _n,rows,k,_s,_h in plan if k=='product'),None)
        sale_total=sales[-1] if sales and is_total(sales[-1]) else None
        discounts={text(x[3]) for x in (sales or [])[1:] if not is_total(x)}
        psf='PSF' in text(first.get('KDV'))
        span(r,width-3,width-1,'GÜNCEL BAKİYE','kpi_label_gold')
        span(r+1,width-3,width-1,meta['balance'],'kpi_balance',total_cell('ledger','F'));heights[r+1]=30
        span(r+2,width-3,width-1,meta['status'],'kpi_status')
        span(r,0,1,'TOPLAM ÜRÜN','kpi_label');span(r,2,3,'KDV HARİÇ TUTAR','kpi_label')
        span(r+1,0,1,meta['products'] if meta['products'] is not None else '—','kpi_count' if meta['products'] is not None else 'kpi_value',total_cell('product','B') if meta['products'] is not None else None)
        span(r+1,2,3,sale_total[6] if sale_total else '—','kpi_money_s' if sale_total else 'kpi_value',total_cell('product','G') if sale_total else None)
        span(r+2,0,1,f"{meta['kinds']} çeşit ürün" if meta['kinds'] is not None else '','kpi_note')
        span(r+2,2,3,('PSF' if psf else 'Belge fiyatı')+(f' · {next(iter(discounts))} iskonto' if len(discounts)==1 else '')+(' · KDV %20 dahil' if psf else ''),'kpi_note')
        for ci in range(width):put(r+3,ci,None,'strip')
        heights[r+3]=6
    # --- bölümler
    for name,rows,kind,start,header in plan:  # noqa: B007 - header yalnız bazı türlerde kullanılır
        span(start-1,0,width-1,name,'section');heights[start-1]=24
        if kind=='product':
            g=[('Ürün',0,0),('Adet',1,1),('PSF (KDV dahil)',2,2),('İskonto',3,3),('İskontolu birim fiyat',4,5),('Tutar',6,7)]
            for t,a,b in g:
                put(start,a,t,'group' if a>=4 else ('head_l' if a==0 else 'head'))
                if a==b:put(start+1,a,None,'head');merges.append(f'{col(a)}{start}:{col(a)}{start+1}')
                else:put(start,b,None,'group');merges.append(f'{col(a)}{start}:{col(b)}{start}')
            for i,t in enumerate(['KDV hariç','KDV dahil','KDV hariç','KDV dahil'],4):put(start+1,i,t,'head')
            heights[start]=heights[start+1]=20
            first_row=start+2;last_row=first_row+len(rows)-3
            for i,x in enumerate(rows[1:]):
                rn=first_row+i
                if is_total(x):
                    put(rn,0,x[0],'total_text');put(rn,1,x[1],'total_int',f'SUM(B{first_row}:B{last_row})')
                    for ci in (2,3,4,5):put(rn,ci,None,'total_blank')
                    put(rn,6,x[6],'total_money',f'SUM(G{first_row}:G{last_row})');put(rn,7,x[7],'total_strong',f'SUM(H{first_row}:H{last_row})')
                    heights[rn]=24;continue
                put(rn,0,x[0],'text');put(rn,1,x[1],'int');put(rn,2,x[2],'money' if isinstance(x[2],Decimal) else 'center');put(rn,3,x[3],'center')
                for ci in (4,5,6):put(rn,ci,x[ci],'money')
                put(rn,7,x[7],'money_strong');heights[rn]=20
            autofilter=f'A{start+1}:H{last_row}'
        elif kind in ('ledger','grid'):
            numeric={j for x in rows[1:] for j,v in enumerate(x) if isinstance(v,(int,Decimal)) and not isinstance(v,bool)}
            for j,t in enumerate(rows[0]):put(start,j,t.replace(' TL','') if kind=='ledger' else t,'head_r' if j in numeric else 'head_l')
            heights[start]=22
            if kind=='ledger':breaks.append(start-2)  # PDF gibi: ekstre ikinci sayfada başlar
            for i,x in enumerate(rows[1:]):
                rn=start+1+i;tot=is_total(x)
                if kind=='ledger':
                    if tot:
                        put(rn,0,x[0],'total_text')
                        for ci in (1,2,3,4):put(rn,ci,None,'total_blank')
                        put(rn,5,x[5],'total_strong',f'F{rn-1}');heights[rn]=24;continue
                    put(rn,0,x[0],'text');put(rn,1,x[1],'text');put(rn,2,x[2],'text');put(rn,3,x[3],'money');put(rn,4,x[4],'money')
                    put(rn,5,x[5],'money',f'D{rn}-E{rn}' if i==0 else f'F{rn-1}+D{rn}-E{rn}');heights[rn]=20
                else:
                    for j,v in enumerate(x):
                        st=('total_money' if isinstance(v,Decimal) else 'total_int' if isinstance(v,int) else 'total_text') if tot else ('money' if isinstance(v,Decimal) else 'int' if isinstance(v,int) else 'text')
                        put(rn,j,v,st)
        elif kind=='pay':
            info=[(x[0],x[1]) for x in rows[1:]];rn=start
            for k_ in ('Banka','Hesap sahibi'):
                v=dict(info).get(k_)
                if v:put(rn,0,k_,'key');span(rn,1,width-1,v,'value');heights[rn]=20;rn+=1
            iban=text(dict(info).get('IBAN'))
            if iban:
                number_,currency=split_iban(iban)
                put(rn,0,'IBAN'+(f' · {currency}' if currency else ''),'iban_key');span(rn,1,width-1,number_,'iban');heights[rn]=28;rn+=1
                put(rn,0,'IBAN (boşluksuz)','iban_key');span(rn,1,width-1,re.sub(r'\s','',number_),'iban_small');heights[rn]=20;rn+=1
            rn+=1;span(rn,0,width-1,'Resmî şirket bilgileri','kpi_label');rn+=1
            for k_,v in info:
                if k_ in ('Banka','Hesap sahibi','IBAN') or not text(v):continue
                put(rn,0,k_,'official_key');span(rn,1,width-1,v,'official_value');heights[rn]=30 if len(text(v))>90 else 16;rn+=1
        else:
            for i,x in enumerate(rows[1:]):
                rn=start+i;put(rn,0,x[0],'key');span(rn,1,width-1,x[1],'value' if not isinstance(x[1],Decimal) else 'money')
                heights[rn]=30 if len(text(x[1]))>90 else 20
    data=''.join(f'<row r="{rn}"'+(f' ht="{heights[rn]}" customHeight="1"' if rn in heights else '')+'>'+''.join(cells_by_row.get(rn,{})[ci] for ci in sorted(cells_by_row.get(rn,{})))+'</row>'
                 for rn in sorted(set(cells_by_row)|set(heights)))
    widths=[26,10,17,11,17,17,17,17]+[16]*(width-8)
    columns=''.join(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i,w in enumerate(widths[:width]))
    merge_xml=f'<mergeCells count="{len(merges)}">'+''.join(f'<mergeCell ref="{m}"/>' for m in merges)+'</mergeCells>' if merges else ''
    break_xml=f'<rowBreaks count="{len(breaks)}" manualBreakCount="{len(breaks)}">'+''.join(f'<brk id="{b}" max="16383" man="1"/>' for b in breaks)+'</rowBreaks>' if breaks else ''
    footer='<headerFooter><oddFooter>&amp;L&amp;8L’CARLIÉ · '+xml_escape(text(meta.get('title') or title))+'&amp;R&amp;8Sayfa &amp;P / &amp;N</oddFooter></headerFooter>'
    sheet_name='Cari ekstre' if title!='Cari hesaplar' else 'Cari hesaplar'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'+('<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' if logo else '')+'</Types>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{rel}/styles" Target="styles.xml"/></Relationships>')
        numfmts='<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;TL&quot;"/><numFmt numFmtId="165" formatCode="#,##0\\ &quot;adet&quot;"/></numFmts>'
        assert len(fonts)==13
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}">{numfmts}<fonts count="{len(fonts)}">{font_xml}</fonts><fills count="7">{fills}</fills><borders count="6">{borders}</borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}" xmlns:r="{rel}"><sheetPr><tabColor rgb="FF{GREEN}"/><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:{last_col}{max(set(cells_by_row)|{1})}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0" tabSelected="1" zoomScale="100"/></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>{columns}</cols><sheetData>{data}</sheetData>'
                   +(f'<autoFilter ref="{autofilter}"/>' if autofilter else '')+f'{merge_xml}<printOptions horizontalCentered="1"/><pageMargins left="0.5" right="0.5" top="0.6" bottom="0.7" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>{footer}{break_xml}'+('<drawing r:id="rId1"/>' if logo else '')+'</worksheet>')
        if logo:
            cx,cy=230*9525,32*9525
            z.writestr('xl/media/logo.png',logo)
            z.writestr('xl/worksheets/_rels/sheet1.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
            z.writestr('xl/drawings/_rels/drawing1.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/image" Target="../media/logo.png"/></Relationships>')
            z.writestr('xl/drawings/drawing1.xml',f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{rel}"><xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>57150</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>95250</xdr:rowOff></xdr:from><xdr:ext cx="{cx}" cy="{cy}"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="2" name="Logo"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>')
    return out.getvalue()


# --------------------------------------------------------------------- PDF
_font_lock=threading.Lock()
def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _font_lock:
        if 'CariTR' in pdfmetrics.getRegisteredFontNames():return
        base='/usr/share/fonts/truetype/dejavu/'
        files=(base+'DejaVuSans.ttf',base+'DejaVuSans-Bold.ttf',base+'DejaVuSansMono-Bold.ttf')
        if not Path(files[0]).exists():files=('C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/arialbd.ttf','C:/Windows/Fonts/consolab.ttf')
        for name,path in zip(('CariTR','CariTRBold','CariMono'),files,strict=True):
            pdfmetrics.registerFont(TTFont(name,path if Path(path).exists() else files[1]))

def pdf(title,tables,meta=None):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT,TA_CENTER
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.pdfgen.canvas import Canvas
    _fonts()
    meta=meta or report_meta(title,tables)
    k=lambda h:colors.HexColor('#'+h)
    P=lambda name,**kw:ParagraphStyle(name,**{'fontName':'CariTR','fontSize':8.8,'leading':11.5,'textColor':k(INK),**kw})
    body=P('body');right=P('right',alignment=TA_RIGHT)
    bold=P('bold',fontName='CariTRBold');bold_right=P('boldr',fontName='CariTRBold',alignment=TA_RIGHT)
    strong=P('strong',fontName='CariTRBold',textColor=k(GREEN),alignment=TA_RIGHT)
    strong_total=P('strongt',fontName='CariTRBold',fontSize=11,leading=14,textColor=k(GREEN),alignment=TA_RIGHT)
    head=P('head',fontName='CariTRBold',textColor=k(GREEN),fontSize=7.8,leading=10);head_c=P('headc',parent=head,alignment=TA_CENTER);head_r=P('headr',parent=head,alignment=TA_RIGHT)
    eyebrow=P('eye',fontName='CariTRBold',fontSize=7.8,textColor=k(GOLD),leading=10)
    muted=P('muted',fontSize=8,leading=11,textColor=k(MUTED))
    section=P('section',fontName='CariTRBold',fontSize=12.5,leading=16,textColor=k(GREEN),spaceBefore=6,spaceAfter=0,keepWithNext=1)
    page=landscape(A4);margin=40;available=page[0]-2*margin
    def esc(v):return html.escape(text(v))
    def cell(v,st=body):
        if isinstance(v,(int,Decimal)) and not isinstance(v,bool):st={body:right,bold:bold_right}.get(st,st)
        return Paragraph(esc(tl(v) if isinstance(v,Decimal) else v),st)
    def heading(textv):return [Paragraph(esc(textv),section),HRFlowable(width=30,thickness=1.6,color=k(GOLD),hAlign='LEFT',spaceBefore=4,spaceAfter=8)]
    pad=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5.5),('BOTTOMPADDING',(0,0),(-1,-1),5.5),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]
    first=dict((r[0],r[1]) for r in tables[0][1][1:] if len(r)>1) if tables else {}
    story=[]
    # --- 1. sayfa: kimlik + bakiye ------------------------------------------------
    left=[Paragraph('CARİ HESAP ÖZETİ' if title!='Cari hesaplar' else 'CARİ HESAPLAR',eyebrow),Spacer(1,3),
          Paragraph(esc(meta.get('title') or title),P('name',fontName='CariTRBold',fontSize=28,leading=32,textColor=k(GREEN))),Spacer(1,4),
          Paragraph(f"Rapor tarihi <b>{esc(meta['date'])}</b>  ·  Hazırlanma {esc(meta['stamp'])}",muted)]
    extra=[f"{esc(a)}: {esc(b)}" for a,b in first.items() if a in ('Vergi dairesi / no','Adres','İletişim') and text(b)]
    if extra:left+=[Spacer(1,3),Paragraph('  ·  '.join(extra),muted)]
    if meta.get('balance') is not None:
        balance=[Paragraph('GÜNCEL BAKİYE',P('bl',fontName='CariTRBold',fontSize=7.8,leading=10,textColor=k(GOLD),alignment=TA_RIGHT)),Spacer(1,4),
                 Paragraph(esc(tl(meta['balance'])),P('bv',fontName='CariTRBold',fontSize=30,leading=34,textColor=k(GREEN),alignment=TA_RIGHT)),Spacer(1,3),
                 Paragraph(f"KDV dahil  ·  <font color='#{CORAL}'><b>{esc(meta['status'])}</b></font>",P('bs',fontSize=8.5,leading=11,textColor=k(MUTED),alignment=TA_RIGHT))]
        hero=Table([[left,balance]],colWidths=[available*.58,available*.42],hAlign='LEFT')
        hero.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'BOTTOM'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),12),('LINEBELOW',(0,0),(-1,0),.8,k(GOLD))]))
        story.append(hero)
        sales=next((r for n_,r in tables if r[0]==PRODUCT_HEAD),None)
        sale_total=sales[-1] if sales and is_total(sales[-1]) else None
        discounts={text(r[3]) for r in (sales or [])[1:] if not is_total(r)}
        psf='PSF' in text(first.get('KDV'))
        stats=[('TOPLAM ÜRÜN',f"{meta['products']} adet" if meta['products'] is not None else '—',f"{meta['kinds']} çeşit ürün" if meta['kinds'] is not None else 'Satış kaydı yok'),
               ('KDV HARİÇ TUTAR',tl(sale_total[6]) if sale_total and isinstance(sale_total[6],Decimal) else '—','Ürün toplamı, KDV hariç'),
               ('FİYATLANDIRMA',('PSF' if psf else 'Belge fiyatı')+(f' · {next(iter(discounts))} iskonto' if len(discounts)==1 else ''),'KDV %20 dahil' if psf else text(first.get('KDV')) or '—')]
        strip=Table([[[Paragraph(a,P('sl',fontName='CariTRBold',fontSize=7,leading=9,textColor=k(MUTED))),Spacer(1,3),
                        Paragraph(esc(b),P('sv',fontName='CariTRBold',fontSize=12.5,leading=15,textColor=k(INK))),Spacer(1,1),
                        Paragraph(esc(c_),P('sn',fontSize=7.3,leading=9,textColor=k(MUTED)))] for a,b,c_ in stats]],colWidths=[available/len(stats)]*len(stats),hAlign='LEFT')
        strip.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(0,0),0),('LEFTPADDING',(1,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),
                                   ('LINEBEFORE',(1,0),(-1,0),.6,k(LINE)),('LINEBELOW',(0,0),(-1,0),.6,k(LINE))]))
        story+=[strip,Spacer(1,12)]
    else:
        story+=left+[Spacer(1,12)]
    # --- tablolar ---------------------------------------------------------------------
    for name,rows in tables:
        if len(rows)==1 or (rows[0] in (['Alan','Bilgi'],['Alan','Açıklama']) and name in ('Cari özeti','Rapor bilgisi')):
            continue  # özet yukarıda; tekrar basılmaz
        if name=='Ödeme bilgileri':
            info=dict((r[0],r[1]) for r in rows[1:])
            iban=text(info.get('IBAN'));number_,currency=split_iban(iban)
            bank=[Paragraph('ÖDEME BİLGİLERİ · BANKA HAVALESİ / EFT',eyebrow),Spacer(1,8)]
            for key_ in ('Banka','Hesap sahibi'):
                if info.get(key_):bank+=[Paragraph(key_,P('bk',fontSize=7.3,leading=9,textColor=k(MUTED))),Paragraph(esc(info[key_]),P('bvv',fontName='CariTRBold',fontSize=9.5,leading=12.5)),Spacer(1,6)]
            if iban:
                bank+=[Paragraph('IBAN'+(f' · {currency}' if currency else ''),P('ik',fontSize=7.3,leading=9,textColor=k(MUTED))),Spacer(1,2),
                       Paragraph(esc(number_),P('ib',fontName='CariMono',fontSize=15,leading=19,textColor=k(GREEN))),Spacer(1,2),
                       Paragraph('Boşluksuz: '+esc(re.sub(r'\s','',number_)),P('ibc',fontName='CariMono',fontSize=8,leading=10,textColor=k(MUTED)))]
            official=[Paragraph('RESMÎ ŞİRKET BİLGİLERİ',P('oh',fontName='CariTRBold',fontSize=7,leading=9,textColor=k(MUTED))),Spacer(1,6)]
            for key_ in ('Unvan','Vergi dairesi','VKN','MERSİS no','Adres','Telefon','E-posta'):
                if info.get(key_):official+=[Paragraph(f"<font color='#{MUTED}'>{esc(key_)}</font>  {esc(info[key_])}",P('ov',fontSize=7.6,leading=10.5)),Spacer(1,2.5)]
            card=Table([[bank,official]],colWidths=[available*.55,available*.45],hAlign='LEFT')
            card.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(0,0),1,k(GOLD)),('BACKGROUND',(0,0),(0,0),k(PAPER)),
                                      ('LEFTPADDING',(0,0),(0,0),16),('RIGHTPADDING',(0,0),(0,0),16),('TOPPADDING',(0,0),(-1,-1),14),('BOTTOMPADDING',(0,0),(-1,-1),14),('LEFTPADDING',(1,0),(1,0),22)]))
            story.append(KeepTogether([Spacer(1,16),card]));continue
        if rows[0] in (['Alan','Bilgi'],['Alan','Açıklama']):
            t=Table([[cell(a,P('kk',fontSize=8,textColor=k(MUTED))),cell(b,bold)] for a,b in ((r[0],r[1]) for r in rows[1:]) if text(b)],colWidths=[available*.24,available*.76],hAlign='LEFT')
            t.setStyle(TableStyle(pad+[('LINEBELOW',(0,0),(-1,-1),.5,k(LINE))]))
            story+=heading(name)+[t];continue
        commands=list(pad)
        if rows[0]==PRODUCT_HEAD:
            h0=['Ürün','Adet','PSF (KDV dahil)','İskonto','İskontolu birim fiyat','','Tutar','']
            h1=['','','','','KDV hariç','KDV dahil','KDV hariç','KDV dahil']
            data=[[Paragraph(v,head if i==0 else head_c) for i,v in enumerate(h0)],[Paragraph(v,head_c) for v in h1]]
            for r in rows[1:]:
                tot=is_total(r);st=bold if tot else body
                data.append([cell(r[0],st),cell(r[1],st),cell(r[2],st),Paragraph(esc(r[3]),P('d',fontName='CariTRBold' if tot else 'CariTR',alignment=TA_CENTER)),
                             cell(r[4],st),cell(r[5],st),cell(r[6],st),cell(r[7],strong_total if tot else strong)])
            widths=[available*w for w in (.2,.06,.125,.075,.13,.13,.135,.145)];header_rows=2
            commands+=[('SPAN',(0,0),(0,1)),('SPAN',(1,0),(1,1)),('SPAN',(2,0),(2,1)),('SPAN',(3,0),(3,1)),('SPAN',(4,0),(5,0)),('SPAN',(6,0),(7,0)),
                       ('LINEBELOW',(4,0),(5,0),.8,k(GOLD)),('LINEBELOW',(6,0),(7,0),.8,k(GOLD)),('LINEBEFORE',(4,0),(4,-1),.5,k(LINE)),('LINEBEFORE',(6,0),(6,-1),.5,k(LINE)),
                       ('TOPPADDING',(0,0),(-1,1),4),('BOTTOMPADDING',(0,0),(-1,1),4),('BACKGROUND',(7,2),(7,-1),k(PAPER))]
            source=rows
        else:
            source=[row[:6] for row in rows] if name.startswith('Teslim ve hediyeler') else rows
            if rows[0]==LEDGER_HEAD:
                # PDF'te tamamen boş sütun basılmaz (ör. hiç belge no girilmemişse); Excel'de kalır.
                empty=[j for j in range(len(rows[0])) if all(not text(r[j]) for r in rows[1:] if not is_total(r))]
                source=[[v for j,v in enumerate(r) if j not in empty] for r in rows]
            numeric_cols={j for row in source[1:] for j,v in enumerate(row) if isinstance(v,(int,Decimal)) and not isinstance(v,bool)}
            data=[[Paragraph(esc(v.replace(' TL','') if rows[0]==LEDGER_HEAD else v),head_r if j in numeric_cols else head) for j,v in enumerate(source[0])]]
            for r in source[1:]:
                tot=is_total(r)
                data.append([cell(v,(strong_total if (tot and j==len(r)-1) else bold) if tot else body) for j,v in enumerate(r)])
            columns=len(source[0]);header_rows=1
            ledger_w={'Tarih':.16,'Hareket':.22,'Belge':.17,'Borç TL':.15,'Alacak TL':.15,'Bakiye TL':.15}
            widths=[available*ledger_w[h]/sum(ledger_w[x] for x in source[0]) for h in source[0]] if rows[0]==LEDGER_HEAD else ([available*.26]+[available*.74/(columns-1)]*(columns-1) if columns>2 else [available*.3,available*.7])
        commands+=[('BACKGROUND',(0,0),(-1,header_rows-1),k(SAGE)),('LINEBELOW',(0,header_rows-1),(-1,header_rows-1),1,k(GREEN)),('LINEBELOW',(0,header_rows),(-1,-1),.4,k(LINE))]
        for i,r in enumerate(source[1:],header_rows):
            if is_total(r):commands+=[('LINEABOVE',(0,i),(-1,i),1.4,k(GOLD)),('LINEBELOW',(0,i),(-1,i),0,colors.white),('TOPPADDING',(0,i),(-1,i),9),('BOTTOMPADDING',(0,i),(-1,i),9)]
        t=Table(data,colWidths=widths,repeatRows=header_rows,hAlign='LEFT');t.setStyle(TableStyle(commands))
        if rows[0]==LEDGER_HEAD and story:story.append(PageBreak())  # 2. sayfa: ekstre + ödeme
        story+=heading(name)+[t]
    out=BytesIO();label=doc_title(title);stamp=meta['stamp'];seller=firm()
    width,height=page
    class Numbered(Canvas):
        """Sayfa x / y: toplam sayfa sayısı ancak belge bitince bilinir."""
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self._saved=[]
        def showPage(self):self._saved.append(dict(self.__dict__));self._startPage()
        def save(self):
            total=len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self.setFont('CariTR',7.3);self.setFillColor(k(MUTED))
                self.drawRightString(width-margin,20,f'Sayfa {self._pageNumber} / {total}')
                Canvas.showPage(self)
            Canvas.save(self)
    def decorate(canvas,doc):
        canvas.saveState()
        if LOGO.exists():canvas.drawImage(str(LOGO),margin,height-50,width=140,height=19.4,mask='auto',preserveAspectRatio=True)
        canvas.setFillColor(k(GOLD));canvas.setFont('CariTRBold',8);canvas.drawRightString(width-margin,height-37,label)
        canvas.setFillColor(k(MUTED));canvas.setFont('CariTR',7.3);canvas.drawRightString(width-margin,height-48,text(meta.get('title') or title)+' · '+stamp)
        canvas.setStrokeColor(k(LINE));canvas.setLineWidth(.6);canvas.line(margin,height-60,width-margin,height-60);canvas.line(margin,32,width-margin,32)
        canvas.setFillColor(k(MUTED));canvas.setFont('CariTR',7.3)
        canvas.drawString(margin,20,'L’CARLIÉ'+(' · '+seller['unvan'] if seller.get('unvan') else '')[:150])
        canvas.restoreState()
    SimpleDocTemplate(out,pagesize=page,leftMargin=margin,rightMargin=margin,topMargin=74,bottomMargin=44,title=label+' · '+text(meta.get('title') or title),author='L’CARLIÉ',subject='Cari hesap ekstresi').build(story,onFirstPage=decorate,onLaterPages=decorate,canvasmaker=Numbered)
    return out.getvalue()


def export(owner,query):
    fmt=(query.get('format') or [''])[0];scope=(query.get('scope') or ['account'])[0]
    if fmt not in ('pdf','xlsx') or scope not in ('account','reconciliation','portfolio'):raise cari.CariError('İndirme biçimi veya kapsamı geçersiz.')
    title,tables=sheets(owner,(query.get('account_id') or [''])[0],scope,(query.get('as_of') or [None])[0])
    if sum(len(rows) for _,rows in tables)>20000:raise cari.CariError('Bu rapor çok büyük; daha küçük bir kapsam seçin.')
    meta=report_meta(title,tables)  # tek kaynak: PDF ve Excel aynı hazırlanma zamanını basar
    data=pdf(title,tables,meta) if fmt=='pdf' else xlsx(tables,title,meta)
    return ('application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),data,'lcarlie-cari.'+fmt
