import {familyName} from './labels.js';
export const DEFAULT_VIEW='all';
const brands={tecdynasty:['TEKNOLOJI','WEB','AI_OPS','SECURITY'],goril:['TASARIM','YAYIN','ART','CONTENT','COPY','CREATIVE_STRAT','UGC']};
export function departmentsForView(departments,key=DEFAULT_VIEW){
 if(key==='center')return departments.filter(d=>['EXEC','TASARIM','PRODUCT','HR'].includes(d.kod));
 if(key.startsWith('brand:'))return departments.filter(d=>(brands[key.slice(6)]||[]).includes(d.kod));
 if(key.startsWith('family:'))return departments.filter(d=>d.aile===key.slice(7));
 return departments;
}
export function viewTitle(key){return key==='all'?'Bütün birimler':key==='center'?'Merkez kat':key==='brand:tecdynasty'?'TECDYNASTY · Teknoloji ve yazılım':key==='brand:goril'?'Goril Ajans':key==='showcase'?'Mağaza ve sergi alanları':familyName(key.slice(7));}
