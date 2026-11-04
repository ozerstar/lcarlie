import threading
import unittest
from unittest.mock import patch
from jarvis.display_language import display, error_message, public_errors, foreign
from jarvis.office_questions import fallback_answer, synthesize_bounded
from jarvis.model_layer import ModelRouter, ModelUnavailable

class TurkishOutputTests(unittest.TestCase):
    def test_labels_are_descriptive(self):
        self.assertEqual(display('GOOGLE_ADS'), 'Google arama reklamları')
        self.assertEqual(display('ecommerce_profitability'), 'Ürün kârlılığı')
        self.assertEqual(display('core.arac_envanteri'), 'Araç envanteri')
        self.assertNotIn('_', display('missing_unknown_key'))
        self.assertNotIn('(',display('Kaynak (DATA_BI)'))
    def test_errors_do_not_expose_provider_or_trace(self):
        for raw in ['no model provider could answer','Internal server error','Unexpected token < in JSON','Traceback TypeError secret','Failed to fetch']:
            text=error_message(raw)
            self.assertNotIn(raw,text)
            self.assertFalse(foreign(text))
        self.assertIn('Oturum',error_message('authentication required',401))
        self.assertIn('bulunamadı',error_message('not found',404))
    def test_machine_fields_are_preserved(self):
        raw={'status':'FAILED','department':'GOOGLE_ADS','source':'ecommerce_profitability','nested':{'error':'internal error'}}
        clean=public_errors(raw,500)
        self.assertEqual(clean['status'],'FAILED')
        self.assertEqual(clean['department'],'GOOGLE_ADS')
        self.assertEqual(clean['source'],'ecommerce_profitability')
        self.assertNotEqual(clean['nested']['error'],'internal error')
        self.assertEqual(raw['nested']['error'],'internal error')
    def test_fallback_is_not_fabricated_answer(self):
        result=fallback_answer('PRODUCT','PRODUCT',[{'ref':'ecommerce_profitability'}],['sales_orders'])
        self.assertFalse(result['model_kullanildi'])
        self.assertEqual(result['kanit_sayisi'],1)
        self.assertIn('değerlendirme tamamlanamadı',result['cevap'])
        self.assertIn('1 kaynak okunamadı',result['cevap'])
    def test_timeout_releases_when_work_finishes(self):
        gate=threading.Event()
        try:
            with self.assertRaises(TimeoutError):synthesize_bounded(lambda:gate.wait(1),timeout=.01)
        finally:gate.set()
        self.assertEqual(synthesize_bounded(lambda:'tamam',timeout=1),'tamam')
    def test_stream_language_gate_and_policy(self):
        router=ModelRouter.__new__(ModelRouter)
        with patch.object(router,'_stream_text_raw',return_value=iter(['The provider cannot answer your request.'])) as stream:
            with self.assertRaises(ModelUnavailable):list(router.stream_text('Merhaba','Yardım et'))
            self.assertIn('yalnızca anlaşılır Türkçe',stream.call_args.args[1])
        with patch.object(router,'_stream_text_raw',return_value=iter(['Ürün ', 'kayıtları incelendi.'])):
            self.assertEqual(list(router.stream_text('Merhaba','Yardım et')),['Ürün kayıtları incelendi.'])
    def test_brand_names_are_not_foreign_sentences(self):
        self.assertFalse(foreign('Google Ads ve Instagram reklamları için veri bulunamadı.'))
        self.assertFalse(foreign('L’CARLIÉ ürününde maliyet bilgisi eksik.'))

if __name__=='__main__':unittest.main()
