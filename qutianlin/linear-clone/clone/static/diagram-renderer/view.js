import mermaid from './mermaid.js';
const supported=new Set(['flowchart','flowchart-v2','sequence','class','classDiagram','stateDiagram','er','journey','gantt','pie','quadrantChart','requirement','gitGraph','timeline','sankey','xychart','block','packet','kanban','c4']);
let serial=0,queue=Promise.resolve(),drag=null;
const send=value=>parent.postMessage({linearDiagram:true,...value},location.origin);
addEventListener('message',event=>{if(event.source!==parent||event.origin!==location.origin||event.data?.type!=='render')return;const {text,request,theme}=event.data;if(typeof text!=='string')return;const current=++serial;queue=queue.catch(()=>{}).then(async()=>{
 if(current!==serial)return;const root=document.querySelector('#diagram');root.replaceChildren();if(!text.trim()){send({type:'rendered',request,empty:true});return;}
 const container=document.createElement('div');container.id='rendering';document.body.append(container);
 try{await document.fonts.load('14px "Berkeley Mono"');await document.fonts.ready;mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:theme==='dark'?'dark':'default',fontFamily:'Berkeley Mono',suppressErrorRendering:true,secure:['secure','securityLevel','startOnLoad','maxTextSize','maxEdges','theme','fontFamily','themeCSS','suppressErrorRendering']});
  const source=text.replace(/(?<!\\)\\n/g,'<br/>').replace(/<(img|script|iframe|object|embed|video|audio|link|meta|style|form|input|button|svg|a|base|math)/gi,'&lt;$1');
  const parsed=await mermaid.mermaidAPI.parse(source);if(!supported.has(parsed.diagramType))throw Error('Unsupported diagram type: '+parsed.diagramType);
  const result=await mermaid.mermaidAPI.render('diagram-render-'+current,source,container);if(current!==serial)return;root.innerHTML=result.svg;
  const svg=root.querySelector('svg');for(const unsafe of svg.querySelectorAll('script,iframe,object,embed,link,meta,img,image'))unsafe.remove();
  for(const element of svg.querySelectorAll('*'))for(const attribute of [...element.attributes])if(attribute.name.toLowerCase().startsWith('on'))element.removeAttribute(attribute.name);
  for(const element of svg.querySelectorAll('style'))if(/@import|url\(\s*['"]?(?:https?:|\/\/)/i.test(element.textContent))element.remove();
  const box=svg.viewBox.baseVal;send({type:'rendered',request,width:box.width||svg.getBoundingClientRect().width,height:box.height||svg.getBoundingClientRect().height,diagramType:parsed.diagramType});
 }catch(error){if(current===serial)send({type:'rendered',request,error:String(error?.message||error).replace(/^(?:Parse error on line \d+:)[^\S\r\n]*\r?\n/,'')});}finally{container.remove();}
});});
addEventListener('click',event=>{const link=event.target.closest('a');if(link){event.preventDefault();const href=link.getAttribute('href')||link.getAttribute('xlink:href');if(href&&!href.startsWith('#'))send({type:'link',url:href});}});
addEventListener('dblclick',()=>send({type:'fullscreen'}));
addEventListener('keydown',event=>{if(['Escape','Delete','Backspace'].includes(event.key)){event.preventDefault();send({type:'key',key:event.key});}});
addEventListener('wheel',event=>{event.preventDefault();send({type:'wheel',x:event.deltaX,y:event.deltaY,zoom:event.ctrlKey||event.metaKey});},{passive:false});
addEventListener('pointerdown',event=>{if(event.button===0)drag={x:event.screenX,y:event.screenY};});addEventListener('pointermove',event=>{if(drag&&event.buttons){send({type:'pan',x:event.screenX-drag.x,y:event.screenY-drag.y});drag={x:event.screenX,y:event.screenY};}else drag=null;});addEventListener('pointerup',()=>drag=null);
send({type:'ready'});
