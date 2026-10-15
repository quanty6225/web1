/* Common editing operations. All uploads and version requests stay local. */
function workImage(accept){
 const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';
 input.onchange=async()=>{try{const file=input.files[0];if(!file)return;if(file.size>900000)throw Error('Choose an image smaller than 900 KB.');const value=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});await accept(value)}catch(error){showDialog('Unable to Add Image','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}};input.click();
}
function workButton(parent,id,label,action){const b=document.createElement('button');b.id=id;b.textContent=label;b.onclick=action;parent.append(b);return b}
function enhanceWorkToolbar(state,tools){
 const bar=document.querySelector('.work-toolbar');
 workButton(bar,'work-backup','Export Local Copy',async()=>{try{await tools.save();localDownload(JSON.stringify({format:'icloud-local-v1',app:state.app,name:state.doc.name,body:state.doc._editor},null,2),'application/json',state.doc.name+'.icloud.json')}catch(error){}});
 workButton(bar,'work-duplicate','Duplicate',async()=>{try{await tools.save();const copy=await api('/api/work/'+state.doc.id+'/duplicate',{});navigate('/'+state.app+'/edit/?item='+copy.id)}catch(error){showDialog('Unable to Duplicate','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}});
 workButton(bar,'work-versions','Version History',async()=>{
  try{await tools.save();const data=await api('/api/work/'+state.doc.id+'/versions');showDialog('Version History',data.versions.length?'<p>Restore a saved version. Your current version will be retained.</p><div class="work-version-list">'+data.versions.map(v=>`<div><span>${esc(v.name)} · ${new Date(v.created*1000).toLocaleString()} · v${v.revision}</span><button data-work-version="${v.revision}">Restore</button></div>`).join('')+'</div><p class="error" role="alert"></p><button data-action="close">Done</button>':'<p>No Earlier Versions</p><button data-action="close">Done</button>');
   modal.querySelectorAll('[data-work-version]').forEach(button=>button.onclick=async()=>{modal.querySelectorAll('button').forEach(b=>b.disabled=true);try{await api('/api/work/'+state.doc.id+'/restore',{version:+button.dataset.workVersion,revision:state.doc._editor_revision});location.reload()}catch(error){modal.querySelector('.error').textContent=error.message;modal.querySelectorAll('button').forEach(b=>b.disabled=false)}})
  }catch(error){showDialog('Unable to Open Versions','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}
 });
 workButton(bar,'work-print','Print',async()=>{try{await tools.save();workPrint(state)}catch(error){showDialog('Unable to Print','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}});
}
function enhanceWorkSurface(state,tools){
 const actions=document.querySelector('.work-actions');
 if(state.app==='pages'){
  const editor=document.querySelector('#work-page');let range=null;
  const capture=()=>{const selection=getSelection();if(selection.rangeCount&&editor.contains(selection.anchorNode))range=selection.getRangeAt(0).cloneRange()};
  const execute=(command,value)=>{editor.focus();if(range){const s=getSelection();s.removeAllRanges();s.addRange(range)}document.execCommand(command,false,value);capture()};
  const format=document.createElement('div');format.className='work-format-extra';format.innerHTML='<label>Font<select aria-label="Font"><option>Arial</option><option>Georgia</option><option>Times New Roman</option><option>Courier New</option></select></label><label>Size<select aria-label="Font size">'+[[1,10],[2,13],[3,16],[4,18],[5,24],[6,32],[7,48]].map(([v,n])=>`<option value="${v}" ${v===3?'selected':''}>${n}</option>`).join('')+'</select></label><label>Color<input type="color" aria-label="Text color" value="#000000"></label>';
  format.onpointerdown=capture;format.onfocusin=()=>{if(!range)capture()};
  format.querySelector('[aria-label="Font"]').onchange=e=>execute('fontName',e.target.value);
  format.querySelector('[aria-label="Font size"]').onchange=e=>execute('fontSize',e.target.value);
  format.querySelector('[aria-label="Text color"]').oninput=e=>execute('foreColor',e.target.value);actions.append(format);
  for(const [cmd,label] of [['justifyLeft','Align Left'],['justifyCenter','Center'],['justifyRight','Align Right'],['justifyFull','Justify']]){const b=workButton(actions,'work-'+cmd,label,()=>execute(cmd));b.onmousedown=e=>{capture();e.preventDefault()}}
  const image=workButton(actions,'work-image','Add Image',()=>workImage(src=>execute('insertHTML','<img src="'+esc(src)+'" alt=""><p><br></p>')));image.onmousedown=capture;
  const table=workButton(actions,'work-table','Insert Table',()=>{showDialog('Insert Table','<form id="work-table-form"><label>Rows<input name="rows" aria-label="Rows" type="number" min="1" max="20" value="3" required></label><label>Columns<input name="columns" aria-label="Columns" type="number" min="1" max="10" value="3" required></label><div class="actions"><button type="button" data-action="close">Cancel</button><button type="submit">Insert</button></div></form>');modal.querySelector('form').onsubmit=e=>{e.preventDefault();const r=Math.min(20,Math.max(1,+e.target.elements.rows.value)),c=Math.min(10,Math.max(1,+e.target.elements.columns.value));closeDialog();execute('insertHTML','<table><tbody>'+Array.from({length:r},()=>'<tr>'+Array.from({length:c},()=>'<td><br></td>').join('')+'</tr>').join('')+'</tbody></table><p><br></p>')}});table.onmousedown=capture;
  workButton(actions,'work-replace','Find and Replace',()=>formDialog('Find and Replace',field('find','Find')+field('replacement','Replace with'),values=>{if(!values.find)throw Error('Enter text to find.');tools.remember();const walker=document.createTreeWalker(editor,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode())node.textContent=node.textContent.split(values.find).join(values.replacement);state.body.html=editor.innerHTML;tools.changed()}));
 }else if(state.app==='numbers'){
  const sheet=state.body.sheets[state.index],select=()=>({row:Math.min(state.cell?.row||0,sheet.cells.length-1),col:Math.min(state.cell?.col||0,sheet.cells[0].length-1)});
  workButton(actions,'work-delete-row','Delete Row',()=>{if(sheet.cells.length<=1)return;const {row}=select();tools.update(()=>{sheet.cells.splice(row,1);workShiftFormats(sheet,'row',row);sheet.cells.forEach(line=>line.forEach((v,c)=>line[c]=workShiftReferences(v,'row',row)));state.cell=null})}).disabled=sheet.cells.length<=1;
  workButton(actions,'work-delete-column','Delete Column',()=>{if(sheet.cells[0].length<=1)return;const {col}=select();tools.update(()=>{workShiftFormats(sheet,'col',col);sheet.cells.forEach(row=>{row.splice(col,1);row.forEach((v,c)=>row[c]=workShiftReferences(v,'col',col))});state.cell=null})}).disabled=sheet.cells[0].length<=1;
  for(const [id,label,sign] of [['ascending','Sort Ascending',1],['descending','Sort Descending',-1]])workButton(actions,'work-sort-'+id,label,()=>{const {col}=select();if(sheet.cells.some(row=>row.some(v=>v.startsWith('=')))){showDialog('Sort Table','<p>Sorting tables containing formulas is not available in this local editor.</p><button data-action="close">Done</button>');return}tools.update(()=>{const order=sheet.cells.map((row,index)=>({row,index})).sort((a,b)=>{const x=a.row[col],y=b.row[col];return sign*(x.trim()&&y.trim()&&Number.isFinite(+x)&&Number.isFinite(+y)?+x-+y:x.localeCompare(y))});const formats={};order.forEach((entry,r)=>entry.row.forEach((_,c)=>{const old=sheet.formats?.[String.fromCharCode(65+c)+(entry.index+1)];if(old)formats[String.fromCharCode(65+c)+(r+1)]=old}));sheet.cells=order.map(entry=>entry.row);if(sheet.formats)sheet.formats=formats})});
  workNumberControls(state,tools,sheet,actions);
  const filter=document.createElement('input');filter.type='search';filter.placeholder='Filter rows';filter.setAttribute('aria-label','Filter rows');filter.oninput=()=>{const q=filter.value.toLowerCase();document.querySelectorAll('.work-table tbody tr').forEach((tr,i)=>tr.hidden=!sheet.cells[i].some(v=>v.toLowerCase().includes(q)))};actions.append(filter);
  document.querySelectorAll('.work-table input').forEach(input=>input.onpaste=event=>{const text=event.clipboardData.getData('text/plain');if(!/[\t\n]/.test(text))return;event.preventDefault();const rows=text.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(row=>row.split('\t')),r=+input.dataset.row,c=+input.dataset.col;if(r+rows.length>200||rows.some(row=>c+row.length>26||row.some(cell=>cell.length>2000))){showDialog('Unable to Paste','<p>The pasted cells exceed the table limits.</p><button data-action="close">Done</button>');return}tools.update(()=>{const width=Math.max(sheet.cells[0].length,c+Math.max(...rows.map(row=>row.length)));while(sheet.cells.length<r+rows.length)sheet.cells.push(Array(width).fill(''));sheet.cells.forEach(row=>{while(row.length<width)row.push('')});rows.forEach((row,dr)=>row.forEach((v,dc)=>sheet.cells[r+dr][c+dc]=v))})});
  workButton(actions,'work-import-csv','Import CSV',()=>{const input=document.createElement('input');input.type='file';input.accept='.csv,text/csv';input.onchange=async()=>{try{const file=input.files[0];if(!file)return;if(file.size>1000000)throw Error('Choose a CSV smaller than 1 MB.');const cells=workParseCSV(await file.text());if(state.body.sheets.length>=10)throw Error('Keep at most 10 sheets.');tools.update(()=>{state.body.sheets.push({name:file.name.slice(0,100),cells});state.index=state.body.sheets.length-1;state.cell=null})}catch(error){showDialog('Unable to Import','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}};input.click()});
 }else{
  const slide=state.body.slides[state.index],surface=document.querySelector('.work-slide');surface.style.background=slide.background||'#ffffff';surface.classList.add(slide.layout||'title-body');
  if(slide.image){const img=document.createElement('img');img.src=slide.image;img.alt='Slide image';surface.prepend(img)}
  workButton(actions,'work-slide-image','Add Image',()=>workImage(src=>tools.update(()=>slide.image=src)));
  workButton(actions,'work-remove-image','Remove Image',()=>tools.update(()=>delete slide.image)).disabled=!slide.image;
  const controls=document.createElement('div');controls.className='work-format-extra';controls.innerHTML='<label>Background<input type="color" aria-label="Slide background" value="'+esc(slide.background||'#ffffff')+'"></label><label>Layout<select aria-label="Slide layout"><option value="title-body">Title and Body</option><option value="title-only">Title Only</option><option value="image-left">Image and Text</option></select></label><label>Transition<select aria-label="Slide transition"><option value="none">None</option><option value="fade">Fade</option><option value="slide">Slide</option></select></label>';actions.append(controls);
  controls.querySelector('[aria-label="Slide background"]').onchange=e=>tools.update(()=>slide.background=e.target.value);
  for(const [label,key,fallback] of [['Slide layout','layout','title-body'],['Slide transition','transition','none']]){const select=controls.querySelector(`[aria-label="${label}"]`);select.value=slide[key]||fallback;select.onchange=e=>tools.update(()=>slide[key]=e.target.value)}
 }
}
function workShiftReferences(value,axis,index){
 if(!value.startsWith('='))return value;
 const parse=ref=>{const m=/^(\$?)([A-Z])(\$?)([1-9]\d*)$/i.exec(ref);return {ca:m[1],col:m[2].toUpperCase().charCodeAt(0)-65,ra:m[3],row:+m[4]-1}};
 const write=ref=>ref.ca+String.fromCharCode(65+ref.col)+ref.ra+(ref.row+1),key=axis==='row'?'row':'col';
 return value.replace(/(\$?[A-Z]\$?[1-9]\d*)(?::(\$?[A-Z]\$?[1-9]\d*))?/gi,(all,first,last)=>{
  const a=parse(first);if(!last){if(a[key]===index)return '#REF!';if(a[key]>index)a[key]--;return write(a)}
  const b=parse(last),low=Math.min(a[key],b[key]),high=Math.max(a[key],b[key]);if(index>high)return all;if(low===high&&index===low)return '#REF!';
  const nextLow=index<low?low-1:low,nextHigh=high-1,forward=a[key]<=b[key];a[key]=forward?nextLow:nextHigh;b[key]=forward?nextHigh:nextLow;return write(a)+':'+write(b);
 });
}
function workParseCSV(text){text=text.replace(/^\uFEFF/,'');const rows=[];let row=[],value='',quoted=false;for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++}else if(quoted)quoted=false;else if(!value)quoted=true;else value+=ch}else if(ch===','&&!quoted){row.push(value);value=''}else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(value);rows.push(row);row=[];value=''}else value+=ch}if(quoted)throw Error('CSV contains an unfinished quoted value.');if(value||row.length)rows.push([...row,value]);if(!rows.length||rows.length>200||rows.some(r=>r.length>26||r.some(c=>c.length>2000)))throw Error('Use 1–200 rows, at most 26 columns and at most 2000 characters per cell.');const width=Math.max(...rows.map(r=>r.length));return rows.map(r=>r.concat(Array(width-r.length).fill('')))}

function workPrint(state){
 document.querySelector('#work-print-root')?.remove();const root=document.createElement('main');root.id='work-print-root';
 const body=state.doc._editor;
 if(state.app==='pages'){root.className='work-paper';root.innerHTML=body.html}
 else if(state.app==='numbers'){root.innerHTML=body.sheets.map(sheet=>'<section><h1>'+esc(sheet.name)+'</h1><table>'+workCalculate(sheet.cells).map((row,r)=>'<tr>'+row.map((value,c)=>'<td>'+esc(workFormatValue(value,sheet.formats?.[String.fromCharCode(65+c)+(r+1)]))+'</td>').join('')+'</tr>').join('')+'</table></section>').join('')}
 else root.innerHTML=body.slides.map(slide=>'<section class="work-slide '+esc(slide.layout||'title-body')+'" style="background:'+esc(slide.background||'#ffffff')+'">'+(slide.image?'<img src="'+esc(slide.image)+'" alt="">':'')+'<h1>'+esc(slide.title)+'</h1><p>'+esc(slide.body)+'</p></section>').join('');
 document.body.append(root);window.addEventListener('afterprint',()=>root.remove(),{once:true});window.print();
}

function workImport(app){
 const input=document.createElement('input');input.type='file';input.accept='.json,application/json';input.onchange=async()=>{try{const file=input.files[0];if(!file)return;if(file.size>2500000)throw Error('Choose a local copy smaller than 2.5 MB.');const data=JSON.parse(await file.text());if(data.app!==app)throw Error('Open this copy in '+(data.app||'its original application')+'.');const doc=await api('/api/work/import',{app,name:data.name,body:data.body});navigate('/'+app+'/edit/?item='+doc.id)}catch(error){showDialog('Unable to Import','<p>'+esc(error.message)+'</p><button data-action="close">Done</button>')}};input.click();
}

function workFormatValue(value,format){
 if(value===''||String(value).startsWith('#')||!Number.isFinite(Number(value)))return value;
 const n=+value;if(format?.number==='number')return n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});if(format?.number==='currency')return n.toLocaleString('en-US',{style:'currency',currency:'CNY'});if(format?.number==='percent')return n.toLocaleString('en-US',{style:'percent',maximumFractionDigits:2});return value;
}
function workShiftFormats(sheet,axis,index){if(!sheet.formats)return;const shifted={};for(const [key,value] of Object.entries(sheet.formats)){const r=+key.slice(1)-1,c=key.charCodeAt(0)-65,n=axis==='row'?r:c;if(n===index)continue;const nr=axis==='row'&&r>index?r-1:r,nc=axis==='col'&&c>index?c-1:c;shifted[String.fromCharCode(65+nc)+(nr+1)]=value}sheet.formats=shifted}
function workSyncCellFormat(sheet,key){const controls=document.querySelector('.work-cell-format');if(!controls)return;const style=sheet.formats?.[key]||{};controls.querySelector('select').value=style.number||'general';controls.querySelector('[type=checkbox]').checked=!!style.bold;controls.querySelector('[type=color]').value=style.color||'#222222';controls.querySelector('output').textContent=key}
function workNumberControls(state,tools,sheet,actions){
 const controls=document.createElement('div');controls.className='work-format-extra work-cell-format';controls.innerHTML='<output>A1</output><label>Format<select aria-label="Cell number format"><option value="general">General</option><option value="number">Number</option><option value="currency">Currency (CNY)</option><option value="percent">Percent</option></select></label><label><input type="checkbox" aria-label="Bold cell">Bold</label><label>Color<input type="color" aria-label="Cell text color" value="#222222"></label>';actions.append(controls);
 const key=()=>String.fromCharCode(65+Math.min(state.cell?.col||0,sheet.cells[0].length-1))+(Math.min(state.cell?.row||0,sheet.cells.length-1)+1);
 for(const [selector,property] of [['select','number'],['[type=checkbox]','bold'],['[type=color]','color']])controls.querySelector(selector).onchange=e=>{const value=e.target.type==='checkbox'?e.target.checked:e.target.value;tools.update(()=>{sheet.formats||={};sheet.formats[key()]={...(sheet.formats[key()]||{}),[property]:value}})};
 for(const input of document.querySelectorAll('.work-table input')){const style=sheet.formats?.[input.getAttribute('aria-label')];input.style.fontWeight=style?.bold?'700':'400';input.style.color=style?.color||'#222222';if(input!==document.activeElement)input.value=workFormatValue(input.value,style)}
 workSyncCellFormat(sheet,key());
 const label=document.createElement('label');label.className='work-format-extra';label.innerHTML='Chart<select aria-label="Chart type"><option value="none">None</option><option value="bar">Bar</option><option value="line">Line</option></select>';actions.append(label);const chart=label.querySelector('select');chart.value=sheet.chart||'none';chart.onchange=e=>tools.update(()=>sheet.chart=e.target.value);workRefreshChart(sheet);
}
function workRefreshChart(sheet){
 document.querySelector('#work-chart')?.remove();if(!sheet.chart||sheet.chart==='none')return;
 const figure=document.createElement('figure');figure.id='work-chart';figure.innerHTML='<figcaption>'+esc(sheet.name)+'</figcaption><p>First column: labels · Second column: values · Up to 50 rows</p>';
 const values=workCalculate(sheet.cells),rows=values.filter(row=>row[1]!==''&&Number.isFinite(Number(row[1]))).slice(0,50).map(row=>({label:String(row[0]),value:+row[1]}));
 if(!rows.length){figure.insertAdjacentHTML('beforeend','<p>Enter numeric values in column B to display a chart.</p>');document.querySelector('.work-surface').append(figure);return}
 const width=Math.max(500,rows.length*55),height=300,min=Math.min(0,...rows.map(r=>r.value)),max=Math.max(0,...rows.map(r=>r.value)),scale=Math.max(Math.abs(min),Math.abs(max),1),span=(max/scale-min/scale)||1,x=i=>50+(i+.5)*(width-70)/rows.length,y=v=>240-(v/scale-min/scale)/span*210,zero=y(0);
 let shapes='<line x1="40" y1="'+zero+'" x2="'+(width-15)+'" y2="'+zero+'" stroke="#777"/>';
 rows.forEach((row,i)=>{const px=x(i),py=y(row.value);shapes+=sheet.chart==='bar'?'<rect x="'+(px-15)+'" y="'+Math.min(py,zero)+'" width="30" height="'+Math.max(1,Math.abs(py-zero))+'" fill="#39a052"><title>'+esc(row.label+': '+row.value)+'</title></rect>':'<circle cx="'+px+'" cy="'+py+'" r="4" fill="#248a3c"><title>'+esc(row.label+': '+row.value)+'</title></circle>';shapes+='<text x="'+px+'" y="'+(py<zero?py-6:py+15)+'" text-anchor="middle" font-size="11">'+esc(row.value)+'</text><text x="'+px+'" y="270" text-anchor="middle" font-size="11">'+esc(row.label.slice(0,9))+'</text>'});
 if(sheet.chart==='line')shapes='<polyline points="'+rows.map((r,i)=>x(i)+','+y(r.value)).join(' ')+'" fill="none" stroke="#248a3c" stroke-width="2"/>'+shapes;
 figure.insertAdjacentHTML('beforeend','<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="'+esc(sheet.chart+' chart for '+sheet.name)+'" viewBox="0 0 '+width+' '+height+'">'+shapes+'</svg>');document.querySelector('.work-surface').append(figure);
}
