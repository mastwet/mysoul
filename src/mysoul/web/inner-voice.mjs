const statuses={waiting:"检查中",silent:"保持安静",message:"已发言",error:"失败",interrupted:"已打断",paused:"已暂停",decided:"已决策",progress:"推进中",completed:"已完成",failed:"失败",superseded:"已打断",queued:"等待处理",running:"进行中",scheduled:"已安排",replaced:"已替换",fired:"已唤醒",cancelled:"已取消"};
const categories={initiative:"自主检查",conversation:"对话决策",task:"任务进度",maintenance:"记忆整理",schedule:"自主日程"};
const fields={due_at:"唤醒时间",triggered_at:"实际唤醒",epoch:"调度轮次",activity:"选择活动",chat_action:"发言选择",event_id:"事件引用",tool:"工具",error_code:"错误类型",error_message:"错误说明",goal_id:"任务引用",activity_id:"执行引用",step:"执行步数",outcome:"执行结果",publication_status:"发布结果",background_goal_id:"后台任务引用",background_status:"后台状态",started_at:"开始时间",finished_at:"结束时间",stage:"整理阶段",attempts:"重试次数",next_attempt_at:"下次重试"};
const values={rest:"休息",read_chat:"回应聊天",work:"工作",read_news:"阅读新闻",reflection:"反思",reply:"发言",silent:"安静",read:"阅读",duplicate:"已抑制重复",yield:"等待下次检查",confirmed:"已确认",not_sent:"未执行",unknown:"结果未知",in_flight:"执行中",failed:"失败",autonomy_disabled:"自主功能已关闭",conversation_reset:"会话已重置",restart:"服务重启",cancelled:"关联任务已取消"};
function timeText(value){const date=new Date(value);return Number.isNaN(date.valueOf())?String(value||""):date.toLocaleString("zh-CN",{hour12:false});}

export function createInnerVoice({document,api}){
  const get=id=>document.getElementById(id),root=get("inner-voice"),list=get("voice-list");
  const filter=get("voice-category"),refreshButton=get("voice-refresh"),olderButton=get("voice-older");
  const feedback=get("voice-feedback"),empty=get("voice-empty");
  let active=false,category="all",loaded=false,cursor=null,more=false,request=0,loading=false;
  let records=new Map(),rows=new Map();
  const rendered=new WeakMap();
  function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
  function controls(){refreshButton.disabled=loading;olderButton.disabled=loading;olderButton.hidden=!more;list.setAttribute("aria-busy",String(loading));}
  function rowFor(entry){
    let row=rows.get(entry.id);
    const signature=JSON.stringify(entry);
    if(row&&rendered.get(row)===signature)return row;
    if(!row){
      row=node("article",undefined,"voice-entry");row.dataset.voiceId=entry.id;
      const meta=node("div",undefined,"voice-meta");meta.append(node("time",undefined,"voice-time"),node("span",undefined,"voice-status"));
      row.append(meta,node("h2",undefined,"voice-title"),node("p",undefined,"voice-summary"));
      const details=node("details",undefined,"disclosure voice-details");details.append(node("summary","调试详情"),node("dl",undefined,"voice-fields"));row.append(details);
      rows.set(entry.id,row);
    }
    row.querySelector(".voice-time").textContent=timeText(entry.time);row.querySelector("time").dateTime=entry.time;
    row.querySelector(".voice-status").textContent=statuses[entry.status]||entry.status||"已记录";
    row.querySelector(".voice-title").textContent=entry.title||categories[entry.category]||"决策记录";
    row.querySelector(".voice-summary").textContent=entry.summary||(entry.status==="waiting"?"检查尚未完成，完成后会显示决策说明。":"本次没有提供简短说明，可展开查看运行状态。");
    const dl=row.querySelector("dl");dl.replaceChildren();
    for(const [key,value] of Object.entries(entry.details||{})){
      const text=key.endsWith("_at")?timeText(value):values[value]||String(value);
      dl.append(node("dt",fields[key]||key),node("dd",text));
    }
    row.querySelector("details").hidden=!dl.childNodes.length;
    rendered.set(row,signature);
    return row;
  }
  function render(){
    const before={top:root.scrollTop,height:root.scrollHeight};
    const ordered=[...records.values()].sort((a,b)=>b.time.localeCompare(a.time)||b.id.localeCompare(a.id));
    ordered.forEach((entry,index)=>{const row=rowFor(entry);if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);});
    if(before.top>0)root.scrollTop=before.top+(root.scrollHeight-before.height);
    empty.hidden=ordered.length>0;controls();
  }
  async function load(mode="latest",requestedCategory=category){
    if(!active||(loading&&mode!=="replace"))return;
    const ticket=++request;loading=true;controls();feedback.textContent="正在读取心语…";
    const params=new URLSearchParams({category:requestedCategory,limit:"30"});
    if(mode==="older"&&cursor)params.set("before",cursor);
    try{
      const page=await api("inner-voice?"+params);
      if(ticket!==request||!active)return;
      if(mode==="replace"){
        records=new Map();rows=new Map();list.replaceChildren();category=requestedCategory;
        loaded=false;root.scrollTop=0;
      }
      const overlaps=page.items.some(entry=>records.has(entry.id));
      for(const entry of page.items)records.set(entry.id,entry);
      if(!loaded||mode==="older"||!overlaps){cursor=page.next_before;more=page.has_more;}
      if(page.wakeup){
        const wake=page.wakeup,line=get("voice-wakeup");
        const text=!wake.enabled?"自主唤醒已暂停。":wake.pending?`本体已安排：${timeText(wake.pending.due_at)} · ${wake.pending.reason}`:wake.next_at?`下次默认检查：${timeText(wake.next_at)}`:"尚未安排下一次自主检查。";
        if(line.textContent!==text)line.textContent=text;
      }
      loaded=true;feedback.textContent="";render();
    }catch(error){
      if(ticket!==request||!active)return;
      filter.value=category;feedback.textContent="心语读取失败，已保留当前记录。点击刷新重试。";
      if(!loaded)empty.hidden=true;
    }finally{if(ticket===request){loading=false;controls();}}
  }
  refreshButton.addEventListener("click",()=>load());
  olderButton.addEventListener("click",()=>load("older"));
  filter.addEventListener("change",()=>load("replace",filter.value));
  return {
    setActive(value){active=value;if(!value){request++;loading=false;filter.value=category;feedback.textContent="";controls();}},
    refresh:()=>load(),
  };
}
