import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createRequire} from "node:module";
import test from "node:test";
import {JSDOM} from "jsdom";
import {createMessageRenderer,shouldSubmitKey} from "../../src/mysoul/web/conversation.mjs";

import {mergeTimeline,prependScrollAnchor} from "../../src/mysoul/web/timeline.mjs";
const require=createRequire(import.meta.url);
const MarkdownIt=require("../../src/mysoul/web/vendor/markdown-it.min.js");
const html=await readFile(new URL("../../src/mysoul/web/index.html",import.meta.url),"utf8");
const script=(await readFile(new URL("../../src/mysoul/web/app.js",import.meta.url),"utf8")).replace(/^import .*;\r?\n/gm,"");

async function until(predicate) {
  for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}
  assert.ok(predicate(),"UI did not settle");
}
async function fixture(chat,modelRequest,{tokenless=false}={}) {
  const dom=new JSDOM(html,{url:tokenless?"http://127.0.0.1:8765/":"http://127.0.0.1:8765/#token=fixture-token",runScripts:"outside-only",pretendToBeVisual:true});
  const {window}=dom,document=window.document;
  const server={state:{fatigue:0,activity:"rest",mode:"normal",autonomy_enabled:true,autonomy_interval_minutes:360,next_initiative_at:null,autonomy_last_checked_at:null,autonomy_last_result:"waiting",model_calls:0,tokens_used:0},limits:{model_calls:100,tokens:50000,context_chars:131072,request_timeout:120},backend:"replay",send_enabled:false,persona:{version:0,public:"A companion",sections:{identity:"identity",relationship:"relationship",redline:"redline",user:"user",world:"world",dream:"dream",dark:"dark",mission:"mission"}},personaHistory:[{version:0,public:"A companion"}],memory:{backend:"local",method:"local lexical",evidence_count:0,pending_mempalace_sync:0,last_context:null},recap:{version:0,text:"",refs:[]},gates:{provider:"deferred",mempalace:"deferred",qq:"deferred",isolation:"disabled"},goals:[],activities:[],interactions:[],drafts:[],effects:[]};
  const sends=[],writes=[],historyReads=[];let pollCallback=()=>{};
  server.model={version:0,mode:"replay",url:"",model:"",key_present:false,source:"runtime",output_token_limit:null,token_budget:50000,context_chars:131072,request_timeout:120};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  window.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new window.Event("close"));};
  window.mergeTimeline=mergeTimeline;window.prependScrollAnchor=prependScrollAnchor;window.markdownit=MarkdownIt;window.createMessageRenderer=createMessageRenderer;window.shouldSubmitKey=shouldSubmitKey;
  window.matchMedia=()=>({matches:false,addEventListener(){}});
  window.setInterval=callback=>{pollCallback=callback;return 0;};
  window.fetch=async(path,options)=>{
    let result;
    if(path==="/api/session")result={csrf:"fixture-csrf",auth_required:!tokenless};
    else if(path==="/api/status")result=server;
    else if(path.startsWith('/api/timeline')){
      const items=[...server.interactions.map((body,i)=>({id:`chat:${body.event_id}`,seq:i+1,revision:1,kind:'chat',body})),...(server.timeline||[])];
      result={items,next_before:items[0]?.seq||null,has_more:false,change_cursor:items.length};
    }else if(path==='/api/archives')result=server.compression||{policy:{version:0},frontier:[],runs:[]};
    else if(path==="/api/chat"){
      const body=JSON.parse(options.body);sends.push(body.text);const custom=chat?await chat(body.text):null;
      result=custom||{event_id:`event-${sends.length}`,choice:"owner_served",input:body.text,text:"**已收到**"};
      server.interactions.push(result);
    }else if(path==="/api/model"||path==="/api/model/test"){
      const body=JSON.parse(options.body);
      if(modelRequest)await modelRequest(path,body);
      if(path==="/api/model/test")result={ok:true};
      else {server.model={...body,version:body.expected_version+1,key_present:true,source:"local"};delete server.model.api_key;server.limits.tokens=body.token_budget;result=server.model;}
    }else if(path==="/api/persona"){
      const body=JSON.parse(options.body);writes.push({path,body});
      if(body.expected_version!==server.persona.version)return {ok:false,status:409,json:async()=>({detail:"stale"})};
      server.persona={version:body.expected_version+1,public:body.public,sections:body.sections};server.personaHistory.push({version:server.persona.version,public:body.public});result=server.persona;
    }else if(path==="/api/persona/history"){historyReads.push(path);result=server.personaHistory;
    }else if(path==="/api/persona/changes")result=[{id:"change",actor:"automatic",status:"applied",base_version:0,version:1,changes:[{target:"relationship",old:"old relationship",new:"new relationship",reason:"evidence",evidence_refs:["source"]}]}];
    else if(path==="/api/cognition/run"||path==="/api/cognition/policy"||path==="/api/persona/rollback"){
      const body=JSON.parse(options.body);writes.push({path,body});
      if(path==="/api/cognition/policy")server.cognition.policy={...body,version:body.expected_version+1};
      result=path==="/api/cognition/run"?{status:"queued",run_id:"run1"}:server.cognition?.policy||{};
    }else if(path==="/api/life"){
      const body=JSON.parse(options.body);writes.push({path,body});
      server.state={...server.state,...body,next_initiative_at:body.autonomy_enabled?"2026-10-22T12:00:00Z":null};result=server.state;
    }else if(path==="/api/evidence"||path==="/api/recap/history")result=[];
    else if(path.startsWith("/api/memory/search?"))result=[];
    else throw new Error(`Unexpected fixture request: ${path}`);
    return {ok:true,status:200,json:async()=>structuredClone(result)};
  };
  window.eval(script);
  await until(()=>!document.getElementById("workspace").hidden);
  await until(()=>document.getElementById("connection").textContent==="已连接 · 本机");
  const textarea=document.getElementById("chat-text");
  function send(text){
    textarea.value=text;textarea.dispatchEvent(new window.Event("input",{bubbles:true}));textarea.focus();
    textarea.dispatchEvent(new window.KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true}));
    assert.equal(textarea.disabled,true);
    // Chromium moves focus to BODY when disabling the textarea; jsdom does not.
    // Reproduce that observed browser boundary using its real focus implementation.
    document.body.tabIndex=-1;document.body.focus();document.body.removeAttribute("tabindex");
    assert.equal(document.activeElement,document.body);
  }
  return {window,document,textarea,sends,writes,historyReads,server,send,poll:async()=>{pollCallback();await until(()=>document.getElementById("persona-version").textContent.includes(`v${server.persona.version}`));},close:()=>window.close()};
}

