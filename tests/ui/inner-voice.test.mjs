import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import {JSDOM} from "jsdom";
import {createInnerVoice} from "../../src/mysoul/web/inner-voice.mjs";

const html=await readFile(new URL("../../src/mysoul/web/index.html",import.meta.url),"utf8");
const entry=(id,summary="我先保持安静。",category="initiative")=>({id,time:`2026-10-23T10:00:0${id}Z`,category,title:"自主检查",summary,status:"silent",details:{epoch:3,publication_status:"silent"}});
const page=(items,next=null)=>({items,next_before:next,has_more:!!next});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
async function settle(){for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));}
function fixture(api){const dom=new JSDOM(html),d=dom.window.document;return {dom,d,voice:createInnerVoice({document:d,api})};}

test("brief decision summaries render literally and details stay open during refresh",async()=>{
  let calls=0;
  const f=fixture(async()=>page([entry("1","<img src=x onerror=alert(1)> 我先休息。") ]));
  try{
    f.voice.setActive(true);await f.voice.refresh();
    const list=f.d.getElementById("voice-list");
    assert.match(list.textContent,/我先休息/);
    assert.equal(list.querySelector("img"),null);
    const details=list.querySelector("details");details.open=true;
    await f.voice.refresh();
    assert.equal(list.querySelector("details"),details);
    assert.equal(details.open,true);
    assert.match(details.textContent,/3/);
  }finally{f.dom.window.close();}
});

test("failed refresh preserves records and can retry",async()=>{
  let failed=false;
  const f=fixture(async()=>{if(failed)throw new Error("offline");return page([entry("1")]);});
  try{
    f.voice.setActive(true);await f.voice.refresh();failed=true;
    await f.voice.refresh();
    assert.match(f.d.getElementById("voice-list").textContent,/我先保持安静/);
    assert.match(f.d.getElementById("voice-feedback").textContent,/失败/);
    failed=false;f.d.getElementById("voice-refresh").click();await settle();
    assert.doesNotMatch(f.d.getElementById("voice-feedback").textContent,/失败/);
  }finally{f.dom.window.close();}
});

test("late filter responses and navigation cannot replace the current view",async()=>{
  const old=deferred();let ready=false;
  const f=fixture(async path=>{if(path.includes("category=task"))return old.promise;return page([entry("2","对话决策", "conversation")]);});
  try{
    f.voice.setActive(true);await f.voice.refresh();
    const filter=f.d.getElementById("voice-category");
    filter.value="task";filter.dispatchEvent(new f.dom.window.Event("change"));
    filter.value="conversation";filter.dispatchEvent(new f.dom.window.Event("change"));await settle();
    old.resolve(page([entry("1","OLD_TASK", "task")]));await settle();
    assert.doesNotMatch(f.d.getElementById("voice-list").textContent,/OLD_TASK/);
    assert.match(f.d.getElementById("voice-list").textContent,/对话决策/);
    f.voice.setActive(false);
    await f.voice.refresh();
    assert.equal(filter.value,"conversation");
  }finally{f.dom.window.close();}
});

test("older pages survive live updates without duplicated entries",async()=>{
  let latest=page([entry("3"),entry("2")],"older");
  const f=fixture(async path=>path.includes("before=")?page([entry("1")]):latest);
  try{
    f.voice.setActive(true);await f.voice.refresh();
    f.d.getElementById("voice-older").click();await settle();
    assert.equal(f.d.querySelectorAll(".voice-entry").length,3);
    latest=page([entry("4"),entry("3","更新后的决策说明")],"older");
    await f.voice.refresh();
    assert.equal(f.d.querySelectorAll(".voice-entry").length,4);
    assert.match(f.d.getElementById("voice-list").textContent,/更新后的决策说明/);
    assert.equal(f.d.getElementById("voice-older").hidden,true);
  }finally{f.dom.window.close();}
});


test("returning after a large burst keeps the missing middle reachable",async()=>{
  const old={...entry("1"),id:"old",time:"2026-10-20T10:00:00Z"};
  let latest=page([old]);
  const burst=Array.from({length:40},(_,i)=>({...entry("1"),id:`burst-${i}`,time:new Date(Date.UTC(2026,9,23,0,40-i)).toISOString()}));
  const f=fixture(async path=>path.includes("before=middle")?page(burst.slice(30).concat([old])):latest);
  try{
    f.voice.setActive(true);await f.voice.refresh();
    f.voice.setActive(false);
    latest=page(burst.slice(0,30),"middle");
    f.voice.setActive(true);await f.voice.refresh();
    assert.equal(f.d.getElementById("voice-older").hidden,false);
    f.d.getElementById("voice-older").click();await settle();
    assert.equal(f.d.querySelectorAll(".voice-entry").length,41);
  }finally{f.dom.window.close();}
});

test("unchanged live refresh preserves text selection for debugging",async()=>{
  const f=fixture(async()=>page([entry("1")]));
  try{
    f.voice.setActive(true);await f.voice.refresh();
    const value=f.d.querySelector(".voice-fields dd");
    const range=f.d.createRange();range.selectNodeContents(value);
    f.dom.window.getSelection().addRange(range);
    assert.equal(f.dom.window.getSelection().toString(),"3");
    await f.voice.refresh();
    assert.equal(f.dom.window.getSelection().toString(),"3");
  }finally{f.dom.window.close();}
});


test("leaving during a filter request restores the committed category",async()=>{
  const pending=deferred();
  const f=fixture(async path=>path.includes("category=task")?pending.promise:page([entry("1")]));
  try{
    f.voice.setActive(true);await f.voice.refresh();
    const filter=f.d.getElementById("voice-category");
    filter.value="task";filter.dispatchEvent(new f.dom.window.Event("change"));
    f.voice.setActive(false);f.voice.setActive(true);await f.voice.refresh();
    assert.equal(filter.value,"all");
    pending.resolve(page([]));await settle();
    assert.match(f.d.getElementById("voice-list").textContent,/我先保持安静/);
  }finally{f.dom.window.close();}
});


test("self wakeup is visible with exact local time and a literal reason",async()=>{
 let pending={due_at:"2026-10-24T12:34:56Z",reason:"<img src=x> 休息后探索",status:"scheduled"};
 const f=fixture(async()=>({...page([{...entry("1"),category:"schedule",title:"唤醒安排",status:pending?"scheduled":"cancelled",details:{due_at:"2026-10-24T12:34:56Z"}}]),wakeup:{enabled:true,next_at:"2026-10-24T12:34:56Z",pending}}));
 try{
  f.voice.setActive(true);await f.voice.refresh();
  const status=f.d.getElementById("voice-wakeup");assert.ok(status);
  assert.match(status.textContent,/休息后探索/);assert.equal(status.querySelector("img"),null);
  assert.match(f.d.getElementById("voice-list").textContent,/已安排/);
  assert.match(f.d.getElementById("voice-list").textContent,/唤醒时间/);
  pending=null;await f.voice.refresh();assert.match(status.textContent,/默认检查/);
  assert.match(f.d.getElementById("voice-list").textContent,/已取消/);
 }finally{f.dom.window.close();}
});
