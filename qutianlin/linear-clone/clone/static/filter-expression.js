// Filter expressions use the source's URL representation: base64url JSON AND/OR groups.
export const priorityNames=['No priority','Urgent','High','Medium','Low'];
const forbidden=new Set(['__proto__','prototype','constructor']);
export function validateExpression(value,depth=0,budget={left:200}){
 if(depth>12||--budget.left<0||!value||typeof value!=='object'||Array.isArray(value))throw Error('Invalid filter expression');
 for(const [key,item] of Object.entries(value)){
  if(forbidden.has(key))throw Error('Invalid filter expression');
  if(key==='and'||key==='or'){
   if(!Array.isArray(item))throw Error('Invalid filter group');
   for(const child of item)validateExpression(child,depth+1,budget);
  }else if(Array.isArray(item)){
   if(item.length>100||item.some(x=>x!==null&&!['string','number','boolean'].includes(typeof x)))throw Error('Invalid filter values');
  }else if(item&&typeof item==='object')validateExpression(item,depth+1,budget);
  else if(item!==null&&!['string','number','boolean'].includes(typeof item))throw Error('Invalid filter value');
 }
 return value;
}
export function encodeExpression(value){validateExpression(value);const bytes=new TextEncoder().encode(JSON.stringify(value));if(bytes.length>20000)throw Error('Filter expression is too large');return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}
export function decodeExpression(value){if(!value||value.length>20000)throw Error('Invalid filter link');try{const bytes=Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')),x=>x.charCodeAt(0));return validateExpression(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));}catch{throw Error('Invalid filter link');}}
export function hasConditions(node){if(!node||typeof node!=='object')return false;const group=node.and||node.or;return group?group.some(hasConditions):Object.keys(node).length>0;}
export function resolveFilterDate(value,now=Date.now()){
 if(typeof value==='number')return Math.abs(value)<1e12?value*1000:value;
 if(typeof value!=='string')return NaN;
 const duration=/^(-?)P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?$/.exec(value);
 if(!duration)return Date.parse(value);
 const sign=duration[1]?-1:1,date=new Date(now),day=date.getUTCDate();
 const months=sign*(Number(duration[2]||0)*12+Number(duration[3]||0));
 if(months){date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+months);const end=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();date.setUTCDate(Math.min(day,end));}
 date.setUTCDate(date.getUTCDate()+sign*(Number(duration[4]||0)*7+Number(duration[5]||0)));return +date;
}
function compare(actual,operator,expected,now){
 const values=Array.isArray(actual)?actual:[actual];
 const equal=(a,b)=>a===b||(a==null&&b==null);
 if(operator==='in')return values.some(a=>expected.some(b=>equal(a,b)));
 if(operator==='nin')return !values.some(a=>expected.some(b=>equal(a,b)));
 if(operator==='eq')return values.some(a=>equal(a,expected));
 if(operator==='neq')return !values.some(a=>equal(a,expected));
 if(operator==='null')return expected?values.every(a=>a==null||a===''):values.some(a=>a!=null&&a!=='');
 if(operator==='contains')return values.some(a=>String(a??'').toLocaleLowerCase().includes(String(expected).toLocaleLowerCase()));
 if(operator==='containsIgnoreCase')return values.some(a=>String(a??'').toLocaleLowerCase().includes(String(expected).toLocaleLowerCase()));
 if(operator==='notContainsIgnoreCase')return !compare(actual,'containsIgnoreCase',expected,now);
 if(operator==='notContains')return !compare(actual,'contains',expected,now);
 if(operator==='lt'||operator==='gt'||operator==='lte'||operator==='gte')return values.some(a=>{if(a==null||a==='')return false;let b=expected;if(typeof b==='string'&&(/^-?P/.test(b)||/^\d{4}-\d{2}-\d{2}/.test(b))){const reference=typeof a==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(a)?new Date(now).setUTCHours(0,0,0,0):now;a=resolveFilterDate(a,reference);b=resolveFilterDate(b,reference);}return operator==='lt'?a<b:operator==='gt'?a>b:operator==='lte'?a<=b:a>=b;});
 throw Error('Unsupported filter operator');
}
const comparisons=new Set(['in','nin','eq','neq','null','contains','notContains','containsIgnoreCase','notContainsIgnoreCase','lt','gt','lte','gte']);
export function matchesExpression(record,expression,now=Date.now()){
 function match(actual,node){
  if(!hasConditions(node))return true;
  if(node.and||node.or){const group=node.and||node.or,items=group.filter(hasConditions);return !items.length||(node.and?items.every(x=>match(actual,x)):items.some(x=>match(actual,x)));}
  return Object.entries(node).every(([key,value])=>{
   if(comparisons.has(key))return compare(actual,key,value,now);
   if(key==='some')return (Array.isArray(actual)?actual:[]).some(x=>match(x,value));
   if(key==='every')return (Array.isArray(actual)?actual:[]).every(x=>match(x,value));
   if(key==='none')return !(Array.isArray(actual)?actual:[]).some(x=>match(x,value));
   if(key==='length'&&Array.isArray(actual))return match(actual.length,value);
   if(Array.isArray(actual))return actual.some(item=>match(item?.[key],value));
   return match(actual?.[key],value);
  });
 }
 return match(record,expression);
}
export function issueFilterRecord(issue,account={},labels=[],groups=[],issues=[]){
 const person=email=>email?{id:email,email,isMe:email===account.email_normalized,name:email===account.email_normalized?account.display_name:email}:null;
 return {...issue,state:{name:issue.status},priority:priorityNames.indexOf(issue.priority),assignee:person(issue.assignee),creator:person(issue.creator),project:issue.project?{id:issue.project}:null,labels:(issue.labels||[]).map(name=>({name,parent:{name:groups.find(g=>g.id===labels.find(l=>l.title===name)?.group)?.title}})),searchableContent:[issue.title,issue.description].filter(Boolean).join('\n'),content:[issue.title,issue.description].filter(Boolean).join('\n'),lastAppliedTemplate:issue.template?{id:issue.template}:null,subscribers:[...new Set([...(issue.subscribers||[]),...(issue.subscribed?[account.email_normalized]:[])])].filter(Boolean).map(person),createdAt:issue.created_at,updatedAt:issue.updated_at,dueDate:issue.due_date||null,startedAt:issue.started_at||null,completedAt:issue.completed_at||null,canceledAt:issue.canceled_at||null,autoClosedAt:issue.auto_closed_at||null,triagedAt:issue.triaged_at||null,accumulatedStateUpdatedAt:issue.status_updated_at||issue.created_at,children:issues.filter(x=>x.parent===issue.id).map(x=>({id:x.id})),parent:issue.parent?{id:issue.parent}:null,hasBlockedByRelations:(issue.blocked_by||[]).length>0||issues.some(x=>(x.blocks||[]).includes(issue.id)),hasBlockingRelations:(issue.blocks||[]).length>0||issues.some(x=>(x.blocked_by||[]).includes(issue.id)),hasRelatedRelations:(issue.related||[]).length>0||issues.some(x=>(x.related||[]).includes(issue.id)),hasDuplicateRelations:!!issue.duplicate_of||issues.some(x=>x.duplicate_of===issue.id)};
}
export function readPath(object,path){return path.reduce((value,key)=>value?.[key],object);}
export function condition(path,operator,values){let value={[operator]:values};for(const key of [...path].reverse())value={[key]:value};return value;}