test("successive keyboard turns restore the composer without duplicate messages",async()=>{
  const ui=await fixture();
  try{
    ui.send("第一条");
    await until(()=>!ui.textarea.disabled&&ui.textarea.value==="");
    assert.equal(ui.document.activeElement,ui.textarea);
    ui.send("第二条");
    await until(()=>!ui.textarea.disabled&&ui.textarea.value==="");
    assert.equal(ui.document.activeElement,ui.textarea);
    assert.deepEqual(ui.sends,["第一条","第二条"]);
    assert.equal(ui.document.querySelectorAll(".message-turn").length,2);
    assert.equal(ui.document.querySelector(".message-body strong").textContent,"已收到");
  }finally{ui.close();}
});

test("main chat shows initiative state and persists its cadence controls",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    assert.match(d.getElementById("initiative-status").textContent,/自主发起已开启/);
    d.getElementById("open-settings").click();
    d.querySelector('[data-setting="life"]').click();
    assert.ok(d.getElementById("autonomy-enabled"));
    d.getElementById("autonomy-enabled").checked=false;
    d.getElementById("autonomy-interval").value="720";
    d.getElementById("life-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>ui.writes.some(item=>item.path==="/api/life")&&!d.getElementById("life-form").hasAttribute("aria-busy"));
    assert.equal(ui.writes.at(-1).body.autonomy_enabled,false);
    assert.equal(ui.writes.at(-1).body.autonomy_interval_minutes,720);
    assert.match(d.getElementById("initiative-status").textContent,/自主发起已暂停/);
  }finally{ui.close();}
});

