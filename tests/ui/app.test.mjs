import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createRequire} from "node:module";
import test from "node:test";
import {JSDOM} from "jsdom";
import {createMessageRenderer,shouldSubmitKey} from "../../src/mysoul/web/conversation.mjs";

const require=createRequire(import.meta.url);
const MarkdownIt=require("../../src/mysoul/web/vendor/markdown-it.min.js");
const html=await readFile(new URL("../../src/mysoul/web/index.html",import.meta.url),"utf8");
const script=(await readFile(new URL("../../src/mysoul/web/app.js",import.meta.url),"utf8")).replace(/^import .*;\r?\n/gm,"");

async function until(predicate) {
  for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}
  assert.ok(predicate(),"UI did not settle");
}
async function fixture(chat,modelRequest) {
  const dom=new JSDOM(html,{url:"http://127.0.0.1:8765/#token=fixture-token",runScripts:"outside-only",pretendToBeVisual:true});
  const {window}=dom,document=window.document;
  const server={state:{fatigue:0,activity:"rest",mode:"normal",model_calls:0,tokens_used:0},limits:{model_calls:100,tokens:50000},backend:"replay",send_enabled:false,persona:{public:"A companion"},recap:{version:0,text:"",refs:[]},gates:{provider:"deferred",mempalace:"deferred",qq:"deferred",isolation:"disabled"},goals:[],activities:[],interactions:[],drafts:[],effects:[]};
  const sends=[];
  server.model={version:0,mode:"replay",url:"",model:"",key_present:false,source:"runtime",output_token_limit:null,token_budget:50000};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  window.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new window.Event("close"));};
  window.markdownit=MarkdownIt;window.createMessageRenderer=createMessageRenderer;window.shouldSubmitKey=shouldSubmitKey;
  window.matchMedia=()=>({matches:false,addEventListener(){}});
  window.setInterval=()=>0;
  window.fetch=async(path,options)=>{
    let result;
    if(path==="/api/session")result={csrf:"fixture-csrf"};
    else if(path==="/api/status")result=server;
    else if(path==="/api/chat"){
      const body=JSON.parse(options.body);sends.push(body.text);if(chat)await chat();
      result={event_id:`event-${sends.length}`,choice:"owner_served",input:body.text,text:"**已收到**"};
      server.interactions.push(result);
    }else if(path==="/api/model"||path==="/api/model/test"){
      const body=JSON.parse(options.body);
      if(modelRequest)await modelRequest(path,body);
      if(path==="/api/model/test")result={ok:true};
      else {server.model={...body,version:body.expected_version+1,key_present:true,source:"local"};delete server.model.api_key;server.limits.tokens=body.token_budget;result=server.model;}
    }else if(path==="/api/evidence"||path==="/api/recap/history")result=[];
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
  return {window,document,textarea,sends,send,close:()=>window.close()};
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
    assert.match(d.getElementById("runtime-label").textContent,/my-model/);
    assert.equal(d.getElementById("model-key").type,"password");
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
