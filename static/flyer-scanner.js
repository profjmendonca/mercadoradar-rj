/* MercadoRadar RJ — leitor de encartes com revisão humana.
   Usa Tesseract.js no navegador; nada é enviado ao banco sem revisão explícita.
   A identificação de nomes, preços e marcas a partir de encartes é apenas sugestiva. */
(()=>{
"use strict";
const $=id=>document.getElementById(id);
const encode=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bands=["Guanabara","Assaí","Prezunic","Mundial","Rede Economia","Supermarket"];
const brandNames=["Coparroz","Nutricaldo","Elegê","Hellmann's","Skala","Andorinha","Camil","Tio João","Gallo","Liza","Seara","Glória","Italac","Colgate","Sorriso","Piracanjuba","Prezunic","Nestlé","Danone","Quatá","Omo","Ypê","Aurora","Sadia","Perdigão"];
const market=document.createElement("select");
market.id="ocr-market";
bands.forEach(m=>{const o=document.createElement("option");o.textContent=m;o.value=m;market.appendChild(o)});
market.value="Rede Economia";
let sourceUrl="",records=[],file=null,working=false;
const ocrPanel=document.createElement("section");
ocrPanel.className="box";
ocrPanel.innerHTML='<h2>Leitor de encartes em imagens</h2>'
+'<p class="muted">Encontre páginas oficiais da Rede Economia ou selecione uma imagem JPG, PNG ou WebP do encarte. O reconhecimento é experimental: confira cada item antes de importar um preço.</p>'
+'<div class="controls"><button type="button" id="ocr-find">Localizar imagens do encarte</button>'
+'<label for="ocr-file" style="margin:0">Ou escolher arquivo:</label><input id="ocr-file" type="file" accept="image/png,image/jpeg,image/webp" style="max-width:230px"></div>'
+'<div id="ocr-images" class="marketgrid" style="margin-top:10px"></div>'
+'<div class="controls"><label for="ocr-market" style="margin:0">Supermercado</label><span id="ocr-market-slot"></span>'
+'<button type="button" id="ocr-scan">Ler imagem selecionada</button></div>'
+'<div id="ocr-info" class="muted">Nenhuma imagem selecionada.</div>'
+'<div id="ocr-review" style="display:none">'
+'<div class="warn">Leitura automática pode confundir preços, produtos e marcas. “Marca não identificada na imagem” significa que o texto não foi reconhecido, não que o produto não tenha marca. Apenas itens conferidos por você podem ser enviados.</div>'
+'<div class="controls"><label>Validade da oferta: <input id="ocr-date" type="date" style="min-height:38px"></label>'
+'<label>Endereço do encarte: <input id="ocr-source" type="url" placeholder="https://..." style="min-width:260px;max-width:100%"></label></div>'
+'<div class="controls"><label>Token de administração: <input id="ocr-token" type="password" autocomplete="off" placeholder="Somente se for importar" style="min-width:200px"></label></div>'
+'<p class="muted">Os valores sugeridos abaixo são rascunhos. Altere dados incorretos, marque apenas os itens verificados e use o token configurado no Render para importar. O token não é salvo pelo navegador.</p>'
+'<div id="ocr-lines"></div>'
+'<div class="controls"><button type="button" id="ocr-download">Baixar rascunho JSON</button><button type="button" id="ocr-publish">Importar itens conferidos</button></div>'
+'</div>';
const catalog=document.getElementById("output");
catalog.parentNode.insertBefore(ocrPanel,catalog.nextSibling);
$("ocr-market-slot").append(market);
const info=msg=>$("ocr-info").textContent=msg;
$("ocr-find").onclick=async()=>{
 $("ocr-images").textContent="Buscando imagens publicadas na página oficial…";
 try{
   const r=await fetch("/api/flyers",{cache:"no-store"}),d=await r.json();
   $("ocr-images").innerHTML="";
   if(d.error)throw Error(d.error);
   if(!d.images.length){$("ocr-images").textContent="Nenhuma imagem de encarte localizada nessa página.";return}
   for(const item of d.images.slice(0,30)){
     const wrap=document.createElement("div");
     wrap.className="market";
     if(item.format==="image"){
       const img=document.createElement("img");
       img.src=item.url;img.alt="Página do encarte para leitura";img.loading="lazy";
       img.style.cssText="width:100%;height:125px;object-fit:contain;display:block;margin-bottom:5px";
       wrap.append(img);
       const b=document.createElement("button");b.type="button";b.textContent="Selecionar imagem";
       b.onclick=()=>{
         sourceUrl=item.url;file=null;$("ocr-file").value="";
         $("ocr-source").value=sourceUrl;info("Imagem oficial selecionada: "+new URL(sourceUrl).pathname.split("/").pop());
       };
       wrap.append(b);
     }else{
       const a=document.createElement("a");a.href=item.url;a.rel="noopener noreferrer";a.target="_blank";
       a.textContent="Encarte PDF (abra e obtenha uma imagem da página para analisar)";
       wrap.append(a);
     }
     $("ocr-images").append(wrap);
   }
 }catch(e){info("Não foi possível localizar os encartes: "+e.message);$("ocr-images").textContent="Consulte a fonte oficial diretamente ou selecione uma imagem no seu aparelho."}
};
$("ocr-file").onchange=e=>{
 file=e.target.files?.[0]||null;sourceUrl="";
 if(!file)return;
 if(!/^image\/(png|jpeg|webp)$/.test(file.type)||file.size>8_000_000){
   info("Escolha uma imagem JPG, PNG ou WebP com no máximo 8 MB.");file=null;return;
 }
 info("Arquivo selecionado: "+file.name+" — informe o endereço original do encarte ao importar.");
};
function amounts(text){
 const results=[];
 const exp=/(?:R\$\s*)?(\d{1,3})\s*[,.]\s*(\d{2})\b/g;
 for(const m of text.matchAll(exp)){
   const n=Number(m[1]+"."+m[2]);
   if(n>0.1&&n<999)results.push(n);
 }
 return results;
}
function stripPrices(text){return text.replace(/(?:R\$\s*)?\d{1,3}\s*[,.]\s*\d{2}\b/g," ").replace(/\s+/g," ").trim()}
function knownBrand(name){
 const n=name.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
 for(const b of brandNames){
   const v=b.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
   if(n.includes(v))return b;
 }
 return "Marca não identificada na imagem";
}
function kind(name){
 const n=name.toLowerCase();
 const types=["arroz","feijão","leite","azeite","creme dental","pasta de dente","óleo","açúcar","maionese","macarrão","café","farinha","frango","carne","shampoo","condicionador","iogurte","papel higiênico","sabão"];
 return types.find(t=>n.includes(t))||"Produto a confirmar";
}
function measure(name){
 const match=name.match(/(\d+(?:[,.]\d+)?)\s*(kg|g|litro|litros|l|ml|unidades?)\b/i);
 if(!match)return {quantity:"",unit:"kg"};
 const x=Number(match[1].replace(",",".")),u=match[2].toLowerCase();
 if(u==="g")return {quantity:x/1000,unit:"kg"};
 if(u==="ml")return {quantity:x/1000,unit:"l"};
 if(["l","litro","litros"].includes(u))return {quantity:x,unit:"l"};
 if(u.startsWith("unidade"))return {quantity:x,unit:"un"};
 return {quantity:x,unit:"kg"};
}
function candidates(data){
 const lines=(data.lines||[]).filter(x=>x&&x.text?.trim()&&x.bbox).map(x=>({
  text:x.text.trim(), x:(x.bbox.x0+x.bbox.x1)/2, y:(x.bbox.y0+x.bbox.y1)/2,
  w:x.bbox.x1-x.bbox.x0, conf:x.confidence??0
 }));
 const results=[];
 const blocked=/\b(cerveja|vinho|vodka|whisky|whiskey|cachaça|licor|gin|rum|tequila)\b/i;
 for(const line of lines){
   for(const price of amounts(line.text)){
     const nearby=lines.filter(x=>x!==line&&Math.abs(x.x-line.x)<Math.max(160,line.w*1.8)&&Math.abs(x.y-line.y)<130);
     nearby.sort((a,b)=>Math.hypot(a.x-line.x,(a.y-line.y)*1.2)-Math.hypot(b.x-line.x,(b.y-line.y)*1.2));
     const text=stripPrices(nearby.slice(0,3).map(x=>x.text).join(" "));
     if(!text||blocked.test(text))continue;
     const t=kind(text),b=knownBrand(text),pack=measure(text);
     if(t==="Produto a confirmar"&&text.length<9)continue;
     results.push({checked:false,name:text.slice(0,150),brand:b,kind:t,quantity:pack.quantity,
      unit:pack.unit,price,confidence:line.conf});
   }
 }
 return results.slice(0,35);
}
function draw(){
 $("ocr-review").style.display="block";
 const root=$("ocr-lines");
 root.replaceChildren();
 if(!records.length){
  root.textContent="Não consegui separar produto e preço com segurança. Experimente uma imagem mais nítida ou recorte a página em partes.";
  return;
 }
 records.forEach((r,i)=>{
  const row=document.createElement("div");
  row.className="market";row.style.marginBottom="9px";
  row.innerHTML='<label style="margin-bottom:9px"><input type="checkbox" data-id="check" style="width:17px;height:17px"> Item '+(i+1)+' conferido</label>'
   +'<div class="controls"><label>Produto<input data-id="name" style="width:240px;max-width:100%"></label>'
   +'<label>Marca<input data-id="brand" style="width:180px;max-width:100%"></label>'
   +'<label>Tipo<input data-id="kind" style="width:160px;max-width:100%"></label>'
   +'<label>Preço R$<input type="number" step="0.01" min="0.01" data-id="price" style="width:105px"></label>'
   +'<label>Quantidade<input type="number" step="0.001" min="0.001" data-id="quantity" style="width:95px"></label>'
   +'<label>Unidade<select data-id="unit"><option value="kg">kg</option><option value="l">L</option><option value="un">un</option></select></label></div>';
  for(const k of ["name","brand","kind","price","quantity","unit","checked"]){
   const input=row.querySelector('[data-id="'+(k==="checked"?"check":k)+'"]');
   if(k==="checked"){input.checked=r[k];input.onchange=()=>r[k]=input.checked}
   else{input.value=r[k];input.onchange=()=>r[k]=(k==="price"||k==="quantity")?Number(input.value):input.value}
  }
  root.append(row);
 });
}
async function getImage(){
 if(file)return file;
 if(!sourceUrl)throw Error("Selecione uma imagem do encarte ou um arquivo primeiro.");
 const r=await fetch("/api/flyers/image?url="+encodeURIComponent(sourceUrl));
 if(!r.ok)throw Error("Não foi possível carregar a imagem oficial ("+r.status+").");
 const blob=await r.blob();
 if(blob.size>8_000_000)throw Error("Imagem muito grande.");
 return blob;
}
$("ocr-scan").onclick=async()=>{
 if(working)return;
 working=true;$("ocr-scan").disabled=true;
 let worker=null;
 try{
   info("Preparando imagem e reconhecedor de texto português…");
   const img=await getImage();
   if(typeof Tesseract==="undefined")throw Error("Biblioteca de OCR indisponível; confira a conexão com a internet.");
   worker=await Tesseract.createWorker("por+eng",1,{logger:m=>{
     if(m.status)info("OCR: "+m.status+" "+(Number.isFinite(m.progress)?Math.round(m.progress*100)+"%":""));
   }});
   const result=await worker.recognize(img);
   records=candidates(result.data);
   if(!records.length && result.data.text?.trim()){
     records=[{checked:false,name:"Produto a confirmar — "+result.data.text.trim().slice(0,90),brand:"Marca não identificada na imagem",
        kind:"Produto a confirmar",quantity:"",unit:"kg",price:"",confidence:0}];
   }
   if(sourceUrl)$("ocr-source").value=sourceUrl;
   draw();info("Leitura concluída. "+records.length+" candidato(s) extraído(s); revisão obrigatória.");
 }catch(e){info("Falha na leitura da imagem: "+e.message)}
 finally{try{await worker?.terminate()}catch(_){/* no-op */}working=false;$("ocr-scan").disabled=false}
};
function reviewed(){
 const date=$("ocr-date").value,link=$("ocr-source").value.trim(),token=$("ocr-token").value.trim();
 if(!date||!Number.isFinite(Date.parse(date)))throw Error("Informe a validade no encarte.");
 const ends=new Date(date+"T23:59:59");if(ends<new Date())throw Error("Este encarte já venceu.");
 let url;try{url=new URL(link);if(url.protocol!=="https:")throw Error()}catch(_){throw Error("Informe a URL HTTPS original do encarte.")}
 const arr=records.filter(r=>r.checked).map(r=>{
   if(!r.name||!r.brand||!r.kind||!(Number(r.price)>0)||!(Number(r.quantity)>0))throw Error("Corrija os campos obrigatórios dos itens selecionados.");
   return {market:market.value,store:"",name:r.name,brand:r.brand,kind:r.kind,price:Number(r.price),
    quantity:Number(r.quantity),unit:r.unit,source:url.href,valid_until:date,checked_at:new Date().toISOString(),
    is_promotion:true,condition:"Extraído por OCR e revisado manualmente; confira estoque e condições."};
 });
 if(!arr.length)throw Error("Marque pelo menos um item depois de revisar todos os seus campos.");
 return {arr,token};
}
$("ocr-download").onclick=()=>{
 try{
  const {arr}=reviewed();const blob=new Blob([JSON.stringify(arr,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="encarte-revisado.json";a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),3000);
  info(arr.length+" item(ns) revisado(s) exportado(s), sem publicá-los.");
 }catch(e){info(e.message)}
};
$("ocr-publish").onclick=async()=>{
 try{
  const {arr,token}=reviewed();
  if(!token)throw Error("Digite o ADMIN_TOKEN configurado no Render para importar.");
  if(!confirm("Importar "+arr.length+" preço(s) revisado(s) para o banco do MercadoRadar?"))return;
  const r=await fetch("/api/admin/prices",{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Token":token},body:JSON.stringify(arr)});
  if(!r.ok)throw Error("Importação não autorizada ou rejeitada ("+r.status+").");
  const data=await r.json();
  info(data.saved+" preço(s) incorporado(s). Atenção: sem banco persistente os dados somem ao reiniciar o Render.");
  $("ocr-token").value="";
 }catch(e){info(e.message)}
};
})();