test("autonomous messages are labeled in the main conversation",async()=>{
  const ui=await fixture();
  try{
    ui.server.interactions.push({event_id:"initiative-1",choice:"initiative",input:"",text:"我想到一个具体建议。"});
    ui.poll();
    await until(()=>ui.document.getElementById("turn-initiative-1"));
    assert.match(ui.document.getElementById("turn-initiative-1").textContent,/主动发起/);
    assert.match(ui.document.getElementById("turn-initiative-1").textContent,/我想到一个具体建议。/);
    assert.equal(ui.document.getElementById("recent-messages"),null);
  }finally{ui.close();}
});

test("main chat reports when an autonomous check completed quietly",async()=>{
  const ui=await fixture();
  try{
    Object.assign(ui.server.state,{autonomy_enabled:true,autonomy_interval_minutes:360,autonomy_last_checked_at:"2026-10-22T11:43:02Z",autonomy_last_result:"silent"});
    ui.poll();
    await until(()=>ui.document.getElementById("initiative-status").textContent.includes("上次保持安静"));
  }finally{ui.close();}
});

test("main chat explains fatigue and exhausted budget pauses",async()=>{
  const ui=await fixture();
  try{
    Object.assign(ui.server.state,{autonomy_enabled:true,fatigue:.95});
    ui.poll();
    await until(()=>ui.document.getElementById("initiative-status").textContent.includes("疲劳"));
    Object.assign(ui.server.state,{fatigue:0,tokens_used:50000});
    ui.poll();
    await until(()=>ui.document.getElementById("initiative-status").textContent.includes("预算"));
  }finally{ui.close();}
});

test("successful reconnection clears a stale connection notice",async()=>{
  const ui=await fixture();
  try{
    const fetch=ui.window.fetch;
    ui.window.fetch=async(path,options)=>{
      if(path==="/api/status")throw new Error("offline");
      return fetch(path,options);
    };
    ui.poll();
    await until(()=>ui.document.getElementById("notice-text").textContent.includes("连接中断"));
    ui.window.fetch=fetch;
    ui.poll();
    await until(()=>ui.document.getElementById("connection").textContent==="已连接 · 本机");
    assert.equal(ui.document.getElementById("notice").hidden,true);
  }finally{ui.close();}
});

test("model settings test without activation then save the configured provider",async()=>{
  const requests=[];
  const ui=await fixture(null,async(path,body)=>requests.push({path,body}));
  try{
    const d=ui.document;
    d.getElementById("open-settings").click();
    assert.ok(d.querySelector('[data-setting="model"]'),"model configuration entry is missing");
    d.querySelector('[data-setting="model"]').click();
    for(const [id,value] of Object.entries({"model-mode":"provider","model-url":"https://provider.test/v1","model-name":"my-model","model-key":"private-key"})){
      d.getElementById(id).value=value;d.getElementById(id).dispatchEvent(new ui.window.Event("input",{bubbles:true}));
    }
    d.getElementById("test-model").click();
    await until(()=>requests.length===1&&!d.getElementById("test-model").disabled);
    assert.equal(d.getElementById("runtime-label").textContent,"离线回放");
    assert.equal(d.getElementById("model-key").value,"private-key");
    d.getElementById("model-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>requests.length===2&&d.getElementById("model-key").value==="");
    assert.equal(requests[1].body.api_key,"private-key");
    assert.equal(requests[1].body.context_chars,131072);
    assert.equal(requests[1].body.request_timeout,120);
    assert.match(d.getElementById("runtime-label").textContent,/my-model/);
    assert.equal(d.getElementById("model-key").type,"password");
  }finally{ui.close();}
});

test("persona editor exposes eight versioned sections and a public projection",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    d.querySelector('[data-view="persona"]').click();
    d.getElementById("edit-persona").click();
    assert.equal(d.querySelectorAll("#persona-fields textarea").length,10);
    d.getElementById("persona-identity").value="A clearer identity";
    d.getElementById("persona-public").value="Public companion";
    d.getElementById("persona-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>ui.writes.some(write=>write.path==="/api/persona")&&!d.getElementById("persona-form").hasAttribute("aria-busy"));
    const submitted=ui.writes.find(write=>write.path==="/api/persona").body;
    assert.equal(submitted.expected_version,0);
    assert.equal(submitted.sections.identity,"A clearer identity");
    assert.equal(submitted.public,"Public companion");
  }finally{ui.close();}
});

