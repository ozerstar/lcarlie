(function(){'use strict';
if(window.__lcCartMeasurement)return;
var diag=window.__lcCartMeasurement={sent:0,deduplicated:0,lastPath:null};
var previous=null,sent=false,cursor=Math.max(0,(window.dataLayer||[]).length-25);
function consent(){try{return JSON.parse(localStorage.getItem('lcarLie_cookie_consent_v4')||'{}').analytics===true;}catch(e){return false;}}
function cartPath(path){return /^\/(cart|cart-page|sepet)(\/|$)/i.test(path);}
function check(){
 var path=location.pathname,dl=window.dataLayer||[];
 if(path!==previous){if(previous!==null)cursor=dl.length;previous=path;sent=false;diag.lastPath=path;}
 if(!cartPath(path)||sent||!consent()||typeof window.gtag!=='function')return;
 for(var i=cursor;i<dl.length;i++){var e=dl[i];
  if(e&&((e[0]==='event'&&e[1]==='view_cart')||e.event==='view_cart')){sent=true;diag.deduplicated++;return;}
 }
 window.gtag('event','view_cart',{send_to:'G-KCPFLRG2RV',page_path:path,event_source:'jarvis-cart-v1'});
 sent=true;diag.sent++;cursor=dl.length;
}
window.addEventListener('popstate',check);
window.addEventListener('storage',check);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',check,{once:true});else check();
setInterval(check,1000);
})();