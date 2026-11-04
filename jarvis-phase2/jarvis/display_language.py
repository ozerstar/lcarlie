"""Turkish presentation policy; identifiers and stored records remain intact."""
from __future__ import annotations
import json
import re
from pathlib import Path
NAMES = json.loads(Path(__file__).with_name('display_catalog.json').read_text(encoding='utf-8'))
POLICY = """Kullanıcıya verdiğin bütün açıklamalar yalnızca anlaşılır Türkçe olmalıdır.
İşlem başarılı da olsa başarısız da olsa ne olduğunu ve sonraki adımı Türkçe açıkla.
İç sistem kodu, alt çizgili alan adı, ham hata, yığın izi veya parantez içinde teknik kimlik gösterme.
Birim, görev ve kaynakların açıklayıcı Türkçe adlarını kullan. Özel ad, marka, adres ve ölçülmüş değerleri değiştirme.
İngilizce kaynakları Türkçe özetle. Kaynağın okunmasını işin tamamlanması gibi anlatma.
Yanıt veremiyorsan uydurma; neyin eksik olduğunu ve neyin yapılabileceğini açıkla."""
_ENGLISH = re.compile(r'\b(the|your|please|unable|failed|cannot|could|request|response|provider|unexpected|invalid|error|is|are|this|with|from|has|have|not|found|retry|timeout)\b', re.I)
def foreign(value: str) -> bool:
    words = re.findall(r'[a-zA-ZçğıöşüİÇĞÖŞÜ]+', value)
    return len(_ENGLISH.findall(value)) >= max(3, len(words)*.17)
def display(value: str) -> str:
    text = str(value or '')
    if text.strip() in NAMES:
        return NAMES[text.strip()]
    text = re.sub(r'\b(?:core|mart|raw|public)\.([a-z][a-z0-9_]*)\b', lambda m:NAMES.get(m[1], 'Şirket veri kaynağı'), text)
    text = re.sub(r'office:team-cycle:[^\s,;]+', 'Son ekip faaliyet kaydı', text)
    text = re.sub(r'\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b', lambda m:NAMES.get(m[0], 'Açıklaması henüz tanımlanmamış kayıt'), text)
    text = re.sub(r'\b[A-Z][A-Z0-9_]{1,}\b',lambda m:NAMES.get(m[0],m[0]),text)
    return re.sub(r'\(([^()]*)\)',lambda m:'— '+m[1].strip()+' —',text)
def error_message(value: str, status: int = 500) -> str:
    text=str(value or '')
    if status==401 or re.search(r'authentication|unauthorized',text,re.I):return 'Oturumunuz sona erdi. Yeniden giriş yapın.'
    if status==403:return 'Bu işlem için yetki veya oturum doğrulanamadı. Sayfayı yenileyip yeniden deneyin.'
    if status==404:return 'İstenen kayıt bulunamadı. Seçiminizi kontrol edip yeniden deneyin.'
    if re.search(r'timeout|timed out|zaman aş|süre.*dol',text,re.I):return 'Yanıt bekleme süresi doldu. İşlem tamamlanamadı; yeniden deneyebilirsiniz.'
    if re.search(r'model|provider|quota|429|overload',text,re.I):return 'Yanıt hizmeti şu anda kullanılamıyor. Biraz sonra yeniden deneyebilirsiniz.'
    if not foreign(text) and re.search('[çğıöşüİ]',text) and not re.search(r'traceback|exception|error|\bHTTP\b|[a-z]+_[a-z]+',text,re.I):return display(text)
    return 'İşlem tamamlanamadı. Bağlantıyı kontrol edip yeniden deneyin. Sorun sürerse sistem durumunu inceleyin.'
def public_errors(payload, status=200):
    if isinstance(payload,list):return [public_errors(x,status) for x in payload]
    if not isinstance(payload,dict):return payload
    return {key: error_message(value,status) if key in ('error','hata') and isinstance(value,str) and value else public_errors(value,status) for key,value in payload.items()}