test("persona edits keep the version captured when the editor opened",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    d.querySelector('[data-view="persona"]').click();
    d.getElementById("edit-persona").click();
    d.getElementById("persona-identity").value="Stale editor text";
    ui.server.persona={...ui.server.persona,version:1,public:"Newer version"};
    await ui.poll();
    d.getElementById("persona-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>!d.getElementById("persona-form").hasAttribute("aria-busy"));
    assert.equal(ui.writes.at(-1).body.expected_version,0);
    assert.equal(ui.server.persona.version,1);
    assert.match(d.getElementById("notice-text").textContent,/状态已变化/);
  }finally{ui.close();}
});

test("persona is a sidebar page and its history refreshes after saving",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    const nav=d.querySelector('[data-view="persona"]');
    assert.ok(nav,"persona should have a first-class sidebar entry");
    assert.equal(d.querySelector('[data-setting="persona"]'),null,"persona should no longer be nested under settings");
    nav.click();
    assert.equal(d.getElementById("page-title").textContent,"人格");
    assert.equal(d.getElementById("persona").hidden,false);
    await until(()=>d.getElementById("persona-history").textContent.includes("人格 v0"));
    assert.ok(ui.historyReads.length>=1);
    d.getElementById("edit-persona").click();
    d.getElementById("persona-public").value="New public version";
    d.getElementById("persona-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>!d.getElementById("persona-form").hasAttribute("aria-busy")&&d.getElementById("persona-history").textContent.includes("人格 v1"));
  }finally{ui.close();}
});

test("memory page can run an explicit local recall search",async()=>{
  const requests=[];
  const ui=await fixture();
  try{
    const original=ui.window.fetch.bind(ui.window);
    ui.window.fetch=async(path,options)=>{if(String(path).startsWith("/api/memory/search?"))requests.push(String(path));return original(path,options);};
    ui.document.querySelector('[data-view="memory"]').click();
    await until(()=>requests.length===0&&ui.document.getElementById("memory-status").textContent.includes("本机按关键词匹配"));
    const input=ui.document.getElementById("memory-query");input.value="蓝鲸";
    ui.document.getElementById("memory-search-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>requests.length===1&&!ui.document.getElementById("memory-search-form").hasAttribute("aria-busy"));
    assert.match(requests[0],/q=%E8%93%9D%E9%B2%B8/);
  }finally{ui.close();}
});

test("failed model save retains all entered configuration",async()=>{
  const ui=await fixture(null,async()=>{throw new Error("offline");});
  try{
    const d=ui.document;
    assert.ok(d.getElementById("model-form"),"model form is missing");
    d.getElementById("model-key").value="retain-secret";
    d.getElementById("model-key").dispatchEvent(new ui.window.Event("input",{bubbles:true}));
    d.getElementById("model-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>!d.getElementById("model-form").hasAttribute("aria-busy"));
    assert.equal(d.getElementById("model-key").value,"retain-secret");
    assert.match(d.getElementById("notice-text").textContent,/输入已保留/);
  }finally{ui.close();}
});

test("discarding model edits clears the secret and restores the active configuration",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    d.getElementById("model-key").value="unsaved-secret";
    d.getElementById("model-mode").value="provider";
    d.getElementById("model-key").dispatchEvent(new ui.window.Event("input",{bubbles:true}));
    assert.ok(d.getElementById("reset-model"),"discard edits action is missing");
    d.getElementById("reset-model").click();
    assert.equal(d.getElementById("model-key").value,"");
    assert.equal(d.getElementById("model-mode").value,"replay");
    assert.equal(d.getElementById("provider-fields").hidden,true);
  }finally{ui.close();}
});

