// Identity and revision remain authoritative for late older-page replies.
export function mergeTimeline(current,page) {
 const byId=new Map(current.map(item=>[item.id,item]));
 for(const item of page.items){const old=byId.get(item.id);if(!old||item.revision>=old.revision)byId.set(item.id,item);}
 return [...byId.values()].sort((a,b)=>a.seq-b.seq);
}
export function prependScrollAnchor(previousMetrics,nextMetrics){
 return previousMetrics.scrollTop+nextMetrics.scrollHeight-previousMetrics.scrollHeight;
}
