(function(){
  const $=id=>document.getElementById(id);
  const facts=[...document.querySelectorAll('#main ol.facts > li.fact')].map(li=>({
    label:li.querySelector('.cat').textContent, title:li.querySelector('h2').textContent, body:li.querySelector('p').textContent,
    url:(li.querySelector('a.more')||{getAttribute:()=>null}).getAttribute('href')}));
  const vis=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(el).visibility!=="hidden";};
  const small=[...document.querySelectorAll('button,select,a')].filter(vis).map(el=>{const r=el.getBoundingClientRect();
    return {t:(el.id||el.className||el.textContent).toString().slice(0,30),w:Math.round(r.width),h:Math.round(r.height)};})
    .filter(x=>x.h<44||x.w<44);
  const first=document.querySelector('#main li.fact h2');
  return {hash:location.hash, facts, recent:[...document.querySelectorAll('.recent a')].map(a=>a.getAttribute('href')),
    options:[...$('archiveSel').options].map(o=>o.value), archiveHidden:$('archiveWrap').hidden,
    prevDisabled:$('prevBtn').disabled, nextDisabled:$('nextBtn').disabled, barDate:$('barDate').textContent,
    selectFont:parseFloat(getComputedStyle($('archiveSel')).fontSize), small,
    scrollW:document.documentElement.scrollWidth, clientW:document.documentElement.clientWidth,
    firstTitleBottom:first?first.getBoundingClientRect().bottom:null, innerH:innerHeight,
    barVisible:vis($('bar')), status:$('statusText').textContent, ndShort:$('ndShort').textContent,
    ndRows:document.querySelectorAll('#ndList dt').length,
    words:[...document.querySelectorAll('#wordList details.wd')].map(d=>[d.dataset.lang,d.querySelector('.w-word').textContent,
      (d.querySelector('a')||{getAttribute:()=>null}).getAttribute('href')])};
})()
