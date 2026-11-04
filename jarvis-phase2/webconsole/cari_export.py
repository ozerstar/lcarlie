"""Authenticated, owner-scoped PDF and genuine XLSX reports; no mutations."""
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as xml_escape
import html,re,zipfile,threading
import cari,cari_invoice,cari_reconciliation

LABELS={'sale':'Satış','purchase':'Alış','sale_return':'Müşteriden iade','purchase_return':'Tedarikçiye iade','collection':'Tahsilat','payment':'Ödeme','opening_receivable':'Açılış alacağı','opening_payable':'Açılış borcu','gift_out':'Bedelsiz verildi','gift_in':'Bedelsiz alındı'}
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
    tables=[('Cari özeti',[['Alan','Bilgi'],['Cari',a['name']],['Hazırlanma',stamp],['İletişim',a.get('contact','')],['Bakiye TL',amount(summary['balance_cents'])],['Durum',summary['status']],['KDV','Belirlenmemiş KDV var' if summary['unknown_tax_documents'] else 'Girilen kayıtlara göre'],['Kapsam','Bakiye kesinleşmiş hareketlere aittir. Mutabakat satışları, bildirilen ödemeler ve iade ön hesabı bakiyeye dahil değildir.']])]
    if scope=='account':
        rows=[['Tarih','Hareket','Belge','Açıklama','Alacak artışı TL','Alacak azalışı TL','Bakiye TL']];balance=0
        for e in statement['entries']:
            p=e['payload'];signed=p['signed_cents']*(-1 if e['reverses'] else 1);balance+=signed
            rows.append([p['date'],('Ters kayıt · ' if e['reverses'] else '')+LABELS.get(p['kind'],'Hareket'),p.get('reference',''),p.get('note',''),amount(max(0,signed)),amount(max(0,-signed)),amount(balance)])
        tables.append(('Hesap ekstresi',rows))
        for key,label in [('sale','Kesinleşmiş satışlar'),('purchase','Kesinleşmiş alışlar'),('gift','Bedelsiz hareketler')]:
            rows=[['Ürün','Net adet','İndirimli birim TL','Satır tutarı TL']]
            for p in statement['product_tables'].get(key,{}).get('rows',[]):rows.append([p['name'],p['quantity'],amount(p['discounted_unit_price_cents']),amount(p['net_cents'])])
            tables.append((label,rows))
    docs=cari_invoice.list_documents(owner,a['id'])['documents']
    active=[d['extracted']['cari_reconciliation'] for d in docs if d['source']=='attachment' and isinstance(d.get('extracted'),dict) and d['extracted'].get('cari_reconciliation',{}).get('status')=='pending']
    if active:tables[0][1][5]=['Durum','Mutabakat bekliyor; bakiye yalnız kesinleşmiş hareketlere aittir.']
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

def xlsx(tables):
    # Inline string cells keep names beginning with =, +, - or @ inert.
    out=BytesIO();ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    col=lambda i:chr(65+i) if i<26 else chr(64+i//26)+chr(65+i%26)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(tables)+1))
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+overrides+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{xml_escape(name[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(tables,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(tables)+1))+f'<Relationship Id="rId{len(tables)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF24584C"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for number,(name,rows) in enumerate(tables,1):  # noqa: B007
            width=len(rows[0]);data=[]
            for ri,row in enumerate(rows,1):
                cells=[]
                for ci,value in enumerate(row):
                    ref=f'{col(ci)}{ri}'
                    if isinstance(value,(int,Decimal)):
                        cells.append(f'<c r="{ref}" s="{2 if isinstance(value,Decimal) else 0}"><v>{value}</v></c>')
                    else:cells.append(f'<c r="{ref}" s="{1 if ri==1 else 0}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(text(value))}</t></is></c>')
                data.append(f'<row r="{ri}"'+(' ht="32" customHeight="1"' if ri==1 else '')+'>'+''.join(cells)+'</row>')
            columns=''.join(f'<col min="{i+1}" max="{i+1}" width="{min(65,max(18,max(len(text(row[i])) if i<len(row) else 0 for row in rows[:100])+2))}" customWidth="1"/>' for i in range(width))
            z.writestr(f'xl/worksheets/sheet{number}.xml',f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{columns}</cols><sheetData>'+''.join(data)+f'</sheetData><autoFilter ref="A1:{col(width-1)}{len(rows)}"/></worksheet>')
    return out.getvalue()

_font_lock=threading.Lock()
def pdf(title,tables):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    with _font_lock:
        if 'CariTR' not in pdfmetrics.getRegisteredFontNames():
            normal='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
            if not Path(normal).exists():normal='C:/Windows/Fonts/arial.ttf';bold='C:/Windows/Fonts/arialbd.ttf'
            pdfmetrics.registerFont(TTFont('CariTR',normal));pdfmetrics.registerFont(TTFont('CariTRBold',bold))
    style=ParagraphStyle('body',fontName='CariTR',fontSize=8,leading=11)
    header=ParagraphStyle('header',parent=style,fontName='CariTRBold',textColor=colors.white)
    heading=ParagraphStyle('heading',fontName='CariTRBold',fontSize=16,leading=22,textColor=colors.HexColor('#24584c'))
    def cell(v,st=style):
        value=f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.') if isinstance(v,Decimal) else text(v)
        return Paragraph(html.escape(value),st)
    story=[];page=landscape(A4);available=page[0]-64
    for index,(name,rows) in enumerate(tables):  # noqa: B007
        if len(rows)==1:continue
        if story:story.append(PageBreak())
        story.extend([cell('L’carlie · '+title,heading),Spacer(1,8),cell(name,heading),Spacer(1,12)])
        # Split the wide delivery sheet into quantities; prices have their own sheet.
        pdfrows=[row[:6] for row in rows] if name.startswith('Teslim ve hediyeler') else rows
        columns=len(pdfrows[0]);widths=[available*.28]+[available*.72/(columns-1)]*(columns-1) if columns>2 else [available*.28,available*.72]
        data=[[cell(v,header if i==0 else style) for v in row] for i,row in enumerate(pdfrows)]
        table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#24584c')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f3f7f5'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(table)
    out=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('CariTR',8);canvas.drawString(32,18,'L’carlie · Mutabakat ön hesapları kesin mali kayıt değildir.');canvas.drawRightString(page[0]-32,18,str(doc.page))
    SimpleDocTemplate(out,pagesize=page,leftMargin=32,rightMargin=32,topMargin=28,bottomMargin=36,title=title,author='L’carlie').build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()

def export(owner,query):
    fmt=(query.get('format') or [''])[0];scope=(query.get('scope') or ['account'])[0]
    if fmt not in ('pdf','xlsx') or scope not in ('account','reconciliation','portfolio'):raise cari.CariError('İndirme biçimi veya kapsamı geçersiz.')
    title,tables=sheets(owner,(query.get('account_id') or [''])[0],scope,(query.get('as_of') or [None])[0])
    if sum(len(rows) for _,rows in tables)>20000:raise cari.CariError('Bu rapor çok büyük; daha küçük bir kapsam seçin.')
    data=pdf(title,tables) if fmt=='pdf' else xlsx(tables)
    return ('application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),data,'cari-raporu.'+fmt
