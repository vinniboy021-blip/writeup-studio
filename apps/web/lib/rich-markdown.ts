// SPDX-License-Identifier: MIT
import MarkdownIt from 'markdown-it';
import TurndownService from 'turndown';

const parser=new MarkdownIt({html:false,linkify:true,breaks:true});
export function markdownToHtml(value:string){return parser.render(value);}
export function htmlToMarkdown(value:string){
 const converter=new TurndownService({headingStyle:'atx',codeBlockStyle:'fenced',bulletListMarker:'-'});
 converter.addRule('fenced-code',{
  filter:node=>node.nodeName==='PRE'&&node.firstChild?.nodeName==='CODE',
  replacement:(_content,node)=>{const code=node.firstChild as HTMLElement;const text=code.textContent||'';const language=(code.className.match(/language-([A-Za-z0-9_+-]+)/)||[])[1]||'';const runs=text.match(/`+/g)||[];const fence='`'.repeat(Math.max(3,...runs.map(v=>v.length+1)));return '\n\n'+fence+language+'\n'+text.replace(/\n$/,'')+'\n'+fence+'\n\n';}
 });
 converter.addRule('strikethrough',{filter:['s','del'],replacement:content=>'~~'+content+'~~'});
 converter.addRule('table',{
  filter:'table',
  replacement:(_content,node)=>{const rows=Array.from((node as HTMLElement).querySelectorAll('tr')).map(tr=>Array.from(tr.querySelectorAll('th,td')).map(cell=>converter.turndown(cell.innerHTML).replace(/\n+/g,' ').replace(/\|/g,'\\|').trim()));if(!rows.length)return '';const width=Math.max(...rows.map(row=>row.length));const line=(row:string[])=>'| '+Array.from({length:width},(_,i)=>row[i]||'').join(' | ')+' |';return '\n\n'+[line(rows[0]),line(Array(width).fill('---')),...rows.slice(1).map(line)].join('\n')+'\n\n';}
 });
 return converter.turndown(value);
}
