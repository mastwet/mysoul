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
async function fixture(chat) {
  const dom=new JSDOM(html,{url:"http://127.0.0.1:8765/#token=fixture-token",runScripts:"outside-only",pretendToBeVisual:true});
  const {window}=dom,document=window.document;
  const server={state:{fatigue:0,activity:"rest",mode:"normal",model_calls:0,tokens_used:0},limits:{model_calls:100,tokens:50000},backend:"replay",send_enabled:false,persona:{public:"A companion"},recap:{version:0,text:"",refs:[]},gates:{provider:"deferred",mempalace:"deferred",qq:"deferred",isolation:"disabled"},goals:[],activities:[],interactions:[],drafts:[],effects:[]};
  const sends=[];
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
