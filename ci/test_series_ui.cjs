const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('webui/js/app.js','utf8');
const slice=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
const functions=slice('async function startDownload(', '// ── Audio-only quality modal')+
 slice('function openQualityModal(', 'function onFormatsReady(')+
 slice('async function confirmDownload(', '// ── Browser extension confirm modal');
const detail='https://hianime.at/fullmetal-alchemist-brotherhood-1140';
const episode=detail.replace('/fullmetal','/watch/fullmetal')+'?ep=19026';
function harness(current=false,fail=false){
 const elements={};
 const one={};
 const $=id=>elements[id]??=( {value:'',checked:false,hidden:false,disabled:false,textContent:'',
  replaceChildren(...options){this.options=options;},showModal(){this.open=true;},close(){this.open=false;}} );
 const calls=[];
 const series={title:'Fullmetal Alchemist: Brotherhood',count:64,episodes:Array.from({length:64},(_,i)=>({id:String(19026+i),number:String(i+1),url:episode.replace('19026',String(19026+i))})),current_episode:current?{id:'19026',number:'1',url:episode}:null};
 const S={connected:true,settings:{save_path:'downloads'},view:'queue'};
 const context=vm.createContext({S,$,clearTimeout(){},setTimeout(){return 0;},
  toast(){},switchView(){},window:{},document:{createElement(){return {};}},
  showFallbackQualities(){S.selectedFmt='bestvideo+bestaudio/best';S.selectedQualLabel='Best quality';$('btn-download').disabled=false;},
  ws:{fire:(...args)=>calls.push(args),send:async(action,data)=>{
   calls.push([action,data]);
   if(action==='detect')return {detection:{type:'ytdlp',label:'HiAnime',series_capable:true}};
   if(action==='inspect_series'){if(fail)throw Error('Site unavailable');return {series};}
   return {ok:true};
  }}});
 vm.runInContext(functions,context);
 return {context,S,$,calls,one};
}
test('series page prompts with 64 episodes before starting any transfer',async()=>{
 const h=harness();await h.context.startDownload(detail);
 assert.equal(h.$('series-title').textContent,'64 episodes found');
 assert.equal(h.$('series-scope').value,'all');
 assert.equal(h.$('series-scope').options.length,65);
 assert.equal(h.$('series-scope').options[0].textContent,'All episodes (64)');
 assert.equal(h.$('series-scope').options[64].textContent,'Episode 64');
 assert.equal(h.$('series-zip').checked,false);assert.equal(h.$('quality-modal').open,true);
 assert.equal(h.calls.some(c=>c[0]==='add'),false);
});
test('episode page defaults to current episode and disables ZIP',async()=>{
 const h=harness(true);await h.context.startDownload(episode);
 assert.equal(h.$('series-scope').value,'episode:19026');
 assert.match(h.$('series-scope').options[1].textContent,/linked episode/);
 assert.equal(h.$('series-zip').disabled,true);
 assert.equal(h.calls.find(c=>c[0]==='fetch_formats')[1].url,episode);
});
test('ticking ZIP with all episodes submits a batch archive job',async()=>{
 const h=harness(true);await h.context.startDownload(episode);
 h.$('series-scope').value='all';h.$('series-zip').checked=true;h.context.updateSeriesChoice();
 assert.equal(h.$('series-zip').disabled,false);assert.equal(h.$('series-note').hidden,false);
 await h.context.confirmDownload();
 const payload=h.calls.find(c=>c[0]==='add')[1];
 assert.equal(payload.opts.dl_type,'hianime_series');assert.equal(payload.opts.series.zip,true);
 assert.equal(payload.opts.series.episodes.length,64);
});
test('unchecked ZIP submits all episodes as separate files',async()=>{
 const h=harness();await h.context.startDownload(detail);await h.context.confirmDownload();
 const payload=h.calls.find(c=>c[0]==='add')[1];assert.equal(payload.opts.series.zip,false);
});
test('single episode submits the existing downloader with no batch',async()=>{
 const h=harness(true);await h.context.startDownload(episode);await h.context.confirmDownload();
 const payload=h.calls.find(c=>c[0]==='add')[1];assert.equal(payload.url,episode);
 assert.equal(payload.opts.dl_type,'ytdlp');assert.equal(payload.opts.series,undefined);
});
test('failed discovery restores the button and does not queue anything',async()=>{
 const h=harness(false,true);await h.context.startDownload(detail);
 assert.equal(h.$('btn-add').disabled,false);assert.equal(h.S.inspectingSeries,false);
 assert.equal(h.$('quality-modal').open,undefined);assert.equal(h.calls.some(c=>c[0]==='add'),false);
});

test('any listed episode can be selected from a series page',async()=>{
 const h=harness();await h.context.startDownload(detail);
 h.$('series-scope').value='episode:19042';h.context.updateSeriesChoice();
 const request=h.calls.filter(c=>c[0]==='fetch_formats').at(-1)[1];
 assert.equal(request.url,episode.replace('19026','19042'));
 assert.equal(h.$('series-zip').disabled,true);
 await h.context.confirmDownload();
 const payload=h.calls.find(c=>c[0]==='add')[1];
 assert.equal(payload.url,request.url);assert.equal(payload.opts.series,undefined);
});
test('an episode link can select a different episode or return to all',async()=>{
 const h=harness(true);await h.context.startDownload(episode);
 h.$('series-scope').value='episode:19089';h.context.updateSeriesChoice();
 assert.equal(h.calls.filter(c=>c[0]==='fetch_formats').at(-1)[1].url,episode.replace('19026','19089'));
 h.$('series-scope').value='all';h.context.updateSeriesChoice();
 assert.equal(h.$('series-zip').disabled,false);
 await h.context.confirmDownload();
 assert.equal(h.calls.find(c=>c[0]==='add')[1].opts.series.episodes.length,64);
});
test('a stale or invalid episode selection cannot queue a download',async()=>{
 const h=harness();await h.context.startDownload(detail);
 h.$('series-scope').value='episode:missing';h.context.updateSeriesChoice();
 assert.equal(h.$('btn-download').disabled,true);
 await h.context.confirmDownload();assert.equal(h.calls.some(c=>c[0]==='add'),false);
});
