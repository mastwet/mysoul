import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {JSDOM} from 'jsdom';
import {createPalaceBrowser} from '../../src/mysoul/web/palace.mjs';

const html=await readFile(new URL('../../src/mysoul/web/index.html',import.meta.url),'utf8');
const overview={state:'ready',counts:{wings:2,rooms:2,chunks:6},read_at:'2026-10-23T12:00:00Z',
  wings:['a','b'].map(id=>({id,label:id,rooms:[{id:'evidence-'+id,chunks:3}],chunks:3})),
  diagnostics:{backend:'chroma',vector_disabled:true},sync:{delivered:2,pending:0}};
const row=id=>({id,wing:id,room:'evidence-'+id,chunks:3,content_preview:'<img src=x onerror=alert(1)>',source_file:'mysoul:'+id});
const page=(id,offset=0)=>({drawers:[row(id)],total:21,offset,limit:20,wing:id,room:''});
const detail=id=>({...row(id),content:'<script>literal original</script>\n末尾空格  ',sources:[{id:'local',source:'chat',matches_original:true}],chunk_ids:['one','two','three']});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
async function settle(){for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));}
function fixture(custom){
  const dom=new JSDOM(html),d=dom.window.document,calls=[];
  const api=async path=>{calls.push(path);const result=custom?.(path);if(result!==undefined)return result;
    if(path==='memory/palace')return structuredClone(overview);
    if(path.startsWith('memory/palace/drawer?'))return detail(new URLSearchParams(path.split('?')[1]).get('drawer_id'));
    const p=new URLSearchParams(path.split('?')[1]);return page(p.get('wing')||'a',Number(p.get('offset')));
  };
  return {dom,d,calls,browser:createPalaceBrowser({document:d,api})};
}

test('native counts, room selection, pagination and literal source detail',async()=>{
  const f=fixture();try{
    await f.browser.open();
    assert.match(f.d.getElementById('palace-counts').textContent,/6.*分块/);
    assert.match(f.d.getElementById('palace-diagnostics').textContent,/已停用/);
    f.d.getElementById('palace-wing').value='a';f.d.getElementById('palace-wing').dispatchEvent(new f.dom.window.Event('change'));
    await settle();
    f.d.querySelector('[data-room="evidence-a"]').click();await settle();
    assert.ok(f.calls.some(p=>p.includes('room=evidence-a')));
    f.d.getElementById('palace-next').click();await settle();
    assert.ok(f.calls.at(-1).includes('offset=20'));
    f.d.querySelector('[data-drawer]').click();await settle();
    assert.equal(f.d.getElementById('palace-original').textContent,detail('a').content);
    assert.equal(f.d.querySelector('#palace-list img'),null);
    assert.equal(f.d.querySelector('#palace-original script'),null);
    assert.match(f.d.getElementById('palace-sources').textContent,/一致/);
  }finally{f.dom.window.close();}
});

test('late list and detail responses cannot replace the latest selection',async()=>{
  let armed=false;const a=deferred(),b=deferred(),da=deferred(),db=deferred();
  const f=fixture(path=>{
    if(!armed)return;
    if(path.startsWith('memory/palace/drawer?'))return path.endsWith('a')?da.promise:db.promise;
    if(path.includes('drawers?'))return path.includes('wing=a')?a.promise:b.promise;
  });try{
    await f.browser.open();armed=true;
    const wing=f.d.getElementById('palace-wing');
    wing.value='a';wing.dispatchEvent(new f.dom.window.Event('change'));
    wing.value='b';wing.dispatchEvent(new f.dom.window.Event('change'));
    b.resolve({...page('b'),drawers:[row('a'),row('b')]});await settle();
    a.resolve(page('a'));await settle();
    assert.match(f.d.getElementById('palace-page-status').textContent,/b/);
    f.d.querySelector('[data-drawer="a"]').click();f.d.querySelector('[data-drawer="b"]').click();
    db.resolve(detail('b'));await settle();da.resolve(detail('a'));await settle();
    assert.match(f.d.getElementById('palace-detail-title').textContent,/b/);
  }finally{f.dom.window.close();}
});

