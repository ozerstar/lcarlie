-- 047: Idefix komisyon oranlari (OLCULDU, varsayilmadi)
--
-- KAYNAK: satici.idefix.com > Envanter > "Komisyon ve Vade" sutunu, 30 satirin
-- 30'u da sayfanin DOM'undan okundu (23.10.2026). Merchant API'de komisyon ucu
-- YOK: /pim/vendor/{v}/commission ve benzeri 6 yol 404, finance/order yollari
-- 503 dondu. Bu yuzden tek gecerli kaynak panel.
--
-- 🔴 ORAN SABIT DEGIL. 29 urun %10, BABYSHOWER (8684869609356) %15.
--    "Idefix %10 alir" diye genellemek bu satiri yanlis hesaplar.
--
-- Panelin yazdigi komisyon TUTARI, oran x (KDV dahil) fiyat hesabimizla
-- 30/30 tuttu; yani komisyon KDV DAHIL fiyat uzerinden aliniyor.
-- Vade: hepsinde 28 gun (bu tabloda alan yok, marj raporunda yazili).
--
-- Havuzdaki 6 not_matched urun bu listede YOK: satis sayfalari olusmadigi icin
-- panelde komisyon satirlari da yok. Olculmeyen deger yazilmaz.

begin;

create temp table _idefix_kom (barkod text, yuzde numeric) on commit drop;

insert into _idefix_kom (barkod, yuzde) values
  ('8684869609097', 10), ('8684869609110', 10), ('8684869609134', 10),
  ('8684869609141', 10), ('8684869609158', 10), ('8684869609165', 10),
  ('8684869609196', 10), ('8684869609073', 10), ('8684869609301', 10),
  ('8684869609516', 10), ('8684869609561', 10), ('8684869609547', 10),
  ('8684869609554', 10), ('8684869609066', 10), ('8684869609202', 10),
  ('8684869609271', 10), ('8684869609103', 10), ('8684869609288', 10),
  ('8684869609295', 10), ('8684869609127', 10), ('8684869609394', 10),
  ('8684869609363', 10), ('8684869609318', 10), ('8684869609530', 10),
  ('8684869609523', 10), ('8684869609356', 15), ('8684869609325', 10),
  ('8684869609370', 10), ('8684869609387', 10), ('8684869609233', 10);

insert into core.urun_platform_komisyon
       (urun_id, platform_kod, komisyon_yuzde, gerekce, kaydeden)
select w.urun_id, 'idefix', k.yuzde,
       'satici paneli Envanter > Komisyon ve Vade sutunu, 23.10.2026; vade 28 gun',
       'panel:idefix'
  from _idefix_kom k
  join raw.wix_urun w on w.sku = k.barkod
on conflict (urun_id, platform_kod) do update
   set komisyon_yuzde = excluded.komisyon_yuzde,
       gerekce        = excluded.gerekce,
       kaydeden       = excluded.kaydeden,
       guncelleme     = now();

-- Eslesmeyen barkod kaldiysa goster (sessizce dusmesin)
do $$
declare eksik int;
begin
  select count(*) into eksik
    from _idefix_kom k
    where not exists (select 1 from raw.wix_urun w where w.sku = k.barkod);
  if eksik > 0 then
    raise notice 'UYARI: % barkod raw.wix_urun ile eslesmedi', eksik;
  end if;
end $$;

commit;
