"""Authenticated, owner-scoped PDF and genuine XLSX reports; no mutations."""
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as xml_escape
import html,re,zipfile,threading
from pathlib import Path
import cari,cari_invoice,cari_reconciliation

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
    tables=[('Cari özeti',[['Alan','Bilgi'],['Cari',a['name']],['Vergi dairesi / no',' · '.join(x for x in (a.get('tax_office'),a.get('tax_id')) if x)],['Adres',a.get('address','')],['İletişim',' · '.join(x for x in (a.get('contact'),a.get('email'),a.get('phone')) if x)],['Hazırlanma',stamp],['Bakiye TL',amount(summary['balance_cents'])],['Durum',summary['status']],['KDV','Fiyatlar PSF üzerinden, KDV %20 dahil' if summary['unknown_tax_documents'] else 'Belgelerdeki KDV oranlarına göre'],['Kapsam','Bakiye kesinleşmiş cari hareketlerine göre hazırlanmıştır.']])]
    if scope=='account':
        for key,label in [('sale','Satılan ürünler'),('purchase','Alınan ürünler'),('gift','Bedelsiz ürünler')]:
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

# L'CARLIÉ kurumsal renkleri (lcarlie-theme.css ile aynı).
GREEN,INK,PAPER,SAGE,GOLD,LINE,MUTED='365F49','263C33','F7F5EF','E5EDDF','82673D','DEDFD3','65746B'
LOGO=Path(__file__).resolve().parent/'static'/'img'/'lcarlie-mark-dark.png'
TOTALS=('GENEL TOPLAM','GÜNCEL BAKİYE','Toplam')
def is_total(row):return isinstance(row[0],str) and row[0] in TOTALS
def doc_title(title):return 'CARİ HESAP LİSTESİ' if title=='Cari hesaplar' else 'CARİ HESAP EKSTRESİ'
def now():return datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')