test("invalid provider fields cannot block switching back to offline replay",async()=>{
  const requests=[];
  const ui=await fixture(null,async(path,body)=>requests.push({path,body}));
  try{
    const d=ui.document;
    d.getElementById("model-mode").value="provider";
    d.getElementById("model-url").value="not a valid url";
    d.getElementById("model-mode").dispatchEvent(new ui.window.Event("change",{bubbles:true}));
    d.getElementById("model-mode").value="replay";
    d.getElementById("model-mode").dispatchEvent(new ui.window.Event("change",{bubbles:true}));
    assert.equal(d.getElementById("model-form").checkValidity(),true);
    d.getElementById("model-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>requests.length===1&&!d.getElementById("model-form").hasAttribute("aria-busy"));
    assert.equal(requests[0].body.mode,"replay");
    assert.equal(requests[0].body.url,"");
  }finally{ui.close();}
});

test("empty token settings submit explicit unlimited values and display unlimited budget",async()=>{
  const requests=[];
  const ui=await fixture(null,async(path,body)=>requests.push(body));
  try{
    const d=ui.document;
    assert.ok(d.getElementById("model-output-limit"),"output limit setting is missing");
    assert.ok(d.getElementById("model-token-budget"),"total token setting is missing");
    for(const id of ["model-output-limit","model-token-budget"]){
      d.getElementById(id).value="";
      d.getElementById(id).dispatchEvent(new ui.window.Event("input",{bubbles:true}));
    }
    d.getElementById("model-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>requests.length===1&&!d.getElementById("model-form").hasAttribute("aria-busy"));
    assert.equal(requests[0].output_token_limit,null);
    assert.equal(requests[0].token_budget,null);
    assert.match(d.getElementById("budget-tokens").textContent,/不限/);
    assert.equal(d.getElementById("notice-text").textContent,"");
  }finally{ui.close();}
});

test("failed send keeps the draft and returns keyboard focus",async()=>{
  const ui=await fixture(()=>{throw new Error("network down");});
  try{
    ui.send("失败后应保留的草稿");
    await until(()=>!ui.textarea.disabled);
    assert.equal(ui.textarea.value,"失败后应保留的草稿");
    assert.equal(ui.document.activeElement,ui.textarea);
    assert.match(ui.document.getElementById("notice-text").textContent,/输入已保留/);
    assert.equal(ui.document.querySelectorAll(".message-turn").length,0);
  }finally{ui.close();}
});

test("structured model failure keeps the chat draft and shows the failure category",async()=>{
  const ui=await fixture(text=>({event_id:"failure-1",choice:"owner_served",input:text,text:"模型请求超时。",error:{code:"timeout",message:"模型请求超时，可以调高请求超时后重试。"}}));
  try{
    ui.send("長回复请求");
    await until(()=>!ui.textarea.disabled&&ui.document.querySelector(".chat-failure"));
    assert.equal(ui.textarea.value,"長回复请求");
    assert.match(ui.document.querySelector(".chat-failure").textContent,/timeout/);
  }finally{ui.close();}
});

test("finishing a send after navigation does not steal focus back to chat",async()=>{
  let release;const pending=new Promise(resolve=>release=resolve);
  const ui=await fixture(()=>pending);
  try{
    ui.send("稍后完成");
    const tasks=ui.document.querySelector('[data-view="tasks"]');tasks.click();tasks.focus();
    release();await until(()=>!ui.textarea.disabled);
    assert.equal(ui.document.activeElement,tasks);
    assert.equal(ui.document.getElementById("chat").hidden,true);
    assert.equal(ui.document.getElementById("tasks").hidden,false);
  }finally{release();ui.close();}
});


test("three-minute heartbeat is selectable, persisted and displayed in minutes",async()=>{
  const ui=await fixture();
  try{
    const d=ui.document;
    d.getElementById("open-settings").click();
    d.querySelector('[data-setting="life"]').click();
    const interval=d.getElementById("autonomy-interval");
    interval.value="3";
    assert.equal(interval.value,"3");
    d.getElementById("life-form").dispatchEvent(new ui.window.Event("submit",{bubbles:true,cancelable:true}));
    await until(()=>ui.writes.some(item=>item.path==="/api/life")&&!d.getElementById("life-form").hasAttribute("aria-busy"));
    assert.equal(ui.writes.at(-1).body.autonomy_interval_minutes,3);
    assert.match(d.getElementById("initiative-status").textContent,/每 3 分钟/);
  }finally{ui.close();}
});


test("tokenless local test opens directly and unlimited calls do not pause initiative",async()=>{
  const ui=await fixture(undefined,undefined,{tokenless:true});
  try{
    assert.equal(ui.document.getElementById("login").hidden,true);
    ui.server.state.model_calls=1000;ui.server.limits.model_calls=null;
    ui.server.persona.version++;
    await ui.poll();
    assert.match(ui.document.getElementById("initiative-status").textContent,/自主发起已开启/);
    assert.match(ui.document.getElementById("budget-calls").textContent,/不限/);
    ui.send("免令牌测试");
    await until(()=>!ui.textarea.disabled);
    assert.equal(ui.sends.length,1);
  }finally{ui.close();}
});

test("memory shows durable failure and manual retry; persona shows automatic change and rollback",async()=>{
  const ui=await fixture();
  try {
    const d=ui.document;
    ui.server.cognition={policy:{version:0,enabled:true,persona_enabled:true,interval_minutes:3},pending:1,covered:0,sources:[{id:"source",event_id:"event",role:"user",covered:0,total:12}],runs:[{id:"run1",status:"failed",stage:"reflect",error:"TimeoutError",created_at:"2026-10-22T12:00:00Z",receipts:["collect","prepare","reconcile"]}]};
    d.querySelector('[data-view="memory"]').click();
    await until(()=>d.getElementById("cognition-status")?.textContent.includes("1"));
    assert.match(d.getElementById("cognition-runs").textContent,/失败/);
    assert.match(d.getElementById("cognition-runs").textContent,/TimeoutError/);
    d.getElementById("organize-now").click();
    await until(()=>ui.writes.some(w=>w.path==="/api/cognition/run"));
    ui.server.persona.version=1;
    d.querySelector('[data-view="persona"]').click();
    await until(()=>d.getElementById("persona-changes").textContent.includes("new relationship"));
    assert.match(d.getElementById("persona-changes").textContent,/old relationship/);
    assert.match(d.getElementById("persona-auto-status").textContent,/自动生效/);
    const rollback=[...d.querySelectorAll('#persona-history button')].find(b=>b.textContent.includes("恢复"));
    assert.ok(rollback);rollback.click();
    await until(()=>ui.writes.some(w=>w.path==="/api/persona/rollback")&&!d.querySelector('[aria-busy="true"]'));
  } finally {ui.close();}
});

test("persona automatic toggle persists without discarding editor draft",async()=>{
  const ui=await fixture();
  try {
    const d=ui.document;
    ui.server.cognition={policy:{version:0,enabled:true,persona_enabled:true,interval_minutes:3},pending:0,covered:0,sources:[],runs:[]};
    d.querySelector('[data-view="persona"]').click();
    await until(()=>d.getElementById("persona-auto-status").textContent.includes("自动生效"));
    d.getElementById("edit-persona").click();d.getElementById("persona-identity").value="unsaved draft";
    d.getElementById("persona-auto-toggle").click();
    await until(()=>ui.writes.some(w=>w.path==="/api/cognition/policy")&&!d.querySelector('[aria-busy="true"]'));
    assert.equal(ui.writes.at(-1).body.persona_enabled,false);
    assert.equal(d.getElementById("persona-identity").value,"unsaved draft");
  } finally {ui.close();}
});

test("autonomous failure and silence expose the persisted reason",async()=>{
  const ui=await fixture();
  try{
    ui.server.state.autonomy_enabled=true;
    ui.server.state.autonomy_last_result="error";
    ui.server.initiative={outcome:"error",error:{code:"timeout",message:"模型请求超时，请稍后重试。"},reason:""};
    await ui.poll();
    await until(()=>ui.document.getElementById("initiative-detail")?.textContent.includes("模型请求超时"));
    assert.match(ui.document.getElementById("initiative-status").textContent,/超时/);
    ui.server.state.autonomy_last_result="silent";
    ui.server.initiative={outcome:"silent",reason:"刚分享过这个话题，暂不重复。",error:null};
    await ui.poll();
    await until(()=>ui.document.getElementById("initiative-detail").textContent.includes("暂不重复"));
  }finally{ui.close();}
});


test("single chat has no session list",async()=>{
 const ui=await fixture();try{assert.equal(ui.document.querySelector('.recent-section'),null);assert.ok(ui.document.getElementById('load-older'));}finally{ui.close();}
});
test("failed older page preserves loaded messages and draft",async()=>{
 const ui=await fixture();try{
  ui.send('retain this');await until(()=>!ui.textarea.disabled&&ui.textarea.value==='');
  ui.textarea.value='unsent draft';
  const fetch=ui.window.fetch;ui.window.fetch=async(path,options)=>{if(String(path).includes('before='))throw new Error('offline');return fetch(path,options);};
  ui.document.getElementById('load-older').hidden=false;ui.document.getElementById('load-older').click();
  await until(()=>ui.document.getElementById('history-feedback').textContent.includes('重试'));
  assert.equal(ui.document.querySelectorAll('.message-turn').length,1);assert.equal(ui.textarea.value,'unsent draft');
 }finally{ui.close();}
});
test("task card updates in place and archive inspection preserves draft",async()=>{
 const ui=await fixture();try{
  ui.server.timeline=[{id:'task:g',seq:1,revision:1,kind:'task',body:{goal_id:'g',activity_id:'a',objective:'Read report',status:'active',result:''}}];
  await ui.poll();await until(()=>ui.document.querySelector('[data-key="task:g"]'));
  ui.server.timeline[0]={...ui.server.timeline[0],revision:2,body:{...ui.server.timeline[0].body,status:'completed',result:'Verified result'}};
  await ui.poll();await until(()=>ui.document.querySelector('[data-key="task:g"]').textContent.includes('Verified result'));
  assert.equal(ui.document.querySelectorAll('[data-key="task:g"]').length,1);
  ui.textarea.value='keep my draft';ui.document.querySelector('[data-view="memory"]').click();
  await until(()=>ui.document.getElementById('archive-status').textContent.includes('L0'));
  ui.document.querySelector('[data-view="chat"]').click();await new Promise(resolve=>setTimeout(resolve,30));assert.equal(ui.textarea.value,'keep my draft');
 }finally{ui.close();}
});

test("pagination with live append preserves older messages and newer card revisions",async()=>{
 const ui=await fixture();try{
  const fetch=ui.window.fetch;let latest=true;
  const row=(seq,revision=1)=>({id:`chat:e${seq}`,seq,revision,kind:'chat',body:{event_id:`e${seq}`,input:`question ${seq}`,text:`reply ${revision}`,choice:'owner_served'}});
  ui.window.fetch=async(path,options)=>{
   if(String(path).startsWith('/api/timeline')){
    let page;
    if(String(path).includes('before='))page={items:[row(1),row(2)],has_more:false,next_before:1,change_cursor:99};
    else page={items:latest?[row(3),row(4)]:[row(4,2),row(5)],has_more:false,next_before:3,change_cursor:latest?4:6};
    latest=false;return {ok:true,json:async()=>page};
   }return fetch(path,options);
  };
  await ui.poll();await until(()=>ui.document.getElementById('turn-e4'));
  ui.document.getElementById('load-older').hidden=false;ui.document.getElementById('load-older').click();
  await until(()=>ui.document.getElementById('turn-e1'));
  await ui.poll();await until(()=>ui.document.getElementById('turn-e5'));
  assert.equal(ui.document.querySelectorAll('.message-turn').length,5);
  assert.match(ui.document.getElementById('turn-e4').textContent,/reply 2/);
 }finally{ui.close();}
});

test("cancelled task card reconciles after its busy action completes",async()=>{
 const ui=await fixture();try{
  ui.server.timeline=[{id:'task:g',seq:1,revision:1,kind:'task',body:{goal_id:'g',activity_id:'a',objective:'Task action',status:'suspended'}}];
  await ui.poll();await until(()=>ui.document.querySelector('[data-key="task:g"]'));
  const fetch=ui.window.fetch;ui.window.fetch=async(path,options)=>{
   if(path==='/api/goals/g/cancel'){
    ui.server.timeline[0]={...ui.server.timeline[0],revision:2,body:{...ui.server.timeline[0].body,status:'cancelled'}};
    return {ok:true,json:async()=>({status:'cancelled'})};
   }return fetch(path,options);
  };
  const row=ui.document.querySelector('[data-key="task:g"]');[...row.querySelectorAll('button')].find(b=>b.textContent==='取消任务').click();
  await until(()=>!row.hasAttribute('aria-busy'));await ui.poll();
  await until(()=>ui.document.querySelector('[data-key="task:g"]').textContent.includes('已取消'));
  assert.equal(ui.document.querySelector('[data-key="task:g"]').querySelectorAll('button').length,0);await new Promise(r=>setTimeout(r,30));
 }finally{ui.close();}
});
test("delayed older page anchors only prepend growth and preserves intervening scroll",async()=>{
 const ui=await fixture();let release;try{
  const row=seq=>({id:`chat:p${seq}`,seq,revision:1,kind:'chat',body:{event_id:`p${seq}`,input:`p${seq}`,text:'reply',choice:'owner_served'}});
  ui.server.timeline=[row(3),row(4)];await ui.poll();await until(()=>ui.document.getElementById('turn-p4'));await new Promise(r=>setTimeout(r,25));
  const scroller=ui.document.getElementById('conversation-scroll');
  Object.defineProperty(scroller,'scrollHeight',{get:()=>1000+(ui.document.getElementById('messages').children.length-2)*100});
  scroller.scrollTop=100;const fetch=ui.window.fetch;
  ui.window.fetch=async(path,options)=>{
   if(String(path).includes('before=')){await new Promise(resolve=>{release=resolve;});return {ok:true,json:async()=>({items:[row(1),row(2)],has_more:false,next_before:1})};}
   return fetch(path,options);
  };
  ui.document.getElementById('load-older').hidden=false;ui.document.getElementById('load-older').click();await until(()=>release);
  ui.server.timeline.push(row(5));await ui.poll();await until(()=>ui.document.getElementById('turn-p5'));
  scroller.scrollTop=300;release();await until(()=>!ui.document.getElementById('load-older').disabled);
  assert.equal(scroller.scrollTop,500);
 }finally{if(release)release();ui.close();}
});
