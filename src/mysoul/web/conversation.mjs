// This renderer owns the safe Markdown policy for untrusted assistant text.
export function createMessageRenderer(MarkdownIt) {
  const parser=new MarkdownIt({html:false,linkify:false,typographer:false,breaks:false});
  parser.validateLink=url=>/^(https?:|mailto:)/i.test(url);
  parser.renderer.rules.image=(tokens,index)=>parser.utils.escapeHtml(tokens[index].content);
  parser.renderer.rules.link_open=(tokens,index,options,env,self)=>{
    tokens[index].attrSet("target","_blank");
    tokens[index].attrSet("rel","noopener noreferrer");
    return self.renderToken(tokens,index,options);
  };
  return text=>parser.render(text);
}

export function shouldSubmitKey(event,enterSends) {
  if(event.key!=="Enter"||event.isComposing||event.keyCode===229)return false;
  return enterSends?!event.shiftKey:!!(event.ctrlKey||event.metaKey);
}
