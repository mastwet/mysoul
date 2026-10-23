import assert from 'node:assert/strict';
import test from 'node:test';
import {mergeTimeline,prependScrollAnchor} from '../../src/mysoul/web/timeline.mjs';
test('pagination with live append and stale revisions keeps every identity once',()=>{
 const row=(seq,revision=1)=>({id:`chat:${seq}`,seq,revision,body:{text:`v${revision}`}});
 let items=mergeTimeline([],{items:[row(3),row(4)]});
 items=mergeTimeline(items,{items:[row(4,2),row(5)]});
 items=mergeTimeline(items,{items:[row(1),row(2),row(4)]});
 assert.deepEqual(items.map(x=>x.seq),[1,2,3,4,5]);assert.equal(items[3].body.text,'v2');
 assert.equal(prependScrollAnchor({scrollTop:120,scrollHeight:1000},{scrollHeight:1600}),720);
});
