import assert from "node:assert/strict";
import {createRequire} from "node:module";
import test from "node:test";
import {createMessageRenderer, shouldSubmitKey} from "../../src/mysoul/web/conversation.mjs";

const require=createRequire(import.meta.url);
const MarkdownIt=require("../../src/mysoul/web/vendor/markdown-it.min.js");
const render=createMessageRenderer(MarkdownIt);

test("message formatting preserves headings, lists, emphasis and literal code",()=>{
  const html=render("## 检查结果\n\n**完成**\n\n1. 读取\n2. 验证\n\n```html\n<script>alert(1)</script>\n```");
  assert.match(html,/<h2>检查结果<\/h2>/);
  assert.match(html,/<strong>完成<\/strong>/);
  assert.match(html,/<ol>/);
  assert.match(html,/<li>读取<\/li>/);
  assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>/);
});

test("untrusted HTML and dangerous links never become executable markup",()=>{
  const html=render('<img src=x onerror="alert(1)"><script>alert(2)</script>\n[危险](javascript:alert(1))\n[页面](https://example.com)');
  assert.doesNotMatch(html,/<(?:img|script)\b/);
  assert.doesNotMatch(html,/href="javascript:/);
  assert.match(html,/href="https:\/\/example.com"/);
  assert.match(html,/rel="noopener noreferrer"/);
});

test("remote image markup renders only its alternative text",()=>{
  const html=render("![图片说明](https://tracker.invalid/private-marker.png)");
  assert.match(html,/图片说明/);
  assert.doesNotMatch(html,/<img|tracker\.invalid/);
});

test("IME, line breaks and the chosen send shortcut remain distinct",()=>{
  for(const [event,enterSends,want] of [
    [{key:"Enter"},true,true],
    [{key:"Enter",shiftKey:true},true,false],
    [{key:"Enter",isComposing:true},true,false],
    [{key:"Enter",keyCode:229},true,false],
    [{key:"Enter"},false,false],
    [{key:"Enter",ctrlKey:true},false,true],
    [{key:"Enter",metaKey:true},false,true],
    [{key:"a",ctrlKey:true},false,false],
  ])assert.equal(shouldSubmitKey(event,enterSends),want,JSON.stringify(event));
});
