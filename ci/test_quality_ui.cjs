const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('webui/js/app.js','utf8');
const handler = source.slice(source.indexOf('function onFormatsReady('),source.indexOf('const FALLBACK_QUALITIES'));
function render(formats) {
 let shown;
 const context = vm.createContext({S:{pendingReqId:'test'}, clearTimeout(){},
   $: id => id === 'quality-modal' ? {open:true} : {},
   heightOf: label => parseInt(label),fmtBytes: String,
   showFallbackQualities(){throw Error('Unexpected fallback');},
   showQualityOptions: opts => {shown=opts;}});
 vm.runInContext(handler,context);
 context.onFormatsReady({request_id:'test',formats});
 return shown;
}
test('HLS resolutions remain selectable when codec metadata is absent', () => {
 const opts=render([{height:360,vcodec:''},{height:720,vcodec:''},{height:1080,vcodec:''}]);
 assert.deepEqual(Array.from(opts,o=>o.label),['1080p','720p','360p','Audio only  (MP3 · 320 kbps)']);
});
test('audio-only streams are excluded from video choices and duplicate heights collapse', () => {
 const opts=render([{height:720,vcodec:'none'},{height:1080,vcodec:'h264'},{height:1080,vcodec:'h264'}]);
 assert.equal(opts.length,2);assert.equal(opts[0].label,'1080p');
});
