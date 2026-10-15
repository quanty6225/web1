import {condition,priorityNames,readPath} from './filter-expression.js';
import {dateFilterFields} from './filter-dates.js';
import {issueRelationField} from './filter-relations.js';
const options=values=>values.map(value=>({label:String(value),value}));
function related(label,key,choices){return {label,key,path:[key],options:choices,read(node){const x=node[key];if(!x)return;const group=x.or||x.and;if(!Array.isArray(group))return;const values=group.flatMap(x=>x.isMe||x.or?.some(v=>v.isMe)?['current-user']:x.null!==undefined?[null]:x.id?.in||x.id?.nin||[]);return {[x.and?'nin':'in']:values};},build(op,values){const group=[],ids=values.filter(x=>x!==null&&x!=='current-user');if(values.includes(null))group.push({null:op==='in'});if(values.includes('current-user'))group.push(op==='in'?{isMe:{eq:true}}:{or:[{null:true},{isMe:{eq:false}}]});if(ids.length)group.push({id:{[op]:ids}});return {[key]:{[op==='in'?'or':'and']:group}};}};}
function subscribers(account){return {
 label:'Subscribers',key:'subscribers',options:[{label:'Current user',value:'current-user'},...(account.email_normalized?[{label:account.display_name||account.email_normalized,value:account.email_normalized}]:[])],
 operatorLabel(op){return op==='nin'?'does not contain':'contains';},
 read(node){const group=node.subscribers?.or;if(!Array.isArray(group))return;const every=group.find(x=>x.every)?.every;const nodes=every?.and||group,values=nodes.flatMap(x=>x.isMe?['current-user']:x.id?.in||x.id?.nin||[]);return {[every?'nin':'in']:values};},
 build(op,values){const ids=values.filter(x=>x!=='current-user'),me=values.includes('current-user');if(op==='nin')return {subscribers:{or:[{every:{and:[{id:{nin:ids}},...(me?[{isMe:{eq:false}}]:[])]}},{length:{eq:0}}]}};return {subscribers:{or:[...(me?[{isMe:{eq:true}}]:[]),{id:{in:ids}}]}};}
};}

export function fieldsForFilters(state={},account={},route=''){
 if(route==='/qqq153/members')return [{label:'Status',key:'member-status',path:['status'],options:options(['Admin','Guest','Member'])}];
 if(route==='/qqq153/teams')return [{label:'Team name',key:'name',path:['name'],type:'text',operators:['containsIgnoreCase'],inputTitle:'Team name contains…'}];
 return [
  {label:'Status',key:'status',path:['state','name'],options:options((state.workflow_states||[]).map(x=>x.title))},
  related('Assignee','assignee',[{label:'No assignee',value:null},{label:'Current user',value:'current-user'}]),
  related('Creator','creator',[{label:'Current user',value:'current-user'}]),
  {label:'Priority',key:'priority',path:['priority'],options:priorityNames.map((label,value)=>({label,value}))},
  {label:'Labels',key:'labels',options:options((state.labels||[]).map(x=>x.title)),operators:['in','any','nin','not-all'],operatorLabel(op,values){if(values.length===1)return op==='nin'||op==='not-all'?'do not include':'include';return {in:'include all of',any:'include any of',nin:'exclude if any of','not-all':'exclude if all'}[op];},read(node){const x=node.labels;if(!x)return;if(x.and)return {in:x.and.map(v=>v.or?.[0]?.name?.eq).filter(v=>v!==undefined)};if(x.or?.[0]?.or)return {any:x.or.map(v=>v.or?.[0]?.name?.eq)};const excluded=x.or?.find(v=>v.every)?.every.and?.[0]?.name;if(excluded?.nin)return {nin:excluded.nin};if(excluded?.neq)return {'not-all':x.or.filter(v=>v.every).map(v=>v.every.and[0].name.neq)};},build(op,values){
   const positive=values.map(value=>({or:[{name:{eq:value}},{parent:{name:{eq:value}}}]}));
   if(op==='in'||op==='any')return {labels:{[op==='in'?'and':'or']:positive}};
   const exclusion=op==='not-all'?values.map(value=>({every:{and:[{name:{neq:value}},{parent:{name:{neq:value}}}]}})):[{every:{and:[{name:{nin:values}},{parent:{name:{nin:values}}}]}}];
   return {labels:{or:[...exclusion,{length:{eq:0}},{null:true}]}};
  }},
  issueRelationField(),
  ...dateFilterFields(),
  subscribers(account),
  related('Template','lastAppliedTemplate',[{label:'No template',value:null},...(state.issue_templates||[]).map(x=>({label:x.title,value:x.id}))]),
  related('Project','project',[{label:'No project',value:null},...(state.projects||[]).map(x=>({label:x.title,value:x.id}))]),
  {label:'Content',key:'content',path:['searchableContent'],type:'text',operators:['contains'],inputTitle:'Filter by content…'},
 ];
}
export function readCondition(field,node){return field.read?field.read(node):readPath(node,field.path);}
export function makeCondition(field,operator,values){return field.build?field.build(operator,values):condition(field.path,operator,values);}