test('failed query retains the committed page and offers retry',async()=>{
  let fail=false;const f=fixture(path=>{
    if(fail&&path.includes('drawers?'))return Promise.reject(new Error('connection lost'));
  });try{
    await f.browser.open();const old=f.d.getElementById('palace-page-status').textContent;
    fail=true;f.d.getElementById('palace-next').click();await settle();
    assert.equal(f.d.getElementById('palace-page-status').textContent,old);
    assert.equal(f.d.querySelectorAll('[data-drawer]').length,1);
    assert.match(f.d.getElementById('palace-list-feedback').textContent,/connection lost/);
    fail=false;f.d.getElementById('palace-list-retry').click();await settle();
    assert.match(f.d.getElementById('palace-page-status').textContent,/21/);
  }finally{f.dom.window.close();}
});

test('unconfigured, unsupported and empty engines have distinct states',async()=>{
  for(const [result,expected] of [[{state:'not_configured'},/尚未接入/],[{state:'unsupported',missing:['tool']},/不支持/],[{...overview,wings:[],counts:{wings:0,rooms:0,chunks:0}},/没有记忆/]]){
    const f=fixture(path=>path==='memory/palace'?result:path.includes('drawers?')?{drawers:[],total:0,offset:0,limit:20,wing:'',room:''}:undefined);
    try{await f.browser.open();assert.match(f.d.getElementById('palace-browser').textContent,expected);}
    finally{f.dom.window.close();}
  }
});

test('refresh recovers after unsupported capability and cancels pending detail cleanly',async()=>{
  let supported=false;const pending=deferred();
  const f=fixture(path=>path==='memory/palace'?(supported?overview:{state:'unsupported'}):path.startsWith('memory/palace/drawer?')?pending.promise:undefined);
  try{
    await f.browser.open();supported=true;await f.browser.refresh();
    f.d.querySelector('[data-drawer]').click();await settle();
    await f.browser.refresh();
    assert.equal(f.d.getElementById('palace-detail').hidden,true);
    pending.resolve(detail('a'));await settle();
    assert.equal(f.d.getElementById('palace-detail').hidden,true);
  }finally{f.dom.window.close();}
});

test('successful retry restores the matching wing selector and rooms',async()=>{
  let fail=false;const f=fixture(path=>fail&&path.includes('drawers?')?Promise.reject(new Error('offline')):undefined);
  try{
    await f.browser.open();const wing=f.d.getElementById('palace-wing');
    wing.value='a';wing.dispatchEvent(new f.dom.window.Event('change'));await settle();
    fail=true;wing.value='b';wing.dispatchEvent(new f.dom.window.Event('change'));await settle();
    assert.equal(wing.value,'a');
    fail=false;f.d.getElementById('palace-list-retry').click();await settle();
    assert.equal(wing.value,'b');assert.ok(f.d.querySelector('[data-room="evidence-b"]'));
  }finally{f.dom.window.close();}
});

test('failed overview refresh settles the list request it cancelled',async()=>{
  let armed=false;const pending=deferred();
  const f=fixture(path=>armed?(path==='memory/palace'?Promise.reject(new Error('overview offline')):path.includes('drawers?')?pending.promise:undefined):undefined);
  try{
    await f.browser.open();const wing=f.d.getElementById('palace-wing'),committed=wing.value;
    armed=true;wing.value='b';wing.dispatchEvent(new f.dom.window.Event('change'));
    await f.browser.refresh();pending.resolve(page('b'));await settle();
    assert.equal(wing.value,committed);
    assert.equal(f.d.getElementById('palace-list-feedback').textContent,'');
    assert.match(f.d.getElementById('palace-feedback').textContent,/overview offline/);
  }finally{f.dom.window.close();}
});