def xlsx(tables,title=''):
    # Inline string cells keep names beginning with =, +, - or @ inert.
    out=BytesIO();ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    col=lambda i:chr(65+i) if i<26 else chr(64+i//26)+chr(65+i%26)
    tables=[t for t in tables if len(t[1])>1] or tables[:1]
    logo=LOGO.read_bytes() if LOGO.exists() else None
    head=5  # 1 logo · 2 başlık · 3 alt başlık · 4 altın şerit · 5 sütun başlıkları
    stamp=now()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        n=len(tables)
        overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,n+1))
        if logo:overrides+=''.join(f'<Override PartName="/xl/drawings/drawing{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' for i in range(1,n+1))
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+overrides+'</Types>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{xml_escape(name[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(tables,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,n+1))+f'<Relationship Id="rId{n+1}" Type="{rel}/styles" Target="styles.xml"/></Relationships>')
        fonts=(f'<font><sz val="11"/><color rgb="FF{INK}"/><name val="Calibri"/></font>'
               f'<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
               f'<font><b/><sz val="18"/><color rgb="FF{GREEN}"/><name val="Calibri"/></font>'
               f'<font><i/><sz val="10"/><color rgb="FF{MUTED}"/><name val="Calibri"/></font>'
               f'<font><b/><sz val="11"/><color rgb="FF{INK}"/><name val="Calibri"/></font>')
        fill=lambda c:f'<fill><patternFill patternType="solid"><fgColor rgb="FF{c}"/><bgColor indexed="64"/></patternFill></fill>'
        fills='<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'+fill(GREEN)+fill(PAPER)+fill(SAGE)+fill(GOLD)
        borders=(f'<border/><border><left/><right/><top/><bottom style="thin"><color rgb="FF{LINE}"/></bottom><diagonal/></border>'
                 f'<border><left/><right/><top style="medium"><color rgb="FF{GOLD}"/></top><bottom style="thin"><color rgb="FF{LINE}"/></bottom><diagonal/></border>')
        xf=lambda font,fill_,border,num=0,extra='':f'<xf numFmtId="{num}" fontId="{font}" fillId="{fill_}" borderId="{border}" xfId="0" applyFont="1" applyFill="1" applyBorder="1"'+(' applyNumberFormat="1"' if num else '')+' applyAlignment="1"><alignment vertical="center"'+extra+'/></xf>'
        # 0 varsayılan · 1 başlık · 2/3 beyaz satır · 4/5 krem satır · 6 belge başlığı · 7 alt başlık · 8/9 toplam · 10 altın şerit
        xfs=[xf(0,0,0),xf(1,2,1,0,' wrapText="1"'),xf(0,0,1),xf(0,0,1,4),xf(0,3,1),xf(0,3,1,4),xf(2,0,0),xf(3,0,0),xf(4,4,2),xf(4,4,2,4),xf(0,5,0)]
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}"><fonts count="5">{fonts}</fonts><fills count="6">{fills}</fills><borders count="3">{borders}</borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        if logo:z.writestr('xl/media/logo.png',logo)
        cx,cy=260*9525,36*9525
        def inline(ref,value,style):return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(text(value))}</t></is></c>'
        for number,(name,rows) in enumerate(tables,1):
            width=len(rows[0]);data=[]
            data.append('<row r="1" ht="40" customHeight="1"/>')
            data.append(f'<row r="2" ht="26" customHeight="1">{inline("A2",title or "L’CARLIÉ",6)}</row>')
            data.append(f'<row r="3">{inline("A3",name+" · "+stamp,7)}</row>')
            data.append('<row r="4" ht="5" customHeight="1">'+''.join(f'<c r="{col(i)}4" s="10"/>' for i in range(width))+'</row>')
            for offset,row in enumerate(rows):
                ri=head+offset;cells=[];total=offset and is_total(row);cream=offset%2==0
                for ci,value in enumerate(row):
                    ref=f'{col(ci)}{ri}'
                    if offset==0:cells.append(inline(ref,value,1));continue
                    numeric=isinstance(value,(int,Decimal)) and not isinstance(value,bool)
                    style=(9 if numeric else 8) if total else ((5 if cream else 3) if isinstance(value,Decimal) else (4 if cream else 2))
                    cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>' if numeric else inline(ref,value,style))
                data.append(f'<row r="{ri}"'+(' ht="30" customHeight="1"' if offset==0 else ' ht="20" customHeight="1"')+'>'+''.join(cells)+'</row>')
            columns=''.join(f'<col min="{i+1}" max="{i+1}" width="{min(60,max(14,max(len(text(row[i])) if i<len(row) else 0 for row in rows[:100])+3))}" customWidth="1"/>' for i in range(width))
            drawing='<drawing r:id="rId1"/>' if logo else ''
            z.writestr(f'xl/worksheets/sheet{number}.xml',f'<worksheet xmlns="{ns}" xmlns:r="{rel}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="{head}" topLeftCell="A{head+1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{columns}</cols><sheetData>'+''.join(data)+f'</sheetData><autoFilter ref="A{head}:{col(width-1)}{head+len(rows)-1}"/><pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>{drawing}</worksheet>')
            if logo:
                z.writestr(f'xl/worksheets/_rels/sheet{number}.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/drawing" Target="../drawings/drawing{number}.xml"/></Relationships>')
                z.writestr(f'xl/drawings/_rels/drawing{number}.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/image" Target="../media/logo.png"/></Relationships>')
                z.writestr(f'xl/drawings/drawing{number}.xml',f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{rel}"><xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>76200</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>76200</xdr:rowOff></xdr:from><xdr:ext cx="{cx}" cy="{cy}"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="2" name="Logo"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>')
    return out.getvalue()

_font_lock=threading.Lock()
def pdf(title,tables):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _font_lock:
        if 'CariTR' not in pdfmetrics.getRegisteredFontNames():
            normal='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
            if not Path(normal).exists():normal='C:/Windows/Fonts/arial.ttf';bold='C:/Windows/Fonts/arialbd.ttf'
            pdfmetrics.registerFont(TTFont('CariTR',normal));pdfmetrics.registerFont(TTFont('CariTRBold',bold))
    c=lambda h:colors.HexColor('#'+h)
    style=ParagraphStyle('body',fontName='CariTR',fontSize=8.5,leading=11.5,textColor=c(INK))
    right=ParagraphStyle('num',parent=style,alignment=TA_RIGHT)
    header=ParagraphStyle('header',parent=style,fontName='CariTRBold',textColor=colors.white)
    header_right=ParagraphStyle('headernum',parent=header,alignment=TA_RIGHT)
    bold=ParagraphStyle('bold',parent=style,fontName='CariTRBold')
    bold_right=ParagraphStyle('boldnum',parent=bold,alignment=TA_RIGHT)
    name_style=ParagraphStyle('name',fontName='CariTRBold',fontSize=20,leading=26,textColor=c(GREEN))
    section=ParagraphStyle('section',fontName='CariTRBold',fontSize=12,leading=16,textColor=c(GREEN),spaceBefore=16,spaceAfter=6,keepWithNext=1)
    def cell_text(v):return f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.') if isinstance(v,Decimal) else text(v)
    def cell(v,st=style):
        numeric=isinstance(v,(int,Decimal)) and not isinstance(v,bool)
        value=cell_text(v)
        if numeric and st is style:st=right
        if numeric and st is bold:st=bold_right
        return Paragraph(html.escape(value),st)
    page=landscape(A4);available=page[0]-72
    story=[Paragraph(html.escape(text(title)),name_style),Spacer(1,6)]
    for name,rows in tables:
        if len(rows)==1:continue
        if rows[0]==['Alan','Bilgi']:
            data=[[cell(k,bold),cell(cell_text(v)+' TL' if isinstance(v,Decimal) else v)] for k,v in rows[1:] if text(v)]
            table=Table(data,colWidths=[available*.22,available*.5],hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),c(SAGE)),('LINEBELOW',(0,0),(-1,-1),.5,c(LINE)),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),8)]))
            story.extend([Paragraph(html.escape(name),section),table]);continue
        # Split the wide delivery sheet into quantities; prices have their own sheet.
        pdfrows=[row[:6] for row in rows] if name.startswith('Teslim ve hediyeler') else rows
        columns=len(pdfrows[0]);widths=[available*.26]+[available*.74/(columns-1)]*(columns-1) if columns>2 else [available*.3,available*.7]
        if name=='Hesap ekstresi':widths=[available*w for w in (.16,.18,.18,.16,.16,.16)]
        numeric_cols={j for row in pdfrows[1:] for j,v in enumerate(row) if isinstance(v,(int,Decimal)) and not isinstance(v,bool)}
        data=[[cell(v,(header_right if j in numeric_cols else header) if i==0 else bold if is_total(row) else style) for j,v in enumerate(row)] for i,row in enumerate(pdfrows)]
        table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        commands=[('BACKGROUND',(0,0),(-1,0),c(GREEN)),('ROWBACKGROUNDS',(0,1),(-1,-1),[c(PAPER),colors.white]),('LINEBELOW',(0,1),(-1,-1),.4,c(LINE)),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]
        for i,row in enumerate(pdfrows):
            if i and is_total(row):commands+=[('BACKGROUND',(0,i),(-1,i),c(SAGE)),('LINEABOVE',(0,i),(-1,i),1.2,c(GOLD))]
        table.setStyle(TableStyle(commands))
        story.extend([Paragraph(html.escape(name),section),table])
    out=BytesIO();stamp=now();label=doc_title(title);seller=firm()
    def decorate(canvas,doc):
        width,height=page;canvas.saveState()
        if LOGO.exists():canvas.drawImage(str(LOGO),36,height-58,width=166,height=23,mask='auto',preserveAspectRatio=True)
        canvas.setFillColor(c(GOLD));canvas.setFont('CariTRBold',11);canvas.drawRightString(width-36,height-44,label)
        canvas.setFillColor(c(MUTED));canvas.setFont('CariTR',8);canvas.drawRightString(width-36,height-57,stamp)
        if seller.get('unvan'):canvas.setFillColor(c(MUTED));canvas.setFont('CariTR',7.5);canvas.drawString(36,height-71,seller['unvan'][:120])
        canvas.setStrokeColor(c(GOLD));canvas.setLineWidth(1.4);canvas.line(36,height-79,width-36,height-79)
        canvas.setFillColor(c(GREEN));canvas.rect(0,0,width,24,stroke=0,fill=1)
        canvas.setFillColor(colors.white);canvas.setFont('CariTR',7.5)
        canvas.drawString(36,9,' · '.join(x for x in ('L’CARLIÉ',seller.get('iban') and 'IBAN '+seller['iban'],'Bu belge cari hesap kayıtlarına göre hazırlanmıştır.') if x))
        canvas.drawRightString(width-36,9,'Sayfa '+str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(out,pagesize=page,leftMargin=36,rightMargin=36,topMargin=92,bottomMargin=40,title=label+' · '+text(title),author='L’CARLIÉ').build(story,onFirstPage=decorate,onLaterPages=decorate)
    return out.getvalue()

def export(owner,query):
    fmt=(query.get('format') or [''])[0];scope=(query.get('scope') or ['account'])[0]
    if fmt not in ('pdf','xlsx') or scope not in ('account','reconciliation','portfolio'):raise cari.CariError('İndirme biçimi veya kapsamı geçersiz.')
    title,tables=sheets(owner,(query.get('account_id') or [''])[0],scope,(query.get('as_of') or [None])[0])
    if sum(len(rows) for _,rows in tables)>20000:raise cari.CariError('Bu rapor çok büyük; daha küçük bir kapsam seçin.')
    data=pdf(title,tables) if fmt=='pdf' else xlsx(tables,title)
    return ('application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),data,'lcarlie-cari.'+fmt
