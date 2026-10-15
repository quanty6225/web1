importScripts('/static/document-editor/guesslang.js');
const model=new GuessLang();
let queue=Promise.resolve();
self.onmessage=event=>{queue=queue.then(async()=>{const {id,text}=event.data;try{const results=await model.runModel(text);for(const row of results){if(['js','html','json','ts','css','py','xml','php','md'].includes(row.languageId))row.confidence+=.05;else if(['cpp','sh','java','cs','c'].includes(row.languageId))row.confidence+=.025;else if(['bat','ini','makefile','csv','toml'].includes(row.languageId))row.confidence-=.35;else if(row.languageId==='sql')row.confidence-=.1;}results.sort((a,b)=>b.confidence-a.confidence);self.postMessage({id,results});}catch(error){self.postMessage({id,error:String(error)});}});};
